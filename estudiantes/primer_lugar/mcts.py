"""Monte Carlo Tree Search con las hojas evaluadas por la tabla V (CONTEXTO.MD §4 y §6).

Lo usan `strategy.py` (en la liga, la tabla es de solo lectura) y los workers de
`herramientas/entrenamiento.py` (escriben cada expansión en la tabla compartida). Vive en la raíz
del equipo porque el código de la liga no puede importar `herramientas/`. Los valores van
siempre desde quien tiene el turno (negamax).

- Expansión: todos los s' de todas las jugadas, con `estado.siguiente(j)`. Cada s' vale
  V(ŝ'_rival) de la tabla (0 si la partida terminó: el ±1000 ya viene en R), así que cada jugada
  tiene su Q(s, a) = Σ P(s'|s,a)·[R(s, s') − γ·valor(s')] y el nodo vale max_a Q: es el respaldo
  de Bellman de CONTEXTO §6.
- Selección: UCT entre las jugadas. En un ataque se baja a cada resultado en proporción a su
  probabilidad; los dos cuentan en Q con su esperanza exacta.
- Retropropagación: en cada ancestro se recalcula el Q de la jugada recorrida y el máximo.
- Jugada elegida: la de mayor Q.
"""

import math

import abstraccion
import specs

# Constante de UCT sobre Q normalizado por la recompensa de victoria (Q / 1000).
EXPLORACION = math.sqrt(2)


def calcular_esperanza_bellman(transiciones, gamma: float) -> float:
    """Valor esperado de una jugada desde la perspectiva de quien la hace (negamax).

        Σ P(s'|s,a) · [ R(s,s') − γ · V(ŝ'_rival) ]

    `transiciones`: ternas (probabilidad, recompensa, valor del rival), una por cada tablero de
    `estado.siguiente(j)`. El valor del rival se resta porque V siempre mide desde el jugador en
    turno, y en s' le toca al rival. Si s' termina la partida no hay futuro: quien llama pasa
    valor del rival 0.
    """
    total_prob = 0.0
    esperanza = 0.0
    for prob, recompensa, valor_rival in transiciones:
        total_prob += prob
        esperanza += prob * (recompensa - gamma * valor_rival)
    if abs(total_prob - 1.0) > 1e-9:
        raise ValueError(f"las probabilidades suman {total_prob}, no 1")
    return esperanza


class Nodo:
    """Un tablero. `valor`: V de la tabla mientras es hoja; max_a Q al expandirlo."""

    __slots__ = ("estado", "resumen", "terminal", "valor", "jugadas", "visitas")

    def __init__(self, estado, resumen, terminal: bool, valor: float) -> None:
        self.estado = estado
        self.resumen = resumen
        self.terminal = terminal
        self.valor = valor
        self.jugadas: list[Rama] | None = None  # None mientras no se expande
        self.visitas = 0


class Rama:
    """Una jugada legal: sus resultados (probabilidad, recompensa, hijo) y su Q."""

    __slots__ = ("jugada", "resultados", "q", "visitas")

    def __init__(self, jugada, resultados: list[tuple[float, int, Nodo]], gamma: float) -> None:
        self.jugada = jugada
        self.resultados = resultados
        self.visitas = 0
        self.actualizar(gamma)

    def actualizar(self, gamma: float) -> None:
        self.q = calcular_esperanza_bellman(
            [(p, recompensa, hijo.valor) for p, recompensa, hijo in self.resultados], gamma
        )


def elegir_resultado(rama: Rama) -> Nodo:
    """El resultado con menos visitas en proporción a su probabilidad (con empate, el primero)."""
    return max(rama.resultados, key=lambda r: r[0] / (r[2].visitas + 1))[2]


class MCTS:
    """Búsqueda sobre `tabla` (V, indexada con abstraccion.indice).

    `al_expandir(nodo)` se llama después de cada expansión, con `nodo.valor` ya en max_a Q:
    el entrenamiento lo usa para escribir V(ŝ) en la tabla compartida.
    """

    def __init__(self, tabla, gamma: float, al_expandir=None) -> None:
        self.tabla = tabla
        self.gamma = gamma
        self.al_expandir = al_expandir

    def nodo(self, estado, resumen=None, mueve=None) -> Nodo:
        """Hoja de `estado`. `mueve`: quien jugó para llegar aquí (para saber si terminó)."""
        if resumen is None:
            resumen = abstraccion.resumir(estado)
        quien = resumen.turno if mueve is None else mueve
        if abstraccion.resultado(resumen, quien) != specs.SIGUE:
            return Nodo(estado, resumen, True, 0.0)
        return Nodo(estado, resumen, False, float(self.tabla[abstraccion.indice(resumen)]))

    def buscar(self, raiz: Nodo, iteraciones: int) -> Rama:
        """Corre `iteraciones` iteraciones desde `raiz` y regresa la jugada de mayor Q."""
        if raiz.terminal:
            raise ValueError("la partida ya terminó: no hay jugadas")
        for _ in range(iteraciones):
            self._iterar(raiz)
        return max(raiz.jugadas, key=lambda r: (r.q, r.visitas))

    def _iterar(self, raiz: Nodo) -> None:
        camino = []
        nodo = raiz
        while nodo.jugadas is not None:
            rama = self._elegir_rama(nodo)
            camino.append((nodo, rama))
            nodo = elegir_resultado(rama)
        if not nodo.terminal:
            self._expandir(nodo)
        nodo.visitas += 1
        for padre, rama in reversed(camino):
            rama.actualizar(self.gamma)
            rama.visitas += 1
            padre.valor = max(r.q for r in padre.jugadas)
            padre.visitas += 1

    def _elegir_rama(self, nodo: Nodo) -> Rama:
        log_visitas = math.log(nodo.visitas + 1)
        return max(
            nodo.jugadas,
            key=lambda r: r.q / specs.R_VICTORIA
            + EXPLORACION * math.sqrt(log_visitas / (r.visitas + 1)),
        )

    def _expandir(self, nodo: Nodo) -> None:
        mueve = nodo.resumen.turno
        nodo.jugadas = []
        for jugada in nodo.estado.jugadas():
            resultados = []
            for p, siguiente in nodo.estado.siguiente(jugada):
                resumen = abstraccion.resumir(siguiente)
                hijo = self.nodo(siguiente, resumen, mueve)
                resultados.append((p, abstraccion.recompensa(nodo.resumen, resumen), hijo))
            nodo.jugadas.append(Rama(jugada, resultados, self.gamma))
        nodo.valor = max(r.q for r in nodo.jugadas)
        if self.al_expandir is not None:
            self.al_expandir(nodo)
