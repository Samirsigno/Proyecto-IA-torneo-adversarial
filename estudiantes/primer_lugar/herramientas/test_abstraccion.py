"""Pruebas de abstraccion.py: del tablero real del motor a la tupla ŝ y a la recompensa R(s, s').

Los valores esperados están calculados a mano sobre los ejemplos de docs/reglas.md. Las pruebas
de simetría y de fin de partida recorren partidas al azar y se comparan con el motor oficial.
"""

import random

from motor import Estado

import abstraccion
import specs
from specs import GANA, PIERDE, SIGUE


def estado(blancas, negras, turno="blancas", puntos=None):
    d = {"blancas": blancas, "negras": negras, "turno": turno}
    if puntos is not None:
        d["puntos"] = puntos
    return Estado.desde_dict(d)


def espejo(e: Estado) -> Estado:
    """El mismo tablero con los colores cambiados: la fila f pasa a 10 − f y se invierte el turno."""

    def voltear(casillas):
        return [c[0] + str(10 - int(c[1])) for c in casillas]

    return Estado.desde_dict(
        {
            "blancas": voltear(e.piezas("negras")),
            "negras": voltear(e.piezas("blancas")),
            "turno": "negras" if e.turno == "blancas" else "blancas",
            "puntos": {"blancas": e.puntos["negras"], "negras": e.puntos["blancas"]},
        }
    )


def tupla(e: Estado):
    return abstraccion.tupla(abstraccion.resumir(e))


def recompensa(e: Estado, jugada: str, gana_ataque=None):
    hijo = e.aplicar(jugada, gana_ataque=gana_ataque)
    return abstraccion.recompensa(abstraccion.resumir(e), abstraccion.resumir(hijo))


def transiciones_al_azar(partidas: int, semilla: int):
    """(estado, hijo) de cada jugada de partidas al azar desde la posición inicial."""
    rng = random.Random(semilla)
    for _ in range(partidas):
        e = Estado.inicial()
        while not e.terminado():
            (p, gana), *pierde = e.siguiente(rng.choice(e.jugadas()))
            hijo = gana if not pierde or rng.random() < p else pierde[0][1]
            yield e, hijo
            e = hijo


class TestTuplaAbstracta:
    def test_posicion_inicial(self):
        # Avance = filas recorridas desde la fila de fondo (0) hacia la final (8): la vanguardia
        # de cada color está en su segunda fila → 1.
        # Vanguardia a2, b2, c2 (desempate por columna): apoyos 1, 2, 2 → 5/3 ≈ 1.67 → 2.
        assert tupla(Estado.inicial()) == (1, 1, specs.material_a_indice(0), 2)
        assert abstraccion.indice(abstraccion.resumir(Estado.inicial())) == specs.estado_a_indice(
            1, 1, 18, 2
        )

    def test_ejemplo_3_combate(self):
        # Blancas e4, d3, f3 contra Negras f5, g6. Vanguardia blanca e4, d3, f3: apoyos 2, 0, 0
        # → 2/3 → 1. Avance blanco: e4 recorrió 3 filas; negro: f5 recorrió 4 (de la 9 a la 5).
        e = estado(["e4", "d3", "f3"], ["f5", "g6"])
        assert tupla(e) == (3, 4, specs.material_a_indice(1), 1)

    def test_avance_cuenta_filas_desde_el_fondo(self):
        # Un peón en la fila final anota y sale, así que en el tablero el avance llega a 7.
        assert tupla(estado(["e8"], [])) == (7, 0, specs.material_a_indice(1), 0)
        # La fila de fondo vale 0, igual que no tener peones.
        assert tupla(estado(["a1"], ["i9"])) == (0, 0, specs.material_a_indice(0), 0)

    def test_soporte_redondea_medios_hacia_arriba(self):
        # Vanguardia de 2 peones: e4 (apoyo 1, por d3) y d3 (apoyo 0) → 0.5 → 1.
        e = estado(["e4", "d3"], ["a9"])
        assert tupla(e) == (3, 0, specs.material_a_indice(1), 1)

    def test_perspectiva_de_quien_tiene_el_turno(self):
        # Mismo tablero, le toca a Negras: x1 es ahora el avance negro.
        e = estado(["e4", "d3", "f3"], ["f5", "g6"], turno="negras")
        # Vanguardia negra f5 (apoyo 1, por g6) y g6 (apoyo 0) → 0.5 → 1.
        assert tupla(e) == (4, 3, specs.material_a_indice(-1), 1)

    def test_espejo_da_la_misma_tupla(self):
        for e, _ in transiciones_al_azar(partidas=10, semilla=1):
            assert tupla(e) == tupla(espejo(e)), e.dibujar()


