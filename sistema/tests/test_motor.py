"""Tests del motor: reglas, combate, puntos, serialización y simulación."""

import random

import pytest

import motor
from motor import Estado, Jugada, prob_combate, reportar, simular_al_azar, tomar_reporte


def posicion(blancas, negras, turno="blancas", puntos=(0, 0)) -> Estado:
    """Arma una posición con casillas en texto, p. ej. ["e4", "d3"]."""
    return Estado.desde_dict(
        {
            "blancas": blancas,
            "negras": negras,
            "turno": turno,
            "puntos": {"blancas": puntos[0], "negras": puntos[1]},
        }
    )


def textos(e: Estado) -> set[str]:
    return {str(j) for j in e.jugadas()}


J = Jugada.desde_texto


# --- Movimiento ---------------------------------------------------------------


def test_inicial():
    e = Estado.inicial()
    # 9 peones de la fila 2 × 3 destinos − 2 de los bordes; la fila 1 está bloqueada.
    assert len(e.jugadas()) == 25
    assert e.turno == "blancas"
    assert e.puntos == {"blancas": 0, "negras": 0}
    assert not e.terminado() and e.ganador() is None


def test_inicial_negras():
    e = Estado.inicial().aplicar(J("e2-e3"))
    assert e.turno == "negras"
    assert len(e.jugadas()) == 25
    assert all(int(str(j)[1]) == 8 and int(str(j)[4]) == 7 for j in e.jugadas())


def test_no_atras_ni_lado():
    e = posicion(["e5"], ["a9"])
    assert textos(e) == {"e5-d6", "e5-e6", "e5-f6"}
    for j in e.jugadas():
        assert j.destino // 9 == j.origen // 9 + 1
    n = posicion(["a1"], ["e5"], turno="negras")
    assert textos(n) == {"e5-d4", "e5-e4", "e5-f4"}


def test_bordes():
    assert textos(posicion(["a3"], ["i9"])) == {"a3-a4", "a3-b4"}
    assert textos(posicion(["i3"], ["a9"])) == {"i3-h4", "i3-i4"}


def test_recto_bloqueado():
    # Pieza rival enfrente: no avanza recto (y no se ataca recto).
    assert "e4-e5" not in textos(posicion(["e4"], ["e5"]))
    # Pieza propia enfrente: tampoco.
    assert "e4-e5" not in textos(posicion(["e4", "e5"], ["a9"]))


def test_diagonal_propia_prohibida():
    assert "e4-f5" not in textos(posicion(["e4", "f5"], ["a9"]))


def test_diagonal_rival_es_ataque():
    e = posicion(["e4"], ["f5"])
    assert e.es_ataque(J("e4-f5"))
    assert not e.es_ataque(J("e4-e5"))
    assert e.prob_ataque(J("e4-e5")) == 1.0


def test_jugada_ilegal_y_falta_dado():
    e = posicion(["e4"], ["f5"])
    with pytest.raises(ValueError):
        e.aplicar(J("e4-e6"))
    with pytest.raises(ValueError):
        e.aplicar(J("e4-f5"))  # ataque sin gana_ataque
    assert e.aplicar("e4-e5").turno == "negras"  # también acepta texto


# --- Combate -----------------------------------------------------------------


def test_prob_combate_tabla():
    pares = [(0, 2), (0, 1), (1, 1), (2, 1), (2, 0)]
    assert [prob_combate(a, d) for a, d in pares] == pytest.approx([0.2, 0.35, 0.5, 0.65, 0.8])


def test_apoyo_desde_origen():
    # g4 está detrás del DESTINO (f5), no del origen (e4): no cuenta.
    assert posicion(["e4", "g4"], ["f5"]).prob_ataque(J("e4-f5")) == pytest.approx(0.5)
    # d3 y f3 están en diagonal detrás del origen e4: cuentan.
    assert posicion(["e4", "d3"], ["f5"]).prob_ataque(J("e4-f5")) == pytest.approx(0.65)
    assert posicion(["e4", "d3", "f3"], ["f5"]).prob_ataque(J("e4-f5")) == pytest.approx(0.8)
    # Apoyo del defensor (Negras: su «atrás» es la fila 6).
    assert posicion(["e4"], ["f5", "e6", "g6"]).prob_ataque(J("e4-f5")) == pytest.approx(0.2)
    # Recto detrás (e3) no es apoyo.
    assert posicion(["e4", "e3"], ["f5"]).prob_ataque(J("e4-f5")) == pytest.approx(0.5)


def test_apoyo_negras_atacan():
    # Negras en e6 atacan d5; su apoyo está en d7 y f7.
    e = posicion(["d5", "c4"], ["e6", "d7", "f7"], turno="negras")
    assert e.prob_ataque(J("e6-d5")) == pytest.approx(0.65)


