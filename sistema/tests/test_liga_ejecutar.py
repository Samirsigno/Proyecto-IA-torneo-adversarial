"""Ejecución de la liga: guardado por pareja, reanudar, fallas de infraestructura y núcleos."""

import json
import threading
from pathlib import Path

import pytest

from arbitro.partida import ResultadoPartida
from arbitro.procesos import BotLocal
from config import limites_prueba
from liga import ejecutar
from liga.calendario import generar_calendario
from liga.ejecutar import ejecutar_liga, leer_incidentes, leer_parejas, ranuras

BOTS = Path(__file__).parent / "bots"
LIMITES = limites_prueba()
CARPETAS = {"a": "azaroso", "b": "fiel", "c": "tranquilo"}


class Muerte(BaseException):
    """Simula que matan el proceso de la liga a la mitad."""


class BotRoto:
    """ProcesoBot que no arranca: provoca una falla de infraestructura."""

    def iniciar(self):
        raise RuntimeError("docker no responde")

    def enviar(self, msg): ...
    def recibir(self, timeout_s):
        return None

    def pausar(self): ...
    def reanudar(self): ...
    def terminar(self): ...
    def salida(self):
        return ""

    def causa_muerte(self):
        return None

    def memoria_pico_mb(self):
        return None


def correr(cal, salida, crear, semilla=11, **kw):
    return ejecutar_liga(cal, crear, LIMITES, LIMITES.efectivos(), semilla, 1, salida, **kw)


def local(nombre, nucleo):
    return BotLocal(BOTS / CARPETAS[nombre])


def test_liga_reanuda_sin_repetir_parejas(tmp_path):
    cal = generar_calendario(["a", "b", "c"], juegos_dados=1)  # 3 parejas × 2 partidas
    llamadas: list[str] = []

    def muere_en_la_pareja_1(nombre, nucleo):
        llamadas.append(nombre)
        if len(llamadas) == 7:  # 2.ª partida de la pareja 1 (c-a), ya empezada
            raise Muerte()
        return local(nombre, nucleo)

    with pytest.raises(Muerte):
        correr(cal, tmp_path, muere_en_la_pareja_1, nucleos=1)
    guardadas = sorted(p.name for p in (tmp_path / "parejas").glob("*.json"))
    assert guardadas == ["0.json"]  # la pareja a medias no se guardó
    antes = (tmp_path / "parejas" / "0.json").read_bytes()

    jugadas: list[tuple[str, str]] = []
    lock = threading.Lock()

    def cuenta(nombre, nucleo):
        with lock:
            jugadas.append(nombre)
        return local(nombre, nucleo)

    registros = correr(cal, tmp_path, cuenta, nucleos=1)
    # Se jugaron completas las parejas 1 y 2 (4 partidas, 8 bots); la 0 no se repitió.
    assert len(jugadas) == 8
    assert (tmp_path / "parejas" / "0.json").read_bytes() == antes
    assert len(registros) == 6
    assert [(r["meta"]["pareja"], r["meta"]["juego"]) for r in registros] == [
        (0, 0),
        (0, 0),
        (1, 0),
        (1, 0),
        (2, 0),
        (2, 0),
    ]
    assert all(r["version"] == 1 and r["ganador"] in {"blancas", "negras"} for r in registros)
    assert all(r["meta"]["semilla_maestra"] == 11 for r in registros)
    assert leer_parejas(tmp_path) == registros
    # Una tercera corrida no juega nada.
    jugadas.clear()
    assert correr(cal, tmp_path, cuenta, nucleos=1) == registros
    assert jugadas == []


def test_reanudar_con_otra_semilla_es_error(tmp_path):
    cal = generar_calendario(["a", "b"], juegos_dados=1)

    def muere(nombre, nucleo):
        raise Muerte()

    with pytest.raises(Muerte):
        correr(cal, tmp_path, muere, semilla=1, nucleos=1)
    estado = json.loads((tmp_path / "estado_liga.json").read_text())
    assert estado["semilla_maestra"] == 1 and estado["participantes"] == ["a", "b"]
    with pytest.raises(ValueError, match="otra liga"):
        correr(cal, tmp_path, muere, semilla=2, nucleos=1)
    with pytest.raises(ValueError, match="otra liga"):
        correr(generar_calendario(["a", "c"], 1), tmp_path, muere, semilla=1, nucleos=1)
    with pytest.raises(ValueError, match="otra liga"):
        correr(cal, tmp_path, muere, semilla=1, nucleos=1, hashes={"a": "x", "b": "y"})
    # Con lo mismo, sí reanuda (y vuelve a morir al crear el primer bot).
    with pytest.raises(Muerte):
        correr(cal, tmp_path, muere, semilla=1, nucleos=1)


