"""Bot «mcts_uct»: Monte Carlo Tree Search con UCT (Upper Confidence bounds applied to Trees).

Copiado de «montecarlo» y cambiado de Monte Carlo plano a un árbol. Cada iteración:

1. Selección: desde la raíz, en cada tablero se baja por la jugada de mayor UCB1; si la jugada
   es un ataque, se tira el dado con su p real para saber a qué resultado bajar.
2. Expansión: en el primer tablero que tenga jugadas sin probar, se prueba una (al azar).
3. Simulación: desde el tablero al que se llegó, partidas al azar con `simular_al_azar`.
4. Retropropagación: cada jugada del camino suma la fracción que ganó quien la hizo.

Se juega la jugada con más visitas.
"""

import math
import random
import time

from motor import Estado, reportar, simular_al_azar

SIMULACIONES = 1  # partidas al azar por cada hoja
K_EXPLORACION = 1.0  # constante de UCB1 (se puede cambiar para explorar más o menos)
EXPLORACION = math.sqrt(2*K_EXPLORACION)  # constante c de UCB1
RESERVA = 0.3  # fracción del reloj que nunca gastamos pensando (la comunicación también cuesta)


class Nodo:
    """Un tablero del árbol: sus jugadas ya probadas (`ramas`) y las que faltan (`pendientes`)."""

    __slots__ = ("estado", "terminal", "pendientes", "ramas", "visitas")

    def __init__(self, estado, rng) -> None:
        self.estado = estado
        self.terminal = estado.terminado()
        self.pendientes = [] if self.terminal else list(estado.jugadas())
        rng.shuffle(self.pendientes)
        self.ramas: list[Rama] = []
        self.visitas = 0


class Rama:
    """Una jugada: sus resultados posibles y lo que ganó con ella quien la hizo."""

    __slots__ = ("jugada", "probs", "estados", "hijos", "visitas", "ganadas")

    def __init__(self, estado, jugada) -> None:
        self.jugada = jugada
        self.probs, self.estados = zip(*estado.siguiente(jugada), strict=True)
        self.hijos: list[Nodo | None] = [None] * len(self.probs)  # se crean al bajar por primera vez
        self.visitas = 0
        self.ganadas = 0.0


def ucb1(rama: Rama, log_visitas_padre: float) -> float:
    """Promedio de victorias más el bono de exploración: x̄ + c·√(ln N / n)."""
    return rama.ganadas / rama.visitas + EXPLORACION * math.sqrt(
        log_visitas_padre / rama.visitas
    )


def elegir_resultado(rama: Rama, rng) -> int:
    """Tira el dado de la jugada: 0 (gana el ataque, o la única salida) con probabilidad p."""
    return 0 if len(rama.probs) == 1 or rng.random() < rama.probs[0] else 1


def _bajar(rama: Rama, rng) -> Nodo:
    i = elegir_resultado(rama, rng)
    if rama.hijos[i] is None:
        rama.hijos[i] = Nodo(rama.estados[i], rng)
    return rama.hijos[i]


def _iterar(raiz: Nodo, rng) -> int:
    """Una iteración completa. Regresa la profundidad a la que llegó."""
    camino = []
    nodo = raiz
    while not nodo.terminal:
        if nodo.pendientes:  # expansión: una jugada nueva y de ahí a simular
            rama = Rama(nodo.estado, nodo.pendientes.pop())
            nodo.ramas.append(rama)
            camino.append((nodo, rama))
            nodo = _bajar(rama, rng)
            break
        log_visitas = math.log(nodo.visitas)
        rama = max(nodo.ramas, key=lambda r: ucb1(r, log_visitas))
        camino.append((nodo, rama))
        nodo = _bajar(rama, rng)

    # Simulación (si el tablero ya terminó, simular_al_azar regresa 1.0 o 0.0).
    blancas = simular_al_azar(nodo.estado, SIMULACIONES, rng.randrange(2**31), para="blancas")
    nodo.visitas += 1
    for padre, rama in camino:
        rama.visitas += 1
        rama.ganadas += blancas if padre.estado.turno == "blancas" else 1.0 - blancas
        padre.visitas += 1
    return len(camino)


def buscar(estado, rng, iteraciones=None, limite=None) -> Nodo:
    """Árbol UCT desde `estado`: hasta `iteraciones` o hasta que `time.perf_counter()` pase
    `limite` (con al menos una iteración). Regresa la raíz."""
    raiz = Nodo(estado, rng)
    global profundidad
    profundidad = 0
    hechas = 0
    while True:
        profundidad = max(profundidad, _iterar(raiz, rng))
        hechas += 1
        if iteraciones is not None and hechas >= iteraciones:
            break
        if limite is not None and time.perf_counter() >= limite:
            break
    return raiz


def preparar(config):
    global color, rng, reserva  # se guardan aquí para usarlos en cada llamada a jugar
    color = config.color
    rng = random.Random(config.semilla)
    reserva = RESERVA * config.reloj_s
    # Calentamos numba ahora (también un ataque): la primera vez tarda y aquí no gasta reloj.
    e = Estado.desde_dict({"blancas": ["e4", "d3", "f3"], "negras": ["f5", "g6"], "turno": "blancas"})
    for j in e.jugadas():
        e.siguiente(j)
    simular_al_azar(Estado.inicial(), 1, 0, para=color)


def jugar(estado, tiempo_restante):
    # 1. Presupuesto: una fracción fija del reloj que queda (sin tocar la reserva).
    disponible = tiempo_restante - reserva
    jugadas = estado.jugadas()

    # 2. Si una jugada gana la partida sin importar el dado, la tomamos.
    for j in jugadas:
        if all(hijo.ganador() == color for _, hijo in estado.siguiente(j)):
            return j
    if disponible <= 0:  # solo queda la reserva: no hay tiempo de pensar
        return rng.choice(jugadas)

    # 3. Árbol UCT hasta agotar el presupuesto de esta jugada.
    raiz = buscar(estado, rng, limite=time.perf_counter() + disponible / 25)

    # 4. La más visitada (la más robusta); con empate, la de mejor promedio.
    mejor = max(raiz.ramas, key=lambda r: (r.visitas, r.ganadas / r.visitas))
    reportar(nodos=raiz.visitas, prof=profundidad, eval=mejor.ganadas / mejor.visitas)
    return mejor.jugada
