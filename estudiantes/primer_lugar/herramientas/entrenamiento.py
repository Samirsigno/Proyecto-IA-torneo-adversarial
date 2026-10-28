"""PASO 3: entrenamiento offline de la tabla de valor V(ŝ) con workers en paralelo.

Cada worker juega partidas contra sí mismo desde la posición inicial. En cada turno corre el
MCTS de `mcts.py` (ITERACIONES por jugada) y cada tablero que el MCTS expande recibe su
respaldo de Bellman negamax, asignado directo en la tabla (CONTEXTO.MD §6):

    V(ŝ) ← max_a Σ P(s'|s,a) · [ R(s, s') − γ · V(ŝ'_rival) ]

La jugada que se ejecuta sigue otra política (off-policy, como en Q-learning): con probabilidad
EPSILON una jugada legal al azar y si no la de mayor Q. Esa elección solo decide a qué tablero
se avanza; lo que se escribe en la tabla es siempre el max_a de la expansión. Además, PROB_CAOS
de las partidas empiezan en un tablero aleatorio en vez de la posición inicial, para llegar a
celdas que el juego normal casi no visita.

La tabla vive en `multiprocessing.shared_memory` (float32, NUM_ESTADOS celdas; CONTEXTO.MD §4):
todos los workers leen y escriben el mismo buffer, sin copias ni candados, así que cada uno usa
al instante lo que escriben los demás. Escribir un float32 alineado es atómico: si dos workers
escriben la misma celda a la vez, queda uno de los dos valores.

El proceso principal reporta el avance, guarda la tabla cada pocos minutos y al terminar
(Ctrl+C, `docker stop` o --horas), y si se vuelve a correr reanuda desde lo guardado.

Uso, con el Docker del torneo, desde la raíz del repo:

    estudiantes/primer_lugar/herramientas/entrenar.sh                  # hasta Ctrl+C
    estudiantes/primer_lugar/herramientas/entrenar.sh --horas 8

Salida: herramientas/tablas/<etiqueta>.npy (la tabla V) y <etiqueta>.json (contadores).
"""

import argparse
import json
import math
import multiprocessing as mp
import os
import random
import re
import signal
import sys
import time
from datetime import datetime
from multiprocessing import shared_memory
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # specs.py vive en la raíz

import abstraccion  # noqa: E402
import mcts  # noqa: E402
import specs  # noqa: E402
from mcts import calcular_esperanza_bellman  # noqa: E402, F401 (vive en la raíz: la usa la liga)
from motor import Estado  # noqa: E402

GAMMA = 0.95
ITERACIONES = 200  # iteraciones del MCTS por jugada
EPSILON = 0.1  # probabilidad de ejecutar una jugada legal al azar (exploración)
PROB_CAOS = 0.05  # probabilidad de empezar una partida en un tablero aleatorio
TIPO_VALOR = np.float32

# Una celda visitada nunca guarda 0.0: `fusionar_arreglos` lo leería como «no explorada».
MINIMO_EXPLORADO = np.finfo(TIPO_VALOR).tiny

CARPETA_TABLAS = Path(__file__).resolve().parent / "tablas"

# Columnas de los contadores compartidos: una fila por worker, y cada uno escribe solo la suya.
RESPALDOS, PARTIDAS, LISTO = 0, 1, 2

# Faros de convergencia: las dos tuplas extremas, ancladas en ±1000 al iniciar. Son solo el
# valor inicial (V es un valor esperado; el ±1000 de verdad lo da R). x1 y x2 son el avance
# máximo (CONTEXTO.MD §5): 8 es la fila final, donde el peón anota y sale.
TUPLA_VICTORIA = (specs.NIVELES_AVANCE - 1, 0, specs.material_a_indice(18), specs.APOYO_MAX)
TUPLA_DERROTA = (0, specs.NIVELES_AVANCE - 1, specs.material_a_indice(-18), 0)


# --- Funciones puras ---------------------------------------------------------------------