def test_falla_de_infraestructura_repite_la_pareja_completa(tmp_path):
    cal = generar_calendario(["a", "b"], juegos_dados=1)
    intentos = {"n": 0}

    def falla_una_vez(nombre, nucleo):
        intentos["n"] += 1
        if intentos["n"] == 3:  # primer bot de la 2.ª partida del 1.er intento
            return BotRoto()
        return local(nombre, nucleo)

    registros = correr(cal, tmp_path, falla_una_vez, nucleos=1)
    assert len(registros) == 2 and all(r["ganador"] for r in registros)
    # 1.er intento: 2 bots + 1 roto (y su rival); 2.º intento: 4 bots.
    assert intentos["n"] == 8
    incidentes = leer_incidentes(tmp_path)
    assert len(incidentes) == 1
    assert incidentes[0]["pareja"] == 0 and incidentes[0]["excluida"] is False
    assert len(incidentes[0]["fallas"]) == 1


def test_falla_persistente_excluye_la_pareja(tmp_path):
    cal = generar_calendario(["a", "b"], juegos_dados=1)
    llamadas = {"n": 0}

    def siempre_roto(nombre, nucleo):
        llamadas["n"] += 1
        return BotRoto()

    assert correr(cal, tmp_path, siempre_roto, nucleos=1) == []
    assert llamadas["n"] == 3 * 2  # 3 intentos (1 + 2 repeticiones), 1 partida cada uno
    assert not list((tmp_path / "parejas").glob("*.json"))
    (incidente,) = leer_incidentes(tmp_path)
    assert incidente["excluida"] is True and len(incidente["fallas"]) == 3
    assert incidente["equipos"] == ["a", "b"]
    # Al reanudar (ya con la infraestructura bien) se vuelve a intentar y deja de estar
    # excluida, sin perder el historial.
    assert len(correr(cal, tmp_path, local, nucleos=1)) == 2
    (incidente,) = leer_incidentes(tmp_path)
    assert incidente["excluida"] is False and len(incidente["fallas"]) == 3


def test_si_falla_crear_negras_se_termina_blancas(tmp_path):
    cal = generar_calendario(["a", "b"], juegos_dados=1)
    terminados = []

    class Blancas(BotRoto):
        def terminar(self):
            terminados.append(1)

    def crear(nombre, nucleo):
        if nombre == "a":
            return Blancas()
        raise RuntimeError("no hay contenedor")

    assert correr(cal, tmp_path, crear, nucleos=1) == []
    # 3 intentos; en cada uno blancas ("a") se creó y se terminó.
    assert len(terminados) == 3
    (incidente,) = leer_incidentes(tmp_path)
    assert "no hay contenedor" in incidente["fallas"][0]


def test_ranuras_dejan_dos_nucleos_libres():
    assert ranuras(list(range(16)), 7) == [(2 + 2 * i, 3 + 2 * i) for i in range(7)]
    assert ranuras(list(range(16)), 3) == [(2, 3), (4, 5), (6, 7)]
    assert ranuras(list(range(8)), 7) == [(2, 3), (4, 5), (6, 7)]
    assert ranuras(list(range(6)), 7) == [(2, 3), (4, 5)]
    # Menos de 6 núcleos: sin núcleos fijos y una partida a la vez.
    assert ranuras(list(range(4)), 7) == [(None, None)]
    assert ranuras([0], 1) == [(None, None)]


def test_partidas_simultaneas_con_nucleos_fijos(tmp_path, monkeypatch):
    cal = generar_calendario(["a", "b", "c", "d"], juegos_dados=2)  # 6 parejas
    vistos: list[tuple] = []
    activos = {"n": 0, "max": 0}
    lock = threading.Lock()

    def falsa(blancas, negras, dados, publicos, efectivos, semilla_bots):
        with lock:
            activos["n"] += 1
            activos["max"] = max(activos["max"], activos["n"])
            vistos.append((blancas, negras))
        threading.Event().wait(0.05)
        with lock:
            activos["n"] -= 1
        return ResultadoPartida("blancas", "puntos", {"blancas": 3, "negras": 0})

    monkeypatch.setattr(ejecutar, "jugar_partida", falsa)
    registros = ejecutar_liga(
        cal, lambda n, c: (n, c), LIMITES, LIMITES.efectivos(), 3, 7, tmp_path, nucleos=16
    )
    assert len(registros) == 24
    assert 1 < activos["max"] <= 6  # 6 parejas → como máximo 6 a la vez
    for (_, nuc_b), (_, nuc_n) in vistos:
        assert nuc_b is not None and nuc_n == nuc_b + 1 and nuc_b >= 2


def _falsa(blancas, negras, dados, publicos, efectivos, semilla_bots):
    return ResultadoPartida("blancas", "puntos", {"blancas": 3, "negras": 0})


