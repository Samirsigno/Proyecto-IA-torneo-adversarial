"""Puente entre el motor y specs.py: del tablero real a la tupla abstracta ŝ y a R(s, s').

`specs.py` traduce tupla → índice y deltas → recompensa; aquí se sacan la tupla y los deltas de
un `Estado` del motor. Lo importan `strategy.py` (en la liga) y `herramientas/` (offline): las
dos fases tienen que leer V en la misma celda. Vive en la raíz del equipo porque el código de la
liga no puede importar `herramientas/`. Ver CONTEXTO.MD, secciones 5 y 6.

Colores como en el motor: 0 = Blancas, 1 = Negras.
"""

from typing import NamedTuple

from motor.nucleo import LADO, VACIA, apoyo, paso
from numba import njit

import specs

VANGUARDIA = 3  # peones de vanguardia que promedian su apoyo (x4)


@njit(cache=True)
def rasgos(tablero, color):
    """(avance máximo, soporte de vanguardia, peones, peones bloqueados) de `color`.

    Avance de un peón: filas recorridas desde su fila de fondo (0) hacia la final (8). En la
    final el peón anota y sale, así que en el tablero llega a 7. Sin peones, el avance es 0.
    Vanguardia: los VANGUARDIA peones más avanzados, con empates por columna (a → i); su soporte
    es el promedio de sus apoyos, redondeado con los .5 hacia arriba (con menos peones, el
    promedio de los que haya; sin peones, 0).
    Bloqueado: sin jugadas legales (recto ocupado y cada diagonal fuera del tablero o propia).
    """
    pieza = color + 1
    adelante = paso(color) * LADO
    avance_max = 0
    peones = 0
    bloqueados = 0
    suma_apoyos = 0
    for avance in range(LADO - 1, -1, -1):  # de la fila más avanzada a la de fondo
        fila = avance if color == 0 else LADO - 1 - avance
        for col in range(LADO):
            casilla = fila * LADO + col
            if tablero[casilla] != pieza:
                continue
            if peones == 0:
                avance_max = avance
            if peones < VANGUARDIA:
                suma_apoyos += apoyo(tablero, casilla, color)
            peones += 1
            frente = casilla + adelante  # existe: ningún peón está en su fila final
            if (
                tablero[frente] != VACIA
                and (col == 0 or tablero[frente - 1] == pieza)
                and (col == LADO - 1 or tablero[frente + 1] == pieza)
            ):
                bloqueados += 1
    en_vanguardia = min(peones, VANGUARDIA)
    if en_vanguardia == 0:
        return avance_max, 0, peones, bloqueados
    # round(suma / n) con los .5 hacia arriba, en enteros.
    soporte = (2 * suma_apoyos + en_vanguardia) // (2 * en_vanguardia)
    return avance_max, soporte, peones, bloqueados


class Resumen(NamedTuple):
    """Lo que la tupla ŝ y R(s, s') necesitan de un tablero. Cada par va indexado por color."""

    turno: int
    puntos: tuple[int, int]
    avance: tuple[int, int]
    soporte: tuple[int, int]
    peones: tuple[int, int]
    bloqueados: tuple[int, int]


def resumir(estado) -> Resumen:
    """Resumen de un `Estado` del motor."""
    # El motor no expone su tablero de 81 casillas ni los puntos como arreglos: se leen sus
    # atributos internos (de solo lectura) en vez de pasar por los textos de `estado.piezas()`.
    tablero, puntos = estado._tablero, estado._puntos
    blancas, negras = rasgos(tablero, 0), rasgos(tablero, 1)
    return Resumen(estado._color, (int(puntos[0]), int(puntos[1])), *zip(blancas, negras))


def tupla(r: Resumen) -> tuple[int, int, int, int]:
    """ŝ = (x1, x2, x3 + 18, x4) desde quien tiene el turno, con x3 ya desplazado para specs."""
    yo, rival = r.turno, 1 - r.turno
    material = specs.material_a_indice(r.peones[yo] - r.peones[rival])
    return r.avance[yo], r.avance[rival], material, r.soporte[yo]


def indice(r: Resumen) -> int:
    """Celda de V que corresponde al tablero, desde quien tiene el turno."""
    return specs.estado_a_indice(*tupla(r))


def resultado(r: Resumen, color: int) -> int:
    """GANA, SIGUE o PIERDE para `color`: 3 puntos, o quien tiene el turno se quedó sin jugadas."""
    if r.puntos[color] >= specs.PUNTOS_PARA_GANAR:
        return specs.GANA
    if r.puntos[1 - color] >= specs.PUNTOS_PARA_GANAR:
        return specs.PIERDE
    if r.bloqueados[r.turno] == r.peones[r.turno]:  # todos bloqueados, o ninguno en el tablero
        return specs.PIERDE if r.turno == color else specs.GANA
    return specs.SIGUE


def recompensa(antes: Resumen, despues: Resumen) -> int:
    """R(s, s') para quien movió en `antes` (CONTEXTO §6).

    Puntos y material: cambio de la diferencia propia − rival. Bloqueos: cambio de los peones
    rivales sin jugadas. Soporte y avance: cambio de los propios.
    """
    yo, rival = antes.turno, 1 - antes.turno

    def diferencia(par):
        return par[yo] - par[rival]

    return specs.calcular_recompensa(
        delta_puntos=diferencia(despues.puntos) - diferencia(antes.puntos),
        delta_material=diferencia(despues.peones) - diferencia(antes.peones),
        delta_bloqueos=despues.bloqueados[rival] - antes.bloqueados[rival],
        delta_soporte=despues.soporte[yo] - antes.soporte[yo],
        delta_avance=despues.avance[yo] - antes.avance[yo],
        resultado=resultado(despues, yo),
    )