def inicializar_tabla() -> np.ndarray:
    """Tabla V de NUM_ESTADOS celdas float32 en 0, con los faros de victoria y derrota."""
    tabla = np.zeros(specs.NUM_ESTADOS, dtype=TIPO_VALOR)
    tabla[specs.estado_a_indice(*TUPLA_VICTORIA)] = specs.R_VICTORIA
    tabla[specs.estado_a_indice(*TUPLA_DERROTA)] = -specs.R_VICTORIA
    return tabla


def fusionar_arreglos(*tablas: np.ndarray) -> np.ndarray:
    """Fusiona tablas V entrenadas por separado (en otras computadoras), celda por celda.

    Un 0 significa «estado no explorado» y no cuenta: cada celda es el promedio de las tablas
    donde no es 0, y queda en 0 si ninguna la exploró.
    """
    if len({t.shape for t in tablas}) != 1:
        raise ValueError(f"las tablas tienen tamaños distintos: {[t.shape for t in tablas]}")
    suma = np.zeros(tablas[0].shape, dtype=np.float64)
    exploradas = np.zeros(tablas[0].shape, dtype=np.int64)
    for tabla in tablas:
        suma += tabla
        exploradas += tabla != 0
    fusion = np.divide(suma, exploradas, out=np.zeros_like(suma), where=exploradas > 0)
    return fusion.astype(TIPO_VALOR)


def escribir_valor(tabla: np.ndarray, indice: int, valor: float) -> None:
    """V(ŝ) ← valor. Un 0.0 (también el que sale al pasar a float32) se guarda como
    MINIMO_EXPLORADO, para que la celda siga contando como explorada."""
    valor = TIPO_VALOR(valor)
    tabla[indice] = valor if valor != 0 else MINIMO_EXPLORADO


def celdas_exploradas(tabla: np.ndarray) -> int:
    """Celdas que ya escribió el entrenamiento (distintas de `inicializar_tabla`)."""
    return int(np.count_nonzero(tabla != inicializar_tabla()))


def generar_tablero_aleatorio(dado=random) -> Estado:
    """Tablero válido pero caótico: de 2 a 18 peones por bando en casillas al azar.

    Ningún peón en la fila donde anotaría (Blancas fuera de la 9, Negras fuera de la 1), turno
    al azar y 0 a 0 en puntos. Nunca es terminal: un bando con algún peón siempre tiene jugada.
    """
    casillas = [col + fila for fila in "123456789" for col in "abcdefghi"]
    blancas = dado.sample([c for c in casillas if c[1] != "9"], dado.randint(2, 18))
    ocupadas = set(blancas)
    libres = [c for c in casillas if c[1] != "1" and c not in ocupadas]
    negras = dado.sample(libres, dado.randint(2, 18))
    turno = dado.choice(("blancas", "negras"))
    return Estado.desde_dict({"blancas": blancas, "negras": negras, "turno": turno})


def tablero_de_inicio(dado, prob_caos: float) -> Estado:
    """Posición con la que empieza una partida: aleatoria con probabilidad `prob_caos`."""
    return generar_tablero_aleatorio(dado) if dado.random() < prob_caos else Estado.inicial()


def elegir_rama(raiz, mejor, dado, epsilon: float):
    """Jugada que se ejecuta (ε-greedy): una legal al azar con probabilidad `epsilon`, si no
    `mejor`. No escribe nada: la tabla ya se actualizó con max_a al expandir `raiz`."""
    return dado.choice(raiz.jugadas) if dado.random() < epsilon else mejor


def jugar_turno(busqueda, raiz, dado, iteraciones: int, epsilon: float):
    """Un turno del worker: búsqueda (que escribe V con max_a), jugada ε-greedy y dado.

    Regresa el tablero siguiente, con su subárbol para reusarlo.
    """
    mejor = busqueda.buscar(raiz, iteraciones)
    return _tirar_dado(elegir_rama(raiz, mejor, dado, epsilon), dado)


# --- Memoria compartida ------------------------------------------------------------------


