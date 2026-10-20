"""Lo que comparten los comandos: rutas, equipos, Docker o local, la liga y la impresión."""

from __future__ import annotations

import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config
from arbitro.procesos import BotDocker, BotLocal, ProcesoBot
from cli import ErrorCLI, salida
from config import Limites, cargar_limites, es_reservado
from liga.calendario import PartidaProgramada, generar_calendario
from liga.ejecutar import ejecutar_liga
from liga.manifest import hash_carpeta
from liga.tabla import FilaTabla
from validador.reglas import PATRON_NOMBRE
from visor.generar import indice

ESTUDIANTES = config.RAIZ / "estudiantes"
REFERENCIAS = ("random", "montecarlo")  # rivales del mini torneo
NOMBRE_DOCKER = re.compile(r"^[a-z0-9_][a-z0-9_.-]{0,127}$")


def imprimir(*partes, **kw) -> None:
    kw.setdefault("flush", True)
    print(*partes, **kw)


# --- Rutas y equipos -----------------------------------------------------------------------
def carpeta_resultados() -> Path:
    return Path(os.environ.get("TORNEO_RESULTADOS") or config.RAIZ / "resultados")


def _huso() -> timezone | None:
    """Zona horaria del alumno (`TORNEO_HUSO`, p. ej. «-0600», la exporta ./torneo)."""
    m = re.fullmatch(r"([+-])(\d\d)(\d\d)", os.environ.get("TORNEO_HUSO", ""))
    if not m:
        return None
    signo = 1 if m.group(1) == "+" else -1
    return timezone(signo * timedelta(hours=int(m.group(2)), minutes=int(m.group(3))))


def nueva_corrida() -> Path:
    """`resultados/<fecha_hora>/` nueva (con sufijo si ya existe una del mismo segundo)."""
    huso = _huso()
    ahora = datetime.now(huso) if huso else datetime.now()
    base = carpeta_resultados() / ahora.strftime("%Y-%m-%d_%H-%M-%S")
    carpeta, n = base, 1
    while True:
        try:
            carpeta.mkdir(parents=True)
            return carpeta
        except FileExistsError:
            n += 1
            carpeta = base.with_name(f"{base.name}-{n}")


def disponibles() -> list[str]:
    if not ESTUDIANTES.is_dir():
        return []
    return sorted(
        p.name for p in ESTUDIANTES.iterdir() if p.is_dir() and not p.name.startswith(".")
    )


def resolver_equipo(texto: str) -> tuple[str, Path]:
    """Nombre de equipo (carpeta de estudiantes/) o ruta a una carpeta → (nombre, carpeta)."""
    propia = ESTUDIANTES / texto
    if "/" not in texto and texto not in (".", "..") and propia.is_dir():
        return texto, propia.resolve()
    ruta = Path(texto)
    if "/" in texto and ruta.is_dir():
        ruta = ruta.resolve()
        return ruta.name, ruta
    raise ErrorCLI(
        f"No existe estudiantes/{texto}/. Equipos disponibles: "
        f"{', '.join(disponibles()) or 'ninguno'}."
    )


def es_del_curso(nombre: str) -> bool:
    """Participantes nuestros (random, montecarlo, tier_*): nombre reservado, pero válidos."""
    return nombre in REFERENCIAS or nombre.startswith("tier_")


def nombre_de_participante(nombre: str) -> bool:
    """Mismas reglas que el validador: formato válido y no reservado (salvo los del curso)."""
    return bool(PATRON_NOMBRE.fullmatch(nombre)) and (
        es_del_curso(nombre) or not es_reservado(nombre)
    )


def limites() -> Limites:
    try:
        return cargar_limites()
    except (OSError, ValueError) as e:
        raise ErrorCLI(f"No pude leer los límites: {e}") from None


def semilla_nueva() -> int:
    return secrets.randbelow(10**6)


# --- Docker o local ------------------------------------------------------------------------
class Entorno:
    """Crea los bots con Docker (oficial) o como subprocesos (`--sin-docker`)."""

    def __init__(self, sin_docker: bool) -> None:
        self.docker = not sin_docker
        self._cliente = None

    def cliente(self):
        if self._cliente is None:
            from cli import imagenes

            self._cliente = imagenes.cliente()
        return self._cliente

    def preparar(self, equipos: dict[str, Path]) -> None:
        """Deja todo listo antes de jugar: aviso, limpieza, caché de numba e imágenes."""
        if not self.docker:
            imprimir(salida.AVISO_SIN_DOCKER)
            return
        from cli import imagenes

        c = self.cliente()
        imagenes.limpiar_contenedores(c)
        imagenes.imagen_base(c)
        for nombre, carpeta in equipos.items():
            self._revisar_carpeta(nombre, carpeta)
        cache = carpeta_resultados() / ".cache"
        if not imagenes.cache_al_dia(c, cache):
            imagenes.calentar(c, cache, avisar=imprimir)
        for nombre, carpeta in equipos.items():
            imagenes.asegurar_imagen_equipo(c, nombre, carpeta, avisar=imprimir)

    @staticmethod
    def _revisar_carpeta(nombre: str, carpeta: Path) -> None:
        if not NOMBRE_DOCKER.fullmatch(nombre):
            raise ErrorCLI(
                f"El nombre de carpeta «{nombre}» no sirve: usa solo minúsculas sin acentos, "
                "dígitos y guion bajo (por ejemplo: los_alfa_beta)."
            )
        try:
            carpeta.resolve().relative_to(config.RAIZ)
        except ValueError:
            raise ErrorCLI(
                f"{carpeta} está fuera del repo. Con Docker, tu bot debe estar en "
                "estudiantes/<tu_equipo>/."
            ) from None

    def bot(self, nombre: str, carpeta: Path, publicos: Limites, nucleo=None) -> ProcesoBot:
        if self.docker:
            from cli.imagenes import imagen_equipo

            return BotDocker(carpeta, imagen_equipo(nombre), nucleo, publicos)
        return BotLocal(carpeta, publicos.salida_kb)


