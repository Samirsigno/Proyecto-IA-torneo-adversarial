"""Runner: corre dentro del contenedor (o subproceso) del bot y habla con el árbitro.

Uso: `python -m arbitro.runner <carpeta_del_bot>`

Pasos:
1. Aparta el protocolo en descriptores propios (≥ 3) y manda fd 1 a stderr con
   `dup2(2, 1)`: cualquier `print`, `os.write(1, ...)`, numba o subproceso escribe en
   stderr y no rompe el protocolo. fd 0 queda en /dev/null (`input()` no roba mensajes).
2. Copia la caché de numba de la máquina (/opt/numba_listo → $NUMBA_CACHE_DIR),
   calienta NUESTRO motor (calentamiento fijo, igual para todos los bots; no corre
   nada del alumno) y manda `hola`. Todo esto pasa fuera de cualquier reloj.
3. Al recibir `preparar`: importa `strategy.py` (dentro del tiempo de `preparar`),
   llama `preparar(config)` y responde `listo`.
4. En cada `jugar`: llama `jugar(estado, tiempo_restante)`, convierte la respuesta
   con `str()` y la manda junto con lo que el bot pasó a `reportar(...)`.
5. Con `fin`: responde `adios` con la memoria pico (informativa) y termina.

Si el código del alumno lanza una excepción, se imprime el traceback en stderr y
el runner sale con código 1 (el árbitro lo cuenta como `error`).

Este módulo solo usa la biblioteca estándar y `arbitro.protocolo`: corre en la
imagen de bots, que no tiene el SDK de Docker.
"""

from __future__ import annotations

import importlib.util
import os
import resource
import shutil
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path

from arbitro import protocolo

CACHE_LISTA = Path("/opt/numba_listo")


@dataclass(frozen=True)
class Config:
    """Lo que recibe `preparar(config)`: `config.color`, `config.semilla`, ..."""

    color: str
    semilla: int
    carpeta_datos: Path
    reloj_s: float


class Canal:
    """Protocolo en descriptores propios, separados de stdin/stdout del alumno."""

    def __init__(self) -> None:
        self._entrada = os.dup(0)  # descriptores nuevos: ≥ 3 y no heredables
        self._salida = os.dup(1)
        nulo = os.open(os.devnull, os.O_RDONLY)
        os.dup2(nulo, 0)
        os.close(nulo)
        os.dup2(2, 1)  # todo lo que vaya a fd 1 termina en stderr
        sys.stdout.reconfigure(line_buffering=True)
        self._lector = protocolo.LectorLineas(self._entrada)

    def recibir(self) -> dict:
        linea = self._lector.leer()
        if linea is None:
            _salir("El árbitro cerró la conexión.", 1)
        return protocolo.decodificar(linea)

    def enviar(self, mensaje: dict) -> None:
        try:
            datos = protocolo.codificar(mensaje)
        except (TypeError, ValueError):  # incluye MensajeInvalido (pasa de 64 KB)
            datos = self._sin_extras(mensaje)
        vista = memoryview(datos)
        while vista:
            vista = vista[os.write(self._salida, vista) :]

    @staticmethod
    def _sin_extras(mensaje: dict) -> bytes:
        """Jugada que no se pudo codificar: sin `info` y con el texto recortado."""
        if mensaje.get("info") is not None:
            print(
                "[runner] Lo que pasaste a reportar(...) no se pudo enviar "
                "(pasa de 64 KB o no es convertible a JSON): se ignoró.",
                file=sys.stderr,
            )
        texto = str(mensaje.get("jugada"))
        if len(texto) > 200:  # ninguna jugada legal es tan larga: el árbitro la rechaza
            texto = texto[:200] + "..."
        return protocolo.codificar({**mensaje, "info": None, "jugada": texto})


def _salir(texto: str, codigo: int) -> None:
    if texto:
        print(texto, file=sys.stderr)
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.flush()
        except (OSError, ValueError):
            pass
    os._exit(codigo)  # sin esperar hilos del alumno


