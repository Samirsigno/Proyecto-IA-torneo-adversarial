"""Tests de los dados y las semillas."""

import pytest

from arbitro.azar import Dados, semilla_bots, semilla_de_color


def test_dados_deterministas_por_color():
    a, b = Dados(1, 0, 0), Dados(1, 0, 0)
    assert [a.tirar("blancas") for _ in range(5)] == [b.tirar("blancas") for _ in range(5)]
    assert Dados(1, 0, 0).tirar("blancas") != Dados(1, 0, 0).tirar("negras")


def test_dados_independientes_entre_colores():
    # Tirar con negras no cambia la secuencia de blancas.
    a, b = Dados(7, 3, 1), Dados(7, 3, 1)
    for _ in range(3):
        b.tirar("negras")
    assert [a.tirar("blancas") for _ in range(4)] == [b.tirar("blancas") for _ in range(4)]


def test_dados_cambian_con_pareja_y_juego():
    base = Dados(1, 0, 0).tirar("blancas")
    assert Dados(1, 1, 0).tirar("blancas") != base
    assert Dados(1, 0, 1).tirar("blancas") != base
    assert Dados(2, 0, 0).tirar("blancas") != base


def test_dados_en_rango():
    d = Dados(5, 0, 0)
    assert all(0.0 <= d.tirar("negras") < 1.0 for _ in range(1000))


def test_color_desconocido():
    with pytest.raises(ValueError, match="blancas"):
        Dados(1, 0, 0).tirar("rojas")


def test_semilla_bots_derivada_y_distinta():
    s = semilla_bots(1, 0, 0)
    assert s == semilla_bots(1, 0, 0)
    assert s != semilla_bots(1, 0, 1)
    assert semilla_de_color(s, "blancas") != semilla_de_color(s, "negras")
    assert 0 <= semilla_de_color(s, "blancas") < 2**63
