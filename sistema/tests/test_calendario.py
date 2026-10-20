"""Calendario de la liga y reparto en shards."""

from collections import Counter

import pytest

from liga.calendario import PartidaProgramada, generar_calendario, repartir


def test_calendario_4_por_pareja_colores_balanceados():
    cal = generar_calendario(["c", "a", "b"])
    assert len(cal) == 12
    parejas = {p.pareja for p in cal}
    assert parejas == {0, 1, 2}
    for pareja in parejas:
        partidas = [p for p in cal if p.pareja == pareja]
        assert len(partidas) == 4
        equipos = {p.blancas for p in partidas} | {p.negras for p in partidas}
        assert len(equipos) == 2
        # Cada equipo juega 2 veces con cada color y cada juego de dados con ambos colores.
        assert Counter(p.blancas for p in partidas) == Counter({e: 2 for e in equipos})
        assert Counter(p.juego for p in partidas) == Counter({0: 2, 1: 2})
        for juego in (0, 1):
            del_juego = [p for p in partidas if p.juego == juego]
            assert {p.blancas for p in del_juego} == equipos


def test_calendario_ordena_alfabeticamente_y_en_orden_fijo():
    cal = generar_calendario(["b", "a"], juegos_dados=2)
    assert cal == [
        PartidaProgramada(0, 0, "a", "b"),
        PartidaProgramada(0, 0, "b", "a"),
        PartidaProgramada(0, 1, "a", "b"),
        PartidaProgramada(0, 1, "b", "a"),
    ]
    # El orden de entrada no cambia el calendario.
    assert generar_calendario(["x", "a", "m"]) == generar_calendario(["m", "x", "a"])


def test_calendario_un_juego_de_dados():
    cal = generar_calendario(["a", "b", "c", "d"], juegos_dados=1)
    assert len(cal) == 6 * 2


def test_calendario_rechaza_repetidos():
    with pytest.raises(ValueError, match="repetidos"):
        generar_calendario(["a", "b", "a"])


def test_repartir_mantiene_parejas_juntas():
    cal = generar_calendario([f"e{i:02d}" for i in range(7)])  # 21 parejas
    trozos = [repartir(cal, s, 4) for s in range(4)]
    # Todo el calendario, sin repetir.
    assert sum(len(t) for t in trozos) == len(cal)
    assert {p for t in trozos for p in t} == set(cal)
    for t in trozos:
        for pareja in {p.pareja for p in t}:
            assert sum(1 for p in t if p.pareja == pareja) == 4
    # Ninguna pareja aparece en dos shards.
    vistos = [frozenset(p.pareja for p in t) for t in trozos]
    assert sum(len(v) for v in vistos) == 21
    # Reparto parejo: 21 parejas en 4 shards → 6, 5, 5, 5.
    assert sorted(len(v) for v in vistos) == [5, 5, 5, 6]


def test_repartir_shard_invalido():
    cal = generar_calendario(["a", "b"])
    with pytest.raises(ValueError, match="Shard"):
        repartir(cal, 4, 4)
    with pytest.raises(ValueError, match="Shard"):
        repartir(cal, 0, 0)