def copiar_cache_numba(origen: Path = CACHE_LISTA) -> None:
    """Copia la caché de numba de la máquina a NUMBA_CACHE_DIR (si hay algo que copiar).

    Solo copia contenido (sin permisos ni fechas): la raíz del tmpfs es de root.
    """
    destino = os.environ.get("NUMBA_CACHE_DIR")
    if not destino or not origen.is_dir():
        return
    try:
        for carpeta, _, archivos in os.walk(origen):
            nueva = Path(destino) / Path(carpeta).relative_to(origen)
            nueva.mkdir(parents=True, exist_ok=True)
            for nombre in archivos:
                shutil.copyfile(Path(carpeta) / nombre, nueva / nombre)
    except OSError as e:  # sin caché solo se compila más lento
        print(f"[runner] No se pudo copiar la caché de numba: {e}", file=sys.stderr)


def calentar_motor() -> None:
    """Carga (o compila) los kernels de numba del motor con un calentamiento fijo.

    Es igual para todos y no corre código del alumno: así nadie paga en su reloj la
    carga del motor que le damos (p. ej. `random` en su primera jugada).
    """
    from motor import Estado, simular_al_azar

    estado = Estado.inicial()
    estado.siguiente(estado.jugadas()[0])
    simular_al_azar(estado, 1, 0, "blancas")


def memoria_pico_mb() -> float:
    """Memoria máxima residente del runner y de sus subprocesos, en MB."""
    pico = max(
        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
    )
    return pico / (1024 * 1024) if sys.platform == "darwin" else pico / 1024


def cargar_estrategia(carpeta: Path):
    """Importa `strategy.py` de la carpeta del bot (cuenta dentro de `preparar`)."""
    archivo = carpeta / "strategy.py"
    if not archivo.is_file():
        _salir(f"No encontré {archivo}. Tu carpeta debe tener strategy.py.", 1)
    sys.path.insert(0, str(carpeta))  # para que importe sus otros módulos
    spec = importlib.util.spec_from_file_location("strategy", archivo)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["strategy"] = modulo
    spec.loader.exec_module(modulo)
    if not callable(getattr(modulo, "jugar", None)):
        _salir("Tu strategy.py no define la función jugar(estado, tiempo_restante).", 1)
    return modulo


def _fallo_del_alumno(donde: str) -> None:
    print(f"\n[runner] Tu bot lanzó una excepción en {donde}:", file=sys.stderr)
    traceback.print_exc()
    _salir(f"[runner] Pierdes esta partida por error en {donde}.", 1)


def main(argv: list[str]) -> None:
    if len(argv) != 2:
        _salir("Uso: python -m arbitro.runner <carpeta_del_bot>", 2)
    carpeta = Path(argv[1]).resolve()
    canal = Canal()
    copiar_cache_numba()
    calentar_motor()
    os.chdir(carpeta)
    canal.enviar(protocolo.hola())

    # --- preparar (el árbitro ya corre el reloj de preparar) ---------------------------
    mensaje = canal.recibir()
    if mensaje["tipo"] == "fin":  # el rival perdió antes de que preparáramos
        canal.enviar(protocolo.adios(memoria_pico_mb()))
        _salir("", 0)
    if mensaje["tipo"] != "preparar":
        _salir(f"[runner] Esperaba 'preparar' y llegó {mensaje['tipo']!r}.", 1)
    datos = mensaje["config"]
    config = Config(
        color=datos["color"],
        semilla=datos["semilla"],
        carpeta_datos=carpeta / datos["carpeta_datos"],
        reloj_s=datos["reloj_s"],
    )
    from motor import Estado, tomar_reporte  # ya importado por calentar_motor

    try:
        estrategia = cargar_estrategia(carpeta)
        if callable(getattr(estrategia, "preparar", None)):
            estrategia.preparar(config)
    except BaseException:
        _fallo_del_alumno("preparar (o al importar strategy.py)")
    canal.enviar(protocolo.listo())

    # --- partida -----------------------------------------------------------------------
    n = 0
    while True:
        mensaje = canal.recibir()
        if mensaje["tipo"] == "fin":
            canal.enviar(protocolo.adios(memoria_pico_mb()))
            _salir("", 0)
        n += 1
        estado = Estado.desde_dict(mensaje["estado"])
        tomar_reporte()  # descarta reportes viejos
        try:
            respuesta = estrategia.jugar(estado, mensaje["tiempo_restante"])
            texto = str(respuesta)
        except BaseException:
            _fallo_del_alumno(f"jugar (jugada {n})")
        info = tomar_reporte()
        canal.enviar(protocolo.jugada(texto, info))


if __name__ == "__main__":
    main(sys.argv)
