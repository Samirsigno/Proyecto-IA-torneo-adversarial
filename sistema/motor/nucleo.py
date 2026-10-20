"""Kernels numba con las reglas del juego (uso interno del motor).

Aquí vive la ÚNICA copia de las reglas. `Estado` y `simular_al_azar` las usan.

Representación:
- `tablero`: arreglo `int8[81]`; casilla = fila*9 + col (fila 0 = fila «1»).
  0 = vacía, 1 = peón blanco, 2 = peón negro.
- `color`: 0 = Blancas, 1 = Negras. La pieza de un color vale `color + 1`.
- `puntos`: arreglo `int64[2]` (Blancas, Negras).
"""

from __future__ import annotations

import numpy as np
from numba import njit

VACIA = 0
LADO = 9
CASILLAS = LADO * LADO
PEONES = 18
MAX_JUGADAS = PEONES * 3
PUNTOS_PARA_GANAR = 3
INTENTOS = 16  # reintentos del muestreo por rechazo en `simular`


@njit(cache=True)
def paso(color: int) -> int:
    """Dirección «adelante»: +1 fila para Blancas, −1 para Negras."""
    return 1 if color == 0 else -1


@njit(cache=True)
def generar(tablero, color, origenes, destinos) -> int:
    """Llena `origenes`/`destinos` con las jugadas legales y regresa cuántas son.

    Orden: casilla de origen creciente; por origen, diagonal izquierda,
    recto, diagonal derecha.
    """
    pieza = color + 1
    avance = paso(color) * LADO
    n = 0
    for c in range(CASILLAS):
        if tablero[c] != pieza:
            continue
        col = c % LADO
        frente = c + avance  # nunca sale del tablero: al llegar a la meta la pieza sale
        if col > 0 and tablero[frente - 1] != pieza:
            origenes[n] = c
            destinos[n] = frente - 1
            n += 1
        if tablero[frente] == VACIA:
            origenes[n] = c
            destinos[n] = frente
            n += 1
        if col < LADO - 1 and tablero[frente + 1] != pieza:
            origenes[n] = c
            destinos[n] = frente + 1
            n += 1
    return n


@njit(cache=True)
def apoyo(tablero, casilla, color) -> int:
    """Peones propios en las dos casillas diagonales de atrás de `casilla` (0, 1 o 2)."""
    fila = casilla // LADO - paso(color)
    if fila < 0 or fila >= LADO:
        return 0
    col = casilla % LADO
    pieza = color + 1
    total = 0
    if col > 0 and tablero[fila * LADO + col - 1] == pieza:
        total += 1
    if col < LADO - 1 and tablero[fila * LADO + col + 1] == pieza:
        total += 1
    return total


@njit(cache=True)
def prob_combate(apoyo_atacante, apoyo_defensor) -> float:
    """p = clip(0.5 + 0.15·(apoyo_atacante − apoyo_defensor), 0.2, 0.9)."""
    p = 0.5 + 0.15 * (apoyo_atacante - apoyo_defensor)
    return min(max(p, 0.2), 0.9)


@njit(cache=True)
def prob_jugada(tablero, color, origen, destino) -> float:
    """Probabilidad de que la jugada salga bien: p si es ataque, 1.0 si no."""
    if tablero[destino] == VACIA:
        return 1.0
    return prob_combate(apoyo(tablero, origen, color), apoyo(tablero, destino, 1 - color))


@njit(cache=True)
def aplicar(tablero, puntos, color, origen, destino, gana_ataque) -> None:
    """Aplica la jugada EN SITIO (no cambia el turno; eso lo hace quien llama)."""
    tablero[origen] = VACIA
    if tablero[destino] != VACIA:  # ataque
        if not gana_ataque:
            return  # sale el atacante; el defensor se queda
        tablero[destino] = VACIA
    meta = LADO - 1 if color == 0 else 0
    if destino // LADO == meta:
        puntos[color] += 1  # anota y la pieza sale del tablero
    else:
        tablero[destino] = color + 1


@njit(cache=True)
def clave(tablero, color, puntos, z_piezas, z_turno, z_puntos) -> np.uint64:
    """Hash Zobrist de 64 bits: piezas, turno y puntos."""
    h = np.uint64(0)
    for c in range(CASILLAS):
        if tablero[c] != VACIA:
            h ^= z_piezas[tablero[c] - 1, c]
    if color == 1:
        h ^= z_turno
    h ^= z_puntos[0, puntos[0]]
    h ^= z_puntos[1, puntos[1]]
    return h


