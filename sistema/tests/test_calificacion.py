"""Calificación (docs/calificacion.md) con tablas sintéticas."""

import pytest

from config import cargar_calificacion
from liga.calificacion import calificar
from liga.tabla import FilaTabla, construir_tabla
from tests.test_tabla import reg

REFS = cargar_calificacion()


def tabla(*filas: tuple[str, int]) -> list[FilaTabla]:
    """Filas (equipo, puntos) en el orden dado (= posiciones tras desempates)."""
    return [
        FilaTabla(equipo=e, puntos=p, victorias=p, sb=0.0, anotados=0, posicion=i + 1, partidas=100)
        for i, (e, p) in enumerate(filas)
    ]


# Tres alumnos fuertes arriba para que los demás no queden en el top 3.
TOP = [("top1", 90), ("top2", 89), ("top3", 88)]
ALUMNOS_TOP = {"top1", "top2", "top3"}


def test_referencias_de_calificacion_toml():
    assert REFS == {
        "random": 1.0,
        "montecarlo": 3.0,
        "tier_1": 5.0,
        "tier_2": 6.0,
        "tier_3": 7.0,
        "tier_4": 8.5,
        "tier_5": 10.0,
    }


def test_ganarle_es_estrictamente_mas_puntos():
    # Mismos puntos que montecarlo (y el desempate lo pone arriba): NO le gana → 1.
    t = tabla(*TOP, ("ana", 20), ("montecarlo", 20), ("random", 5))
    notas = calificar(t, REFS, ALUMNOS_TOP | {"ana"})
    assert notas["ana"] == 1


def test_top3_es_10_aunque_no_supere_tiers():
    # Las referencias arriba no cuentan para el top 3 de alumnos.
    t = tabla(
        ("tier_2", 50),
        ("tier_1", 40),
        ("montecarlo", 30),
        ("ana", 10),
        ("beto", 9),
        ("caro", 9),
        ("dani", 9),
        ("random", 8),
    )
    notas = calificar(t, REFS, {"ana", "beto", "caro", "dani"})
    assert notas == {"ana": 10, "beto": 10, "caro": 10, "dani": 1}


def test_top3_con_empate_en_puntos_usa_posicion():
    # caro y dani empatan en puntos; el desempate puso a caro arriba: caro es 3.ª.
    t = tabla(("ana", 30), ("beto", 25), ("caro", 4), ("dani", 4), ("random", 3))
    notas = calificar(t, REFS, {"ana", "beto", "caro", "dani"})
    assert notas["caro"] == 10
    assert notas["dani"] == 1


def test_escalones():
    t = tabla(
        *TOP,
        ("tier_5", 60),
        ("tier_4", 55),
        ("tier_3", 50),
        ("ana", 45),  # le gana a tier_2 y no a tier_3 → 6
        ("tier_2", 40),
        ("beto", 36),  # tier_1 → 5
        ("tier_1", 35),
        ("montecarlo", 20),
        ("caro", 19),  # random → 1
        ("random", 5),
    )
    notas = calificar(t, REFS, ALUMNOS_TOP | {"ana", "beto", "caro"})
    assert (notas["ana"], notas["beto"], notas["caro"]) == (6, 5, 1)


def test_vale_el_mejor_bot_al_que_le_gana_aunque_pierda_con_uno_menor():
    # Más puntos que tier_1 pero no que montecarlo (posible por la variedad de rivales).
    t = tabla(*TOP, ("montecarlo", 40), ("ana", 30), ("tier_1", 29), ("random", 1))
    assert calificar(t, REFS, ALUMNOS_TOP | {"ana"})["ana"] == 5


def test_cero_si_no_supera_random():
    t = tabla(*TOP, ("random", 10), ("ana", 10), ("beto", 2))
    notas = calificar(t, REFS, ALUMNOS_TOP | {"ana", "beto"})
    assert (notas["ana"], notas["beto"]) == (0, 0)


