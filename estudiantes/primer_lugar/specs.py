"""Especificación matemática del entorno: abstracción del estado, combate y recompensas.

Lo importan `strategy.py` (en la liga) y `herramientas/` (offline). Vive en la raíz del equipo
porque el código de la liga no puede importar `herramientas/`. Sin dependencias.
Ver CONTEXTO.MD, secciones 5 y 6.
"""

# --- Abstracción del estado -----------------------------------------------------------
# Tupla abstracta ŝ = (x1, x2, x3, x4):
#   x1, x2: avance máximo aliado y rival, avance máximo en casillas [0,8]
#   x3:     diferencial de material (−18 a 18); llega desplazado a x3 + 18 (0 a 36)
#   x4:     soporte de la vanguardia (0 a 2)
NIVELES_AVANCE = 9
NIVELES_MATERIAL = 37
NIVELES_SOPORTE = 3
DESPLAZAMIENTO_MATERIAL = 18

NUM_ESTADOS = NIVELES_AVANCE * NIVELES_AVANCE * NIVELES_MATERIAL * NIVELES_SOPORTE  # 8 991


def _validar(nombre: str, valor: int, minimo: int, maximo: int) -> None:
    if not minimo <= valor <= maximo:
        raise ValueError(f"{nombre} = {valor} fuera de [{minimo}, {maximo}]")


def material_a_indice(diferencial: int) -> int:
    """Diferencial de material (−18 a 18) → componente desplazada x3 + 18 (0 a 36)."""
    _validar("diferencial de material", diferencial, -DESPLAZAMIENTO_MATERIAL, DESPLAZAMIENTO_MATERIAL)
    return diferencial + DESPLAZAMIENTO_MATERIAL


def estado_a_indice(avance_aliado: int, avance_rival: int, material: int, soporte: int) -> int:
    """Tupla abstracta → índice 1D único en [0, NUM_ESTADOS).

    Suma polinomial de base mixta (9, 9, 37, 3), evaluada con la regla de Horner:
        i = ((x1·9 + x2)·37 + (x3 + 18))·3 + x4
    `material` ya viene desplazado (0 a 36): usar `material_a_indice` para convertirlo.
    Cada componente es menor que su base, así que el mapeo es biyectivo (`indice_a_estado`
    es la inversa). Fuera de rango lanza ValueError en vez de escribir en otra celda.
    """
    _validar("avance aliado", avance_aliado, 0, NIVELES_AVANCE - 1)
    _validar("avance rival", avance_rival, 0, NIVELES_AVANCE - 1)
    _validar("material desplazado", material, 0, NIVELES_MATERIAL - 1)
    _validar("soporte", soporte, 0, NIVELES_SOPORTE - 1)
    return (
        (avance_aliado * NIVELES_AVANCE + avance_rival) * NIVELES_MATERIAL + material
    ) * NIVELES_SOPORTE + soporte


def indice_a_estado(indice: int) -> tuple[int, int, int, int]:
    """Índice 1D → tupla abstracta (avance aliado, avance rival, material desplazado, soporte)."""
    _validar("índice", indice, 0, NUM_ESTADOS - 1)
    resto, soporte = divmod(indice, NIVELES_SOPORTE)
    resto, material = divmod(resto, NIVELES_MATERIAL)
    avance_aliado, avance_rival = divmod(resto, NIVELES_AVANCE)
    return avance_aliado, avance_rival, material, soporte


# --- Combate ---------------------------------------------------------------------------
APOYO_MAX = 2
P_MIN, P_MAX = 0.2, 0.9  # cotas de docs/reglas.md (con apoyos de 0 a 2 nunca se alcanzan)

# Con apoyos de 0 a 2 la diferencia solo toma 5 valores: la fórmula se evalúa una vez aquí.
# El redondeo a 2 decimales deja el flotante más cercano a 0.20, 0.35, ... (sin el error
# acumulado de 0.5 + 0.15·d). Índice: apoyo_atacante − apoyo_defensor + APOYO_MAX.
_P_POR_DIFERENCIA = tuple(
    round(min(max(0.5 + 0.15 * d, P_MIN), P_MAX), 2) for d in range(-APOYO_MAX, APOYO_MAX + 1)
)


def calcular_probabilidad_combate(apoyo_atacante: int, apoyo_defensor: int) -> float:
    """Probabilidad de que gane el atacante: p = 0.5 + 0.15·(apoyo_atacante − apoyo_defensor)."""
    _validar("apoyo del atacante", apoyo_atacante, 0, APOYO_MAX)
    _validar("apoyo del defensor", apoyo_defensor, 0, APOYO_MAX)
    return _P_POR_DIFERENCIA[apoyo_atacante - apoyo_defensor + APOYO_MAX]


# --- Recompensas R(s, s') ----------------------------------------------------------------
R_VICTORIA = 1000
R_PUNTO = 300
R_MATERIAL = 15
R_BLOQUEO = 5
R_SOPORTE = 3
R_AVANCE = 2

PUNTOS_PARA_GANAR = 3
GANA, SIGUE, PIERDE = 1, 0, -1


def calcular_recompensa(
    delta_puntos: int,
    delta_material: int,
    delta_bloqueos: int,
    delta_soporte: int = 0,
    delta_avance: int = 0,
    resultado: int = SIGUE,
) -> int:
    """Recompensa de una jugada, desde el punto de vista del jugador que la hizo.

    Primero se revisa si la partida terminó: ganar vale +1000 y perder −1000 en lugar de los
    demás términos (no se suman). Terminó si `resultado` es GANA o PIERDE (cualquier forma de
    ganar, también dejar al rival sin jugadas) o si |delta_puntos| ≥ 3: una jugada anota a lo
    más 1 punto, así que ±3 no es ambiguo y se lee como «ganó / perdió».

    Si la partida sigue, es la suma de los deltas por su peso. `delta_material` es el cambio
    real del diferencial en el tablero, que incluye a los peones que anotaron y salieron. Esa
    salida no es una pieza comida, así que no se penaliza: cada punto saca exactamente un peón,
    y se le devuelve al material. Anotar caminando (delta_puntos = +1, delta_material = −1) vale
    300; anotar ganando un ataque (+1, 0) vale 300 + 15 por la pieza comida.
    """
    if resultado not in (GANA, SIGUE, PIERDE):
        raise ValueError(f"resultado = {resultado} no es GANA (1), SIGUE (0) ni PIERDE (-1)")
    if resultado == GANA or delta_puntos >= PUNTOS_PARA_GANAR:
        return R_VICTORIA
    if resultado == PIERDE or delta_puntos <= -PUNTOS_PARA_GANAR:
        return -R_VICTORIA
    material_comido = delta_material + delta_puntos
    return (
        R_PUNTO * delta_puntos
        + R_MATERIAL * material_comido
        + R_BLOQUEO * delta_bloqueos
        + R_SOPORTE * delta_soporte
        + R_AVANCE * delta_avance
    )