@njit(cache=True)
def _quitar(lista, cuantos, indice, color, casilla) -> None:
    """Quita de la lista de peones de `color` el que está en `casilla`."""
    i = indice[casilla]
    ultimo = lista[color, cuantos[color] - 1]
    lista[color, i] = ultimo
    indice[ultimo] = i
    cuantos[color] -= 1


@njit(cache=True)
def simular(tablero, puntos, color, n, semilla, para) -> float:
    """Juega `n` partidas al azar y regresa la fracción que gana `para`.

    Jugadas uniformes entre las legales; cada ataque gana si u < p.
    Supone que la posición inicial no ha terminado por puntos.

    Para ir rápido, elige (peón, dirección) al azar y reintenta si no es legal
    (muestreo por rechazo: sigue siendo uniforme entre las jugadas legales).
    Tras INTENTOS fallidos genera todas las jugadas, lo cual también es uniforme.
    """
    np.random.seed(semilla)
    tab = np.empty(CASILLAS, np.int8)
    pts = np.empty(2, np.int64)
    origenes = np.empty(MAX_JUGADAS, np.int64)
    destinos = np.empty(MAX_JUGADAS, np.int64)
    lista = np.empty((2, CASILLAS), np.int64)  # casillas de los peones de cada color
    cuantos = np.empty(2, np.int64)
    indice = np.empty(CASILLAS, np.int64)  # posición de cada peón dentro de su lista
    victorias = 0
    for _ in range(n):
        tab[:] = tablero
        pts[:] = puntos
        cuantos[:] = 0
        for s in range(CASILLAS):
            if tab[s] != VACIA:
                k = tab[s] - 1
                lista[k, cuantos[k]] = s
                indice[s] = cuantos[k]
                cuantos[k] += 1
        c = color
        while True:
            pieza = c + 1
            avance = paso(c) * LADO
            o = -1
            d = -1
            for _intento in range(INTENTOS):
                if cuantos[c] == 0:
                    break
                prueba = lista[c, np.random.randint(0, cuantos[c])]
                giro = np.random.randint(-1, 2)
                col = prueba % LADO + giro
                if col < 0 or col >= LADO:
                    continue
                destino = prueba + avance + giro
                v = tab[destino]
                if v == pieza or (giro == 0 and v != VACIA):
                    continue
                o = prueba
                d = destino
                break
            if o < 0:
                m = generar(tab, c, origenes, destinos)
                if m == 0:
                    ganador = 1 - c  # sin jugadas: gana el otro
                    break
                k = np.random.randint(0, m)
                o = origenes[k]
                d = destinos[k]
            ataque = tab[d] != VACIA
            gana = True
            if ataque:
                gana = np.random.random() < prob_jugada(tab, c, o, d)
                if gana:
                    _quitar(lista, cuantos, indice, 1 - c, d)
                else:
                    _quitar(lista, cuantos, indice, c, o)
            if gana:
                meta = LADO - 1 if c == 0 else 0
                if d // LADO == meta:
                    _quitar(lista, cuantos, indice, c, o)
                else:
                    i = indice[o]
                    lista[c, i] = d
                    indice[d] = i
            aplicar(tab, pts, c, o, d, gana)
            if pts[c] >= PUNTOS_PARA_GANAR:
                ganador = c
                break
            c = 1 - c
        if ganador == para:
            victorias += 1
    return victorias / n


def _splitmix64(semilla: int, cuantos: int) -> np.ndarray:
    """Números de 64 bits fijos para siempre (no dependen de la versión de numpy)."""
    mascara = (1 << 64) - 1
    x = semilla
    salida = []
    for _ in range(cuantos):
        x = (x + 0x9E3779B97F4A7C15) & mascara
        z = x
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & mascara
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & mascara
        salida.append(z ^ (z >> 31))
    return np.array(salida, dtype=np.uint64)


_Z = _splitmix64(20261018, 2 * CASILLAS + 1 + 2 * (PUNTOS_PARA_GANAR + 1))
Z_PIEZAS = _Z[: 2 * CASILLAS].reshape(2, CASILLAS)
Z_TURNO = _Z[2 * CASILLAS]
Z_PUNTOS = _Z[2 * CASILLAS + 1 :].reshape(2, PUNTOS_PARA_GANAR + 1)
