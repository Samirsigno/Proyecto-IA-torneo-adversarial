"""Pruebas del bot UCT: la fórmula, el conteo del árbol, el dado, la perspectiva y el reloj."""

import math
import random
import time
from pathlib import Path

from motor import Estado

import strategy
from strategy import EXPLORACION, Nodo, Rama, buscar, elegir_resultado, ucb1


class Config:
    color, semilla, reloj_s = "blancas", 1, 30.0
    carpeta_datos = Path(__file__).resolve().parent.parent / "data"


def anota_o_pierde(turno):
    """Los dos llevan 2 puntos y un peón a una casilla de anotar el tercero: quien tiene el turno
    gana si anota ya; si no, el rival anota y gana en su turno."""
    return Estado.desde_dict(
        {"blancas": ["e8", "a1", "b1"], "negras": ["e2", "a9", "b9"], "turno": turno,
         "puntos": {"blancas": 2, "negras": 2}}
    )  # fmt: skip


ANOTA = {"blancas": {"e8-d9", "e8-e9", "e8-f9"}, "negras": {"e2-d1", "e2-e1", "e2-f1"}}


class TestUCB1:
    def test_formula(self):
        rama = Rama(Estado.inicial(), Estado.inicial().jugadas()[0])
        rama.visitas, rama.ganadas = 4, 3.0
        esperado = 0.75 + EXPLORACION * math.sqrt(math.log(10) / 4)
        assert math.isclose(ucb1(rama, math.log(10)), esperado)


class TestArbol:
    def test_las_visitas_cuadran(self):
        raiz = buscar(Estado.inicial(), random.Random(1), iteraciones=200)
        assert raiz.visitas == 200
        assert sum(r.visitas for r in raiz.ramas) == 200
        for rama in raiz.ramas:  # lo que entra a una jugada baja a alguno de sus resultados
            assert rama.visitas == sum(h.visitas for h in rama.hijos if h is not None)

    def test_prueba_cada_jugada_antes_de_repetir(self):
        e = Estado.inicial()
        raiz = buscar(e, random.Random(2), iteraciones=len(e.jugadas()))
        assert sorted(str(r.jugada) for r in raiz.ramas) == sorted(str(j) for j in e.jugadas())
        assert all(r.visitas == 1 for r in raiz.ramas)

    def test_los_resultados_de_un_ataque_salen_con_su_probabilidad(self):
        e = Estado.desde_dict(
            {"blancas": ["e4", "d3", "f3"], "negras": ["f5", "g6"], "turno": "blancas"}
        )
        rama = Rama(e, next(j for j in e.jugadas() if str(j) == "e4-f5"))  # p = 0.65
        dado = random.Random(3)
        gana = sum(elegir_resultado(rama, dado) == 0 for _ in range(4000))
        assert 2500 <= gana <= 2700  # esperado 2600 (±3.3 desviaciones estándar)

    def test_un_nodo_terminal_no_se_expande(self):
        nodo = Nodo(Estado.desde_dict({"blancas": ["a1"], "negras": [], "turno": "negras"}),
                    random.Random(4))  # fmt: skip
        assert nodo.terminal and nodo.pendientes == []


class TestPerspectiva:
    def test_cada_color_anota_antes_de_que_anote_el_rival(self):
        for semilla, turno in enumerate(("blancas", "negras")):
            raiz = buscar(anota_o_pierde(turno), random.Random(semilla), iteraciones=300)
            assert str(max(raiz.ramas, key=lambda r: r.visitas).jugada) in ANOTA[turno]


class TestJugar:
    def test_regresa_una_jugada_legal_dentro_de_su_presupuesto(self):
        strategy.preparar(Config())
        e = Estado.inicial()
        inicio = time.perf_counter()
        jugada = strategy.jugar(e, 30.0)
        assert jugada in e.jugadas()
        assert time.perf_counter() - inicio < (30.0 - strategy.reserva) / 25 + 0.5

    def test_sin_tiempo_contesta_al_instante(self):
        strategy.preparar(Config())
        e = Estado.inicial()
        inicio = time.perf_counter()
        assert strategy.jugar(e, strategy.reserva) in e.jugadas()
        assert time.perf_counter() - inicio < 0.2
