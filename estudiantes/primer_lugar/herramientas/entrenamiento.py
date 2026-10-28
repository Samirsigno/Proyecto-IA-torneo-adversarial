"""PASO 3: entrenamiento offline de la tabla de valor V(ŝ) con Asynchronous Value Iteration.

Por ahora solo las funciones puras (tabla inicial, ecuación de Bellman negamax y fusión de
tablas). El bucle de los workers en memoria compartida va después. Ver CONTEXTO.MD §4 y §6.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # specs.py vive en la raíz

import specs  # noqa: E402

TIPO_VALOR = np.float32

# Faros de convergencia: las dos tuplas extremas, ancladas en ±1000 al iniciar.
# x1 y x2 son el avance máximo de cada bando (CONTEXTO.MD §5): 8 es lo más avanzado.
TUPLA_VICTORIA = (specs.NIVELES_AVANCE - 1, 0, specs.material_a_indice(18), specs.APOYO_MAX)
TUPLA_DERROTA = (0, specs.NIVELES_AVANCE - 1, specs.material_a_indice(-18), 0)


def inicializar_tabla() -> np.ndarray:
    """Tabla V de NUM_ESTADOS celdas float32 en 0, con los faros de victoria y derrota."""
    tabla = np.zeros(specs.NUM_ESTADOS, dtype=TIPO_VALOR)
    tabla[specs.estado_a_indice(*TUPLA_VICTORIA)] = specs.R_VICTORIA
    tabla[specs.estado_a_indice(*TUPLA_DERROTA)] = -specs.R_VICTORIA
    return tabla


def calcular_esperanza_bellman(transiciones, gamma: float) -> float:
    """Valor esperado de una jugada desde la perspectiva de quien la hace (negamax).

        Σ P(s'|s,a) · [ R(s,s') − γ · V(ŝ'_rival) ]

    `transiciones`: pares de resultados (probabilidad, recompensa, valor del rival), uno por
    cada tablero de `estado.siguiente(j)`. El valor del rival se resta porque V siempre mide
    desde el jugador en turno, y en s' le toca al rival. Si s' termina la partida no hay
    futuro: quien llama pasa valor del rival 0.
    """
    total_prob = 0.0
    esperanza = 0.0
    for prob, recompensa, valor_rival in transiciones:
        total_prob += prob
        esperanza += prob * (recompensa - gamma * valor_rival)
    if abs(total_prob - 1.0) > 1e-9:
        raise ValueError(f"las probabilidades suman {total_prob}, no 1")
    return esperanza


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