class Memoria:
    """La tabla V (float32) y los contadores de los workers (int64) en `shared_memory`.

    El proceso principal la crea con `crear` y la libera con `liberar`; cada worker se conecta
    por nombre con `abrir` y la suelta con `cerrar`. Nadie copia la tabla.
    """

    def __init__(self, bloques, trabajadores: int) -> None:
        self._bloques = bloques
        self.tabla = np.ndarray((specs.NUM_ESTADOS,), dtype=TIPO_VALOR, buffer=bloques[0].buf)
        self.contadores = np.ndarray((trabajadores, 3), dtype=np.int64, buffer=bloques[1].buf)

    @classmethod
    def crear(cls, trabajadores: int) -> "Memoria":
        tamanos = (specs.NUM_ESTADOS * np.dtype(TIPO_VALOR).itemsize, trabajadores * 3 * 8)
        memoria = cls(
            [shared_memory.SharedMemory(create=True, size=t) for t in tamanos], trabajadores
        )
        memoria.contadores[:] = 0
        return memoria

    @classmethod
    def abrir(cls, nombres, trabajadores: int) -> "Memoria":
        return cls([shared_memory.SharedMemory(name=n) for n in nombres], trabajadores)

    @property
    def nombres(self) -> tuple[str, str]:
        return tuple(b.name for b in self._bloques)

    def cerrar(self) -> None:
        self.tabla = self.contadores = None  # sin vistas vivas, el buffer se puede cerrar
        for bloque in self._bloques:
            bloque.close()

    def liberar(self) -> None:
        self.cerrar()
        for bloque in self._bloques:
            bloque.unlink()


# --- Workers -----------------------------------------------------------------------------


def _trabajar(numero, nombres, trabajadores, semilla, juego, partidas, parar) -> None:
    """Proceso worker: conecta la memoria compartida y juega hasta que se lo pidan.

    `juego`: (iteraciones, epsilon, prob_caos).
    """
    signal.signal(signal.SIGINT, signal.SIG_IGN)  # Ctrl+C lo atiende el proceso principal
    memoria = Memoria.abrir(nombres, trabajadores)
    _jugar(memoria, numero, random.Random(semilla), *juego, partidas, parar)
    memoria.cerrar()


def _jugar(memoria, numero, dado, iteraciones, epsilon, prob_caos, partidas, parar) -> None:
    """Partidas contra sí mismo hasta que `parar` se active o se cumplan `partidas`."""
    contadores = memoria.contadores

    def al_expandir(nodo):
        escribir_valor(memoria.tabla, abstraccion.indice(nodo.resumen), nodo.valor)
        contadores[numero, RESPALDOS] += 1

    busqueda = mcts.MCTS(memoria.tabla, GAMMA, al_expandir)
    contadores[numero, LISTO] = 1
    while not parar.is_set() and (partidas is None or contadores[numero, PARTIDAS] < partidas):
        raiz = busqueda.nodo(tablero_de_inicio(dado, prob_caos))
        while not raiz.terminal and not parar.is_set():
            raiz = jugar_turno(busqueda, raiz, dado, iteraciones, epsilon)
        if raiz.terminal:
            contadores[numero, PARTIDAS] += 1


def _tirar_dado(rama: mcts.Rama, dado: random.Random) -> mcts.Nodo:
    """Resultado de la jugada: un ataque gana (el primer resultado) con probabilidad p."""
    (p, _, gana), *pierde = rama.resultados
    return gana if not pierde or dado.random() < p else pierde[0][2]


# --- Proceso principal -------------------------------------------------------------------


def _guardar(salida: Path, tabla: np.ndarray, meta: dict) -> None:
    """Escribe la tabla (.npy) y sus contadores (.json) sin dejar nunca un archivo a medias."""
    salida.parent.mkdir(parents=True, exist_ok=True)
    temporal = salida.with_name(salida.name + ".tmp")
    with open(temporal, "wb") as archivo:
        np.save(archivo, tabla)
    os.replace(temporal, salida)
    temporal.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    os.replace(temporal, salida.with_suffix(".json"))


def _cargar(salida: Path) -> tuple[np.ndarray, dict]:
    tabla = np.load(salida)
    if tabla.shape != (specs.NUM_ESTADOS,) or tabla.dtype != TIPO_VALOR:
        raise ValueError(
            f"{salida}: se esperaba float32[{specs.NUM_ESTADOS}], hay {tabla.dtype}{tabla.shape}"
        )
    contadores = salida.with_suffix(".json")
    meta = json.loads(contadores.read_text()) if contadores.exists() else {}
    return tabla, meta


