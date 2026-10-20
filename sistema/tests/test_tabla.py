"""Tabla de la liga y desempates (docs/calificacion.md), con registros sintéticos."""

from itertools import count

from liga.tabla import FilaTabla, construir_tabla

_parejas = count(1000)


def reg(ganador: str, perdedor: str, anot_g: int = 3, anot_p: int = 0, pareja=None) -> dict:
    """Registro v1 mínimo: `ganador` (con blancas) le gana a `perdedor`."""
    return {
        "version": 1,
        "meta": {
            "blancas": ganador,
            "negras": perdedor,
            "pareja": next(_parejas) if pareja is None else pareja,
            "juego": 0,
            "semilla_maestra": 1,
        },
        "jugadas": [],
        "ganador": "blancas",
        "motivo": "puntos",
        "puntos": {"blancas": anot_g, "negras": anot_p},
        "reloj_usado": {},
        "salidas": {},
    }


def por_equipo(tabla: list[FilaTabla]) -> dict[str, FilaTabla]:
    return {f.equipo: f for f in tabla}


def orden(tabla: list[FilaTabla]) -> list[str]:
    return [f.equipo for f in tabla]


def test_puntos_victorias_y_posiciones():
    tabla = construir_tabla([reg("a", "b"), reg("a", "c"), reg("b", "c")], semilla_maestra=1)
    assert orden(tabla) == ["a", "b", "c"]
    assert [f.posicion for f in tabla] == [1, 2, 3]
    a = por_equipo(tabla)["a"]
    assert (a.puntos, a.victorias, a.partidas) == (2, 2, 2)
    assert por_equipo(tabla)["c"].puntos == 0


def test_desempate_entre_empatados():
    # x y y empatan con 3 puntos. y tiene mejor Sonneborn-Berger, pero x le ganó a y.
    registros = [
        reg("x", "y"),
        reg("x", "w"),
        reg("x", "w"),
        reg("y", "s"),
        reg("y", "s"),
        reg("y", "w"),
        reg("s", "w"),
        reg("s", "x"),
    ]
    tabla = construir_tabla(registros, semilla_maestra=1)
    t = por_equipo(tabla)
    assert t["x"].puntos == t["y"].puntos == 3
    assert t["y"].sb > t["x"].sb
    assert orden(tabla)[:2] == ["x", "y"]


def test_desempate_entre_empatados_cuenta_a_todo_el_grupo():
    # Empate de 3 (a, b, r): r es referencia y cuenta igual que los alumnos.
    # Entre ellos: r 2, a 1, b 0.
    registros = [
        reg("r", "a"),
        reg("r", "b"),
        reg("a", "b"),
        reg("a", "w"),
        reg("b", "w"),
        reg("b", "w"),
        reg("w", "r"),
    ]
    tabla = construir_tabla(registros, semilla_maestra=1)
    assert {f.puntos for f in tabla if f.equipo != "w"} == {2}
    assert orden(tabla)[:3] == ["r", "a", "b"]


def test_desempate_sb_por_partida():
    # x y y: 3 puntos, 1–1 entre ellos. x le ganó DOS veces a s (2 puntos): cuenta 2 veces.
    registros = [
        reg("x", "y"),
        reg("y", "x"),
        reg("x", "s"),
        reg("x", "s"),
        reg("y", "w"),
        reg("y", "w"),
        reg("s", "w"),
        reg("s", "w"),
    ]
    tabla = construir_tabla(registros, semilla_maestra=1)
    t = por_equipo(tabla)
    assert t["x"].puntos == t["y"].puntos == 3
    assert t["x"].sb == 3 + 2 + 2  # y + s + s (por partida, no por rival)
    assert t["y"].sb == 3 + 0 + 0
    assert orden(tabla)[:2] == ["x", "y"]


def test_desempate_anotados_y_sorteo_determinista():
    # x y y: mismos puntos, 1–1 entre ellos, mismo SB; x anotó más peones.
    registros = [
        reg("x", "y", 3, 0),
        reg("y", "x", 3, 2),
        reg("x", "w", 3, 1),
        reg("y", "w", 3, 2),
    ]
    for semilla in range(20):
        tabla = construir_tabla(registros, semilla_maestra=semilla)
        t = por_equipo(tabla)
        assert t["x"].sb == t["y"].sb
        assert (t["x"].anotados, t["y"].anotados) == (8, 6)
        assert orden(tabla)[:2] == ["x", "y"]

    # Empate total: decide el sorteo, siempre igual con la misma semilla.
    simetricos = [reg("a", "b"), reg("b", "a")]
    ordenes = set()
    for semilla in range(30):
        primero = orden(construir_tabla(simetricos, semilla_maestra=semilla))
        assert primero == orden(construir_tabla(simetricos, semilla_maestra=semilla))
        ordenes.add(tuple(primero))
    assert ordenes == {("a", "b"), ("b", "a")}
    # Orden fijado: sha256("<semilla>:<equipo>") de menor a mayor. Si esto cambia, cambió
    # el sorteo publicado (y una liga ya jugada no se podría reproducir).
    assert orden(construir_tabla(simetricos, semilla_maestra=0)) == ["a", "b"]
    assert orden(construir_tabla(simetricos, semilla_maestra=4)) == ["b", "a"]
    assert orden(construir_tabla(simetricos, semilla_maestra=11)) == ["b", "a"]


def test_falla_de_infraestructura_nunca_entra_a_la_tabla():
    # La pareja 7 tiene una falla: se descartan TODAS sus partidas.
    falla = reg("a", "b", pareja=7)
    falla["ganador"] = ""
    registros = [reg("a", "b", pareja=7), falla, reg("b", "a", pareja=8)]
    tabla = construir_tabla(registros, semilla_maestra=1)
    t = por_equipo(tabla)
    assert (t["a"].puntos, t["a"].partidas) == (0, 1)
    assert (t["b"].puntos, t["b"].partidas) == (1, 1)


def test_participantes_sin_partidas_aparecen_con_cero():
    tabla = construir_tabla([reg("a", "b")], semilla_maestra=1, participantes=["a", "b", "z"])
    assert orden(tabla) == ["a", "b", "z"] or orden(tabla) == ["a", "z", "b"]
    assert por_equipo(tabla)["z"].partidas == 0
