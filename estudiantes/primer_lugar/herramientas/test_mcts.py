"""Pruebas de mcts.py: expansión = respaldo de Bellman negamax, selección y elección de jugada.

Valores esperados calculados a mano; las recompensas son las de test_abstraccion.py.
"""

import numpy as np
from motor import Estado

import mcts
import specs

GAMMA = 0.95


def estado(blancas, negras, turno="blancas", puntos=None):
    d = {"blancas": blancas, "negras": negras, "turno": turno}
    if puntos is not None:
        d["puntos"] = puntos
    return Estado.desde_dict(d)


def tabla_llena(valor):
    return np.full(specs.NUM_ESTADOS, valor, dtype=np.float32)


def rama(nodo, texto):
    return next(r for r in nodo.jugadas if str(r.jugada) == texto)


def expandir(e, tabla, al_expandir=None):
    """Raíz de `e` expandida (la primera iteración del MCTS solo expande la raíz)."""
    busqueda = mcts.MCTS(tabla, GAMMA, al_expandir)
    raiz = busqueda.nodo(e)
    busqueda.buscar(raiz, iteraciones=1)
    return raiz


class TestExpansionEsRespaldoDeBellman:
    def test_ejemplo_3_con_tabla_en_cero(self):
        # Q(e4-f5) = 0.65·(14 − γ·0) + 0.35·(−20 − γ·0) = 9.1 − 7 = 2.1
        raiz = expandir(estado(["e4", "d3", "f3"], ["f5", "g6"]), tabla_llena(0.0))
        assert np.isclose(rama(raiz, "e4-f5").q, 2.1)
        assert raiz.valor == max(r.q for r in raiz.jugadas)

    def test_resta_el_valor_del_rival(self):
        # Todas las celdas en 10 (desde el rival): 0.65·(14 − 9.5) + 0.35·(−20 − 9.5) = −7.4
        raiz = expandir(estado(["e4", "d3", "f3"], ["f5", "g6"]), tabla_llena(10.0))
        assert np.isclose(rama(raiz, "e4-f5").q, -7.4)

    def test_un_tablero_terminal_no_lee_la_tabla(self):
        # Comer el último peón negro termina la partida: vale +1000 sin futuro (no 1000 − γ·500).
        # Si pierde, sigue la partida: −21 − 0.95·500. Q = 0.5·1000 + 0.5·(−496) = 252.
        raiz = expandir(estado(["e4"], ["f5"]), tabla_llena(500.0))
        assert np.isclose(rama(raiz, "e4-f5").q, 252.0)

    def test_avisa_cada_expansion_con_su_valor(self):
        avisos = []
        raiz = expandir(
            estado(["e4", "d3", "f3"], ["f5", "g6"]),
            tabla_llena(0.0),
            al_expandir=lambda nodo: avisos.append((nodo, nodo.valor)),
        )
        assert avisos == [(raiz, raiz.valor)]


class TestBusqueda:
    def test_cuenta_las_iteraciones(self):
        avisos = []
        busqueda = mcts.MCTS(tabla_llena(0.0), GAMMA, al_expandir=avisos.append)
        raiz = busqueda.nodo(Estado.inicial())
        busqueda.buscar(raiz, iteraciones=25)
        assert raiz.visitas == 25
        # La primera iteración expande la raíz; cada una de las demás baja por una jugada.
        assert sum(r.visitas for r in raiz.jugadas) == 24
        assert 1 < len(avisos) <= 25

    def test_encuentra_el_tercer_punto(self):
        # Blancas con 2 puntos y un peón en e8: anotar (e8-d9, e8-e9 o e8-f9) gana ya, con
        # Q = 1000. Con la tabla en −1000 cualquier otra jugada vale a lo más R + 950 < 1000.
        e = estado(["e8", "a2"], ["i9"], puntos={"blancas": 2, "negras": 0})
        for valor in (0.0, -1000.0, 1000.0):
            busqueda = mcts.MCTS(tabla_llena(valor), GAMMA)
            elegida = busqueda.buscar(busqueda.nodo(e), iteraciones=30)
            assert str(elegida.jugada) in {"e8-d9", "e8-e9", "e8-f9"}, valor

    def test_los_resultados_de_un_ataque_se_visitan_en_proporcion_a_p(self):
        raiz = expandir(estado(["e4", "d3", "f3"], ["f5", "g6"]), tabla_llena(0.0))
        ataque = rama(raiz, "e4-f5")  # p = 0.65 gana, 0.35 pierde
        for _ in range(20):
            mcts.elegir_resultado(ataque).visitas += 1
        assert [hijo.visitas for _, _, hijo in ataque.resultados] == [13, 7]