def test_reanudar_con_otros_limites_es_error(tmp_path, monkeypatch):
    from dataclasses import replace

    monkeypatch.setattr(ejecutar, "jugar_partida", _falsa)
    cal = generar_calendario(["a", "b"], juegos_dados=1)
    correr(cal, tmp_path, lambda n, c: n, nucleos=1)
    estado = json.loads((tmp_path / "estado_liga.json").read_text())
    assert estado["limites"]["efectivos"]["reloj_s"] == LIMITES.efectivos().reloj_s
    otros = replace(LIMITES, escala_limites=2.0)
    with pytest.raises(ValueError, match="limites"):
        ejecutar_liga(cal, lambda n, c: n, otros, otros.efectivos(), 11, 1, tmp_path, nucleos=1)
    with pytest.raises(ValueError, match="limites"):
        ejecutar_liga(cal, lambda n, c: n, LIMITES, otros.efectivos(), 11, 1, tmp_path, nucleos=1)


def test_shards_juntados_se_reanudan_como_liga_completa(tmp_path, monkeypatch):
    import shutil

    from liga.calendario import repartir

    jugadas: list[str] = []

    def falsa(blancas, negras, *args):
        jugadas.append(blancas)
        return _falsa(blancas, negras, *args)

    monkeypatch.setattr(ejecutar, "jugar_partida", falsa)
    completo = generar_calendario(["a", "b", "c", "d"], juegos_dados=1)  # 6 parejas
    juntada = tmp_path / "juntada"
    for i in (1, 2, 3):
        carpeta = tmp_path / f"shard{i}"
        parte = repartir(completo, i - 1, 3)
        correr(parte, carpeta, lambda n, c: n, nucleos=1, completo=completo, shard=(i, 3))
        assert (carpeta / "estados_shard" / f"{i}_de_3.json").is_file()
        if i < 3:  # el shard 3 «se perdió»: la liga completa lo debe reanudar
            shutil.copytree(carpeta, juntada, dirs_exist_ok=True)
    estados = {(tmp_path / f"shard{i}" / "estado_liga.json").read_text() for i in (1, 2, 3)}
    assert len(estados) == 1  # todos los shards escriben el mismo estado global
    jugadas.clear()
    registros = correr(completo, juntada, lambda n, c: n, nucleos=1)
    assert len(registros) == 12
    assert len(jugadas) == 4  # solo las 2 parejas del shard 3
    # Re-correr un shard sobre la carpeta juntada también es válido.
    jugadas.clear()
    parte = repartir(completo, 0, 3)
    correr(parte, juntada, lambda n, c: n, nucleos=1, completo=completo, shard=(1, 3))
    assert jugadas == []


def test_avance_cuenta_cada_pareja_una_vez(tmp_path, monkeypatch):
    monkeypatch.setattr(ejecutar, "jugar_partida", _falsa)
    cal = generar_calendario(["a", "b", "c", "d"], juegos_dados=1)
    lineas: list[str] = []
    ejecutar_liga(
        cal,
        lambda n, c: n,
        LIMITES,
        LIMITES.efectivos(),
        3,
        4,
        tmp_path,
        nucleos=16,
        avisar=lineas.append,
    )
    assert sorted(linea.rsplit(" ", 1)[1] for linea in lineas) == [f"{n}/6" for n in range(1, 7)]
    assert [linea.rsplit(" ", 1)[1] for linea in lineas][-1] == "6/6"


def _registro(pareja, juego, blancas, negras, semilla=5):
    meta = {"pareja": pareja, "juego": juego, "blancas": blancas, "negras": negras}
    return {"meta": {**meta, "semilla_maestra": semilla}}


def test_revisar_resultados_contra_el_calendario():
    cal = generar_calendario(["a", "b", "c"], juegos_dados=1)  # 3 parejas × 2
    completos = [_registro(p.pareja, p.juego, p.blancas, p.negras) for p in cal]
    revisar = ejecutar.revisar_resultados
    assert revisar(cal, completos, [], 5) == []
    assert "faltan" in revisar(cal, completos[:-1], [], 5)[0]
    assert "repetida" in revisar(cal, [*completos, completos[0]], [], 5)[0]
    assert "ajena" in revisar(cal, [*completos, _registro(0, 0, "a", "z")], [], 5)[0]
    assert (
        "ajena"
        in revisar(cal, [*completos[:-1], {**completos[-1]} | _registro(2, 0, "c", "b", 6)], [], 5)[
            0
        ]
    )
    excluida = [{"pareja": 2, "excluida": True}]
    assert revisar(cal, completos[:4], excluida, 5) == []
    assert "excluida" in revisar(cal, completos, excluida, 5)[0]