# --- Impresión ---------------------------------------------------------------------------------
def linea_limites(publicos: Limites, docker: bool) -> str:
    modo = "con Docker (límites del torneo)" if docker else "sin Docker"
    return (
        f"Reloj: {publicos.reloj_s:g} s por partida para cada bot · preparar: "
        f"{publicos.preparar_s:g} s · {modo}"
    )


def cierre(registros: list[dict], destino: Path, tabla: list | None = None) -> None:
    ruta = indice(registros, destino, tabla)
    imprimir(f"Repeticiones: {salida.ruta_visible(ruta)}  (ábrelo en tu navegador)")


def avisos_y_problemas(
    registros: list[dict], publicos: Limites, con_salida: bool = True, sin: tuple = ()
) -> None:
    lineas: list[str] = []
    for n, reg in enumerate(registros, 1):
        if any(reg["meta"][c] in sin for c in salida.COLORES):
            continue  # contra humano: sin avisos de reloj
        lineas += salida.problemas(n, reg, publicos, con_salida=con_salida)
        lineas += salida.avisos(n, reg, publicos.reloj_s)
    for linea in lineas:
        imprimir(linea)
    if any(linea.startswith("✗") for linea in lineas) and con_salida:
        imprimir("  (con -v ves cada jugada y todo lo que imprimió cada bot)")


def tabla_partidas(registros: list[dict], publicos: Limites, con_salida: bool) -> None:
    if not registros:
        return
    nombres = [r["meta"][c] for r in registros for c in salida.COLORES]
    tabla = salida.TablaPartidas(nombres, len(registros))
    imprimir("")
    imprimir(tabla.encabezado())
    for n, reg in enumerate(registros, 1):
        imprimir(tabla.fila(n, reg))
    avisos_y_problemas(registros, publicos, con_salida=con_salida)


LEYENDA_TABLA = (
    "SB = calidad de victorias (desempate) · Anotados = peones que llegaron a la meta · "
    "ver docs/calificacion.md"
)


def imprimir_tabla(titulo: str, tabla: list[FilaTabla]) -> None:
    imprimir("")
    imprimir(titulo)
    for linea in salida.tabla_liga(tabla):
        imprimir(f"  {linea}")
    imprimir(f"  {LEYENDA_TABLA}")
    imprimir("")


# --- Liga ------------------------------------------------------------------------------------
def simultaneas() -> int:
    """Partidas a la vez: `TORNEO_SIMULTANEAS` o la mitad de los núcleos (la liga ajusta)."""
    texto = os.environ.get("TORNEO_SIMULTANEAS", "")
    if texto.isdigit() and int(texto) > 0:
        return int(texto)
    return max(1, (os.cpu_count() or 1) // 2)


def jugar_liga(
    participantes: dict[str, Path],
    juegos: int,
    semilla: int,
    destino: Path,
    entorno: Entorno,
    publicos: Limites,
    calendario: list[PartidaProgramada] | None = None,
    shard: tuple[int, int] | None = None,
) -> list[dict]:
    """Juega el calendario (todos contra todos si no se da) y regresa los registros.

    `participantes` son TODOS los de la liga (aunque el calendario sea un shard).
    """
    completo = generar_calendario(sorted(participantes), juegos)
    calendario = completo if calendario is None else calendario
    parejas = len({p.pareja for p in calendario})
    imprimir(
        f"Jugando {len(calendario)} partidas ({parejas} pareja{'s' if parejas != 1 else ''}, "
        f"{juegos} juego{'s' if juegos != 1 else ''} de dados por pareja) · semilla {semilla}"
    )
    imprimir(linea_limites(publicos, entorno.docker))
    return ejecutar_liga(
        calendario,
        lambda equipo, nucleo: entorno.bot(equipo, participantes[equipo], publicos, nucleo),
        publicos,
        publicos.efectivos(),
        semilla,
        simultaneas(),
        destino,
        hashes={e: hash_carpeta(c) for e, c in participantes.items()},
        avisar=lambda texto: imprimir(f"  · {texto}"),
        completo=completo,
        shard=shard,
    )