def test_ataque_gana_y_pierde():
    e = posicion(["e4", "d3"], ["f5", "a9"])
    j = J("e4-f5")
    (p1, gana), (p2, pierde) = e.siguiente(j)
    assert p1 == pytest.approx(0.65) and p1 + p2 == pytest.approx(1)
    # Gana: el defensor sale y el atacante ocupa su casilla.
    assert gana.a_dict()["blancas"] == ["d3", "f5"]
    assert gana.a_dict()["negras"] == ["a9"]
    # Pierde: sale el atacante y el defensor se queda.
    assert pierde.a_dict()["blancas"] == ["d3"]
    assert pierde.a_dict()["negras"] == ["f5", "a9"]
    assert gana.turno == pierde.turno == "negras"
    assert gana.clave == e.aplicar(j, gana_ataque=True).clave
    assert pierde.clave == e.aplicar(j, gana_ataque=False).clave


def test_siguiente_sin_ataque():
    e = Estado.inicial()
    [(p, nuevo)] = e.siguiente(J("e2-e3"))
    assert p == 1.0 and nuevo.clave == e.aplicar(J("e2-e3")).clave


def test_estado_inmutable():
    e = Estado.inicial()
    antes = e.clave
    e.aplicar(J("e2-e3"))
    e.siguiente(J("d2-d3"))
    e.jugadas().clear()
    e.puntos["blancas"] = 99
    assert e.clave == antes and len(e.jugadas()) == 25 and e.puntos["blancas"] == 0


# --- Puntos y fin ------------------------------------------------------------


def test_anotar_caminando():
    e = posicion(["e8"], ["a9"])
    nuevo = e.aplicar(J("e8-e9"))
    assert nuevo.puntos == {"blancas": 1, "negras": 0}
    assert nuevo.a_dict()["blancas"] == []  # la pieza desaparece
    n = posicion(["i1"], ["e2"], turno="negras").aplicar(J("e2-d1"))
    assert n.puntos == {"blancas": 0, "negras": 1} and n.a_dict()["negras"] == []


def test_anotar_ganando_ataque():
    e = posicion(["e8", "a2"], ["f9", "a9"])
    gana = e.aplicar(J("e8-f9"), gana_ataque=True)
    assert gana.puntos["blancas"] == 1
    assert gana.a_dict()["blancas"] == ["a2"] and gana.a_dict()["negras"] == ["a9"]
    pierde = e.aplicar(J("e8-f9"), gana_ataque=False)
    assert pierde.puntos["blancas"] == 0
    assert pierde.a_dict()["blancas"] == ["a2"] and pierde.a_dict()["negras"] == ["a9", "f9"]


def test_tres_puntos_gana():
    e = posicion(["e8", "a2"], ["a9", "b9"], puntos=(2, 0)).aplicar(J("e8-e9"))
    assert e.terminado() and e.ganador() == "blancas"
    assert e.jugadas() == []
    with pytest.raises(ValueError):
        e.aplicar(J("a2-a3"))


def test_sin_jugadas_pierde():
    e = posicion([], ["e5"])
    assert e.jugadas() == []
    assert e.terminado() and e.ganador() == "negras"
    n = posicion(["e5"], [], turno="negras")
    assert n.terminado() and n.ganador() == "blancas"


def test_partidas_al_azar_siempre_terminan():
    for semilla in range(200):
        rng = random.Random(semilla)
        e = Estado.inicial()
        jugadas = 0
        while not e.terminado():
            j = rng.choice(e.jugadas())
            gana = rng.random() < e.prob_ataque(j) if e.es_ataque(j) else None
            e = e.aplicar(j, gana_ataque=gana)
            jugadas += 1
            assert jugadas <= 2 * 144
        assert e.ganador() in ("blancas", "negras")


# --- Texto, diccionario y clave ------------------------------------------------


def test_texto_ida_y_vuelta():
    assert str(Jugada.desde_texto("a1-b2")) == "a1-b2"
    j = Jugada.desde_texto("e2-e3")
    assert j == Jugada(13, 22) and str(Jugada(13, 22)) == "e2-e3"


@pytest.mark.parametrize("malo", ["", "e2e3", "e2-e10", "j2-j3", "e0-e1", "E2-E3x", 23])
def test_texto_mal_formado(malo):
    with pytest.raises(ValueError):
        Jugada.desde_texto(malo)


def test_dict_ida_y_vuelta():
    e = Estado.inicial()
    rng = random.Random(3)
    for _ in range(30):
        j = rng.choice(e.jugadas())
        e = e.aplicar(j, gana_ataque=True if e.es_ataque(j) else None)
    copia = Estado.desde_dict(e.a_dict())
    assert copia.clave == e.clave and copia == e
    assert copia.a_dict() == e.a_dict()