class TestRecompensa:
    def test_ejemplo_3_ataque_gana(self):
        # +1 de material (+15), soporte 1 → 0 (−3: f5 queda sin apoyo), avance 3 → 4 (+2).
        e = estado(["e4", "d3", "f3"], ["f5", "g6"])
        assert recompensa(e, "e4-f5", gana_ataque=True) == 15 - 3 + 2

    def test_ejemplo_3_ataque_pierde(self):
        # −1 de material (−15), soporte 1 → 0 (−3), avance 3 → 2 (−2).
        e = estado(["e4", "d3", "f3"], ["f5", "g6"])
        assert recompensa(e, "e4-f5", gana_ataque=False) == -15 - 3 - 2

    def test_anotar_caminando(self):
        # +1 punto (+300); el peón que sale no cuenta como pieza perdida. El avance máximo baja
        # de 7 (e8) a 1 (a2): −6 filas × 2 = −12.
        e = estado(["e8", "a2"], ["i9"])
        assert recompensa(e, "e8-e9") == 300 - 12

    def test_tercer_punto_gana(self):
        e = estado(["e8", "a2"], ["i9"], puntos={"blancas": 2, "negras": 0})
        assert recompensa(e, "e8-e9") == specs.R_VICTORIA

    def test_comer_el_ultimo_peon_gana(self):
        e = estado(["e4"], ["f5"])
        assert recompensa(e, "e4-f5", gana_ataque=True) == specs.R_VICTORIA

    def test_perder_el_ultimo_peon_no_termina_la_partida(self):
        # Blancas se quedan sin peones, pero le toca a Negras, que sí tienen jugadas.
        # −1 de material (−15) y el avance baja de 3 a 0 (−6).
        e = estado(["e4"], ["f5"])
        assert recompensa(e, "e4-f5", gana_ataque=False) == -15 - 6

    def test_bloquear_un_peon_rival(self):
        # El peón negro de a3 queda sin jugadas: a2 ocupada y su única diagonal (b2) es propia.
        # +1 bloqueado (+5) y el avance blanco sube de 0 a 1 (+2).
        e = estado(["a1"], ["a3", "b2"])
        assert recompensa(e, "a1-a2") == 5 + 2

    def test_espejo_da_la_misma_recompensa(self):
        for e, hijo in transiciones_al_azar(partidas=10, semilla=2):
            directa = abstraccion.recompensa(abstraccion.resumir(e), abstraccion.resumir(hijo))
            reflejada = abstraccion.recompensa(
                abstraccion.resumir(espejo(e)), abstraccion.resumir(espejo(hijo))
            )
            assert directa == reflejada, e.dibujar()


class TestFinDePartida:
    def test_resultado_coincide_con_el_motor(self):
        vistos = set()
        for e, hijo in transiciones_al_azar(partidas=30, semilla=3):
            yo = 0 if e.turno == "blancas" else 1
            ganador = hijo.ganador()
            esperado = SIGUE if ganador is None else GANA if ganador == e.turno else PIERDE
            assert abstraccion.resultado(abstraccion.resumir(hijo), yo) == esperado, hijo.dibujar()
            vistos.add(esperado)
        assert GANA in vistos  # las partidas al azar sí llegaron a terminar