def test_referencias_ausentes_se_ignoran():
    # Sin tiers en esta corrida: lo máximo es montecarlo.
    t = tabla(*TOP, ("ana", 50), ("montecarlo", 20), ("random", 5))
    assert calificar(t, REFS, ALUMNOS_TOP | {"ana"})["ana"] == 3


def test_solo_califica_alumnos():
    t = tabla(*TOP, ("montecarlo", 20), ("random", 5))
    assert set(calificar(t, REFS, ALUMNOS_TOP)) == ALUMNOS_TOP


def test_alumno_sin_fila_o_referencia_como_alumno_es_error():
    t = tabla(*TOP, ("random", 5))
    with pytest.raises(ValueError, match="nadie"):
        calificar(t, REFS, ALUMNOS_TOP | {"nadie"})
    with pytest.raises(ValueError, match="random"):
        calificar(t, REFS, ALUMNOS_TOP | {"random"})


def test_referencia_sin_partidas_no_cuenta_como_ganada():
    # tier_5 aparece con 0 partidas válidas (todas sus parejas excluidas): no se le «gana».
    t = tabla(*TOP, ("ana", 30), ("montecarlo", 20), ("random", 5), ("tier_5", 0))
    t[-1] = FilaTabla("tier_5", 0, 0, 0.0, 0, len(t), partidas=0)
    notas = calificar(t, REFS, ALUMNOS_TOP | {"ana"})
    assert notas["ana"] == 3


def test_no_calificables_juegan_pero_no_ocupan_top3():
    t = tabla(
        ("sin_informe", 50),
        ("ana", 40),
        ("beto", 30),
        ("caro", 20),
        ("dani", 10),
        ("montecarlo", 5),
        ("random", 1),
    )
    notas = calificar(
        t, REFS, {"ana", "beto", "caro", "dani", "sin_informe"}, no_calificables={"sin_informe"}
    )
    assert notas == {"ana": 10, "beto": 10, "caro": 10, "dani": 3}


def test_empate_de_tres_que_cruza_el_tercer_lugar():
    # beto, caro y dani empatan en puntos en los lugares 2–4 entre alumnos. El desempate
    # (posición) decide: beto y caro entran al top 3; dani no, aunque tenga los mismos puntos.
    t = tabla(
        ("ana", 40), ("beto", 20), ("caro", 20), ("dani", 20), ("montecarlo", 19), ("random", 1)
    )
    notas = calificar(t, REFS, {"ana", "beto", "caro", "dani"})
    assert notas == {"ana": 10, "beto": 10, "caro": 10, "dani": 3}
    # Si el empate está por debajo de una referencia con los mismos puntos, no le ganan.
    t = tabla(
        ("ana", 40),
        ("beto", 30),
        ("caro", 20),
        ("montecarlo", 20),
        ("dani", 20),
        ("eli", 20),
        ("random", 1),
    )
    notas = calificar(t, REFS, {"ana", "beto", "caro", "dani", "eli"})
    assert notas == {"ana": 10, "beto": 10, "caro": 10, "dani": 1, "eli": 1}


def test_empate_de_tres_en_el_tercer_lugar_desde_registros():
    # De punta a punta (registros → tabla → calificación). ana gana todo; beto, caro y dani
    # hacen un ciclo (1 punto cada uno, 1 entre ellos, SB 1): deciden los peones anotados.
    registros = [reg("ana", e) for e in ("beto", "caro", "dani")] + [
        reg("beto", "caro", 3, 2),
        reg("caro", "dani", 3, 1),
        reg("dani", "beto", 3, 0),
    ]
    t = construir_tabla(registros, semilla_maestra=1)
    assert [f.equipo for f in t] == ["ana", "caro", "dani", "beto"]
    notas = calificar(t, REFS, {"ana", "beto", "caro", "dani"})
    assert notas == {"ana": 10, "caro": 10, "dani": 10, "beto": 0}