def _horas(segundos: float) -> str:
    minutos, s = divmod(int(segundos), 60)
    return f"{minutos // 60:d}:{minutos % 60:02d}:{s:02d}"


def entrenar(
    salida: Path,
    trabajadores: int,
    iteraciones: int = ITERACIONES,
    *,
    epsilon: float = EPSILON,
    prob_caos: float = PROB_CAOS,
    horas: float | None = None,
    partidas_por_trabajador: int | None = None,
    guardar_cada_s: float = 300.0,
    reportar_cada_s: float = 60.0,
    desde_cero: bool = False,
    semilla: int | None = None,
) -> dict:
    """Entrena con `trabajadores` procesos sobre una sola tabla compartida.

    Guarda la tabla en `salida` (.npy) y sus contadores en el .json de al lado; si ya existen
    (y no se pide `desde_cero`), continúa desde ahí. Termina con Ctrl+C / SIGTERM, al cumplir
    `horas` de entrenamiento o cuando cada worker juega `partidas_por_trabajador`. Regresa los
    contadores guardados.
    """
    salida = Path(salida)
    tabla_inicial, previo = inicializar_tabla(), {}
    if salida.exists() and not desde_cero:
        tabla_inicial, previo = _cargar(salida)
        print(f"Reanudando {salida}: {previo.get('partidas', 0):,} partidas previas.", flush=True)
    abstraccion.resumir(Estado.inicial())  # compila numba aquí (caché) y no en cada worker

    contexto = mp.get_context("spawn")
    parar = contexto.Event()
    memoria = Memoria.crear(trabajadores)
    detener = []  # señales recibidas: el bucle principal las revisa
    anteriores = {
        s: signal.signal(s, lambda numero, _marco: detener.append(numero))
        for s in (signal.SIGINT, signal.SIGTERM)
    }
    procesos = []
    segundos = 0.0

    def contadores() -> dict:
        return {
            "partidas": previo.get("partidas", 0) + int(memoria.contadores[:, PARTIDAS].sum()),
            "respaldos": previo.get("respaldos", 0) + int(memoria.contadores[:, RESPALDOS].sum()),
            "segundos": round(previo.get("segundos", 0.0) + segundos, 1),
            "gamma": GAMMA,
            "iteraciones": iteraciones,
            "epsilon": epsilon,
            "prob_caos": prob_caos,
            "trabajadores": trabajadores,
            "actualizado": datetime.now().astimezone().isoformat(timespec="seconds"),
        }

    try:
        memoria.tabla[:] = tabla_inicial
        for numero, hijo in enumerate(np.random.SeedSequence(semilla).spawn(trabajadores)):
            semilla_dado = int(hijo.generate_state(1, np.uint64)[0])
            juego = (iteraciones, epsilon, prob_caos)
            args = (numero, memoria.nombres, trabajadores, semilla_dado, juego,
                    partidas_por_trabajador, parar)  # fmt: skip
            procesos.append(contexto.Process(target=_trabajar, args=args, name=f"worker-{numero}"))
            procesos[-1].start()

        # El reloj de --horas corre desde que todos los workers están listos (importar tarda).
        while not detener and not memoria.contadores[:, LISTO].all():
            if not all(p.is_alive() for p in procesos):
                break
            time.sleep(0.05)
        inicio = time.monotonic()
        fin = inicio + horas * 3600 if horas is not None else math.inf
        proximo_reporte, proximo_guardado = inicio + reportar_cada_s, inicio + guardar_cada_s
        anterior = memoria.tabla.copy()
        # El ritmo se mide desde los respaldos ya hechos (los de corridas anteriores incluidos).
        respaldos_anteriores, momento_anterior = previo.get("respaldos", 0), inicio
        avisados = set()

        while not detener and any(p.is_alive() for p in procesos):
            time.sleep(0.2)
            ahora = time.monotonic()
            segundos = ahora - inicio
            for p in procesos:
                if p.exitcode not in (None, 0) and p.name not in avisados:
                    avisados.add(p.name)
                    print(f"⚠ {p.name} terminó con error (código {p.exitcode}).", flush=True)
            if ahora >= fin:
                break
            if ahora >= proximo_reporte:
                proximo_reporte += reportar_cada_s
                actual = memoria.tabla.copy()
                exploradas = actual != inicializar_tabla()
                cambio = np.abs(actual - anterior)[exploradas].mean() if exploradas.any() else 0.0
                c = contadores()
                ritmo = (c["respaldos"] - respaldos_anteriores) / (ahora - momento_anterior)
                print(
                    f"[{_horas(c['segundos'])}] partidas {c['partidas']:,} · respaldos "
                    f"{c['respaldos']:,} ({ritmo:,.0f}/s) · celdas exploradas "
                    f"{int(exploradas.sum()):,}/{specs.NUM_ESTADOS:,} · cambio medio {cambio:.3f}",
                    flush=True,
                )
                anterior, respaldos_anteriores, momento_anterior = actual, c["respaldos"], ahora
            if ahora >= proximo_guardado:
                proximo_guardado += guardar_cada_s
                _guardar(salida, memoria.tabla.copy(), contadores())
        if detener:
            print("Deteniendo: esperando a los workers y guardando...", flush=True)
    finally:
        parar.set()
        for p in procesos:
            p.join(timeout=30)
            if p.is_alive():
                p.terminate()
                p.join()
        meta = contadores()
        _guardar(salida, memoria.tabla.copy(), meta)
        memoria.liberar()
        for s, manejador in anteriores.items():
            signal.signal(s, manejador)

    print(
        f"Guardado {salida}: {meta['partidas']:,} partidas, {meta['respaldos']:,} respaldos, "
        f"{_horas(meta['segundos'])} de entrenamiento.",
        flush=True,
    )
    fallidos = [p.name for p in procesos if p.exitcode != 0]
    if fallidos:
        raise RuntimeError(f"workers con error: {', '.join(fallidos)} (la tabla sí se guardó)")
    return meta


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        description="Entrena la tabla V con workers en paralelo sobre memoria compartida."
    )
    parser.add_argument(
        "--etiqueta",
        default=os.environ.get("ENTRENAMIENTO_ETIQUETA", "local"),
        help="nombre de la tabla: herramientas/tablas/<etiqueta>.npy (por omisión, tu usuario)",
    )
    parser.add_argument("--workers", type=int, default=os.cpu_count(), help="procesos (núcleos)")
    parser.add_argument("--horas", type=float, help="detenerse después de H horas (si no, Ctrl+C)")
    parser.add_argument("--iteraciones", type=int, default=ITERACIONES, help="del MCTS por jugada")
    parser.add_argument(
        "--epsilon", type=float, default=EPSILON, help="probabilidad de jugar una jugada al azar"
    )
    parser.add_argument(
        "--caos", type=float, default=PROB_CAOS, help="fracción de partidas desde un tablero al azar"
    )
    parser.add_argument("--guardar-cada", type=float, default=5.0, help="minutos entre guardados")
    parser.add_argument("--desde-cero", action="store_true", help="ignorar la tabla guardada")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.etiqueta):
        parser.error(f"etiqueta inválida: {args.etiqueta!r} (letras, dígitos, _ . -)")
    for nombre in ("epsilon", "caos"):
        if not 0.0 <= getattr(args, nombre) <= 1.0:
            parser.error(f"--{nombre} debe estar entre 0 y 1")

    salida = CARPETA_TABLAS / f"{args.etiqueta}.npy"
    print(
        f"Entrenando con {args.workers} workers · {args.iteraciones} iteraciones de MCTS por "
        f"jugada · γ = {GAMMA} · ε = {args.epsilon:g} · caos {args.caos:.0%}\n"
        f"Tabla: {salida} (se guarda cada {args.guardar_cada:g} min)\n"
        "Ctrl+C para detener: guarda antes de salir.",
        flush=True,
    )
    entrenar(
        salida,
        args.workers,
        args.iteraciones,
        epsilon=args.epsilon,
        prob_caos=args.caos,
        horas=args.horas,
        guardar_cada_s=args.guardar_cada * 60,
        desde_cero=args.desde_cero,
    )


if __name__ == "__main__":
    main()