@pytest.mark.parametrize(
    "malo",
    [
        {"blancas": ["e4"], "negras": ["e4"], "turno": "blancas"},  # casilla repetida
        {"blancas": ["e9"], "negras": ["a9"], "turno": "blancas"},  # Blancas en su fila de anotar
        {"blancas": ["e4"], "negras": ["a9"], "turno": "rojas"},
        {"blancas": ["z4"], "negras": ["a9"], "turno": "blancas"},
        {"blancas": ["e4"], "negras": ["a9"], "turno": "blancas", "puntos": {"blancas": 4}},
    ],
)
def test_dict_invalido(malo):
    with pytest.raises(ValueError):
        Estado.desde_dict(malo)


def test_clave_distinta_por_turno():
    b = posicion(["e4"], ["a9"], turno="blancas")
    n = posicion(["e4"], ["a9"], turno="negras")
    assert b.clave != n.clave
    assert posicion(["e4"], ["a9"], puntos=(1, 0)).clave != b.clave
    assert posicion(["e4"], ["a9"], puntos=(0, 1)).clave != b.clave
    assert 0 <= b.clave < 2**64


def test_dibujar():
    texto = Estado.inicial().dibujar()
    assert "a b c d e f g h i" in texto
    assert "blancas" in texto


# --- Simulación ----------------------------------------------------------------


def test_simular_al_azar_rango_y_determinista():
    r = simular_al_azar(Estado.inicial(), 200, 7, "blancas")
    assert 0 <= r <= 1 and r == simular_al_azar(Estado.inicial(), 200, 7, "blancas")
    assert simular_al_azar(Estado.inicial(), 200, 7, "negras") == pytest.approx(1 - r)


def test_simular_perspectiva():
    # Blancas a una jugada de su tercer punto y con el turno.
    e = posicion(["e8"], ["a9", "b9"], puntos=(2, 0))
    assert simular_al_azar(e, 200, 1, "blancas") > 0.9
    assert simular_al_azar(e, 200, 1, "negras") < 0.1


def test_simular_terminal():
    ganada_blancas = posicion(["e4"], ["a9"], puntos=(3, 0))
    assert simular_al_azar(ganada_blancas, 10, 1, "blancas") == 1.0
    assert simular_al_azar(ganada_blancas, 10, 1, "negras") == 0.0


def test_simular_argumentos_invalidos():
    with pytest.raises(ValueError):
        simular_al_azar(Estado.inicial(), 10, 1, "rojas")
    with pytest.raises(ValueError):
        simular_al_azar(Estado.inicial(), 0, 1, "blancas")
    with pytest.raises(ValueError):
        simular_al_azar(Estado.inicial(), 10, 1.5, "blancas")


# --- Reporte -----------------------------------------------------------------


def test_reporte():
    assert tomar_reporte() is None
    reportar(prof=3, nodos=1200)
    assert tomar_reporte() == {"prof": 3, "nodos": 1200}
    assert tomar_reporte() is None


def _prob_exacta(e: Estado, para: str, memo: dict) -> float:
    """Probabilidad exacta de que gane `para` si ambos juegan uniforme al azar."""
    if e.terminado():
        return 1.0 if e.ganador() == para else 0.0
    if e.clave not in memo:
        jugadas = e.jugadas()
        memo[e.clave] = sum(
            p * _prob_exacta(s, para, memo) for j in jugadas for p, s in e.siguiente(j)
        ) / len(jugadas)
    return memo[e.clave]


def test_simular_coincide_con_calculo_exacto():
    # Final pequeño con bloqueos y ataques: la simulación debe estimar la probabilidad exacta.
    e = posicion(["a5", "b6"], ["a6", "c7"], turno="negras", puntos=(2, 2))
    exacta = _prob_exacta(e, "blancas", {})
    assert 0.05 < exacta < 0.95
    assert simular_al_azar(e, 40000, 3, "blancas") == pytest.approx(exacta, abs=0.015)


# --- Revisión A2 ---------------------------------------------------------------


def test_piezas():
    e = posicion(["e4", "a2"], ["f5"])
    assert e.piezas("blancas") == ["a2", "e4"]
    assert e.piezas("negras") == ["f5"]
    assert len(Estado.inicial().piezas("negras")) == 18
    with pytest.raises(ValueError):
        e.piezas("rojas")


def test_version():
    assert motor.__version__ == "1.0.0"


def test_tupla_no_es_jugada():
    e = Estado.inicial()
    with pytest.raises(ValueError):
        e.aplicar((13, 22))
    with pytest.raises(ValueError):
        e.siguiente((13, 22))
    assert e.aplicar(Jugada(13, 22)).turno == "negras"


@pytest.mark.parametrize("malo", [-1, 81, 1000])
def test_nombre_casilla_fuera_de_rango(malo):
    with pytest.raises(ValueError):
        str(Jugada(malo, 13))
