"""Participantes públicos `random` y `montecarlo`."""

import importlib.util
import time
import tomllib
from pathlib import Path
from types import SimpleNamespace

from arbitro.azar import Dados, semilla_bots, semilla_de_color
from arbitro.partida import jugar_partida
from arbitro.procesos import BotLocal
from config import RAIZ, limites_prueba
from motor import Estado

ESTUDIANTES = Path(RAIZ) / "estudiantes"
LIMITES = limites_prueba()


def partida(blancas: str, negras: str, semilla: int, limites=LIMITES):
    return jugar_partida(
        BotLocal(ESTUDIANTES / blancas),
        BotLocal(ESTUDIANTES / negras),
        Dados(semilla, 0, 0),
        limites,
        limites.efectivos(),
        semilla_bots(semilla, 0, 0),
    )


def test_random_juega_legal():
    for semilla in range(4):
        r = partida("random", "random", semilla)
        assert r.motivo in {"puntos", "sin_jugadas"}, r.salidas
        assert not r.falla_infraestructura


def test_montecarlo_le_gana_a_random():
    victorias = 0
    for semilla in range(14):
        mc_blancas = semilla % 2 == 0
        r = partida(
            *(("montecarlo", "random") if mc_blancas else ("random", "montecarlo")), semilla
        )
        assert not r.falla_infraestructura
        victorias += r.ganador == ("blancas" if mc_blancas else "negras")
    assert victorias >= 11  # ~90 % medido; azar puro (50 %) casi nunca llega


def cargar_montecarlo(semilla: int = 1):
    spec = importlib.util.spec_from_file_location("mc", ESTUDIANTES / "montecarlo" / "strategy.py")
    mc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mc)
    mc.preparar(
        SimpleNamespace(
            color="blancas", semilla=semilla_de_color(semilla, "blancas"), reloj_s=LIMITES.reloj_s
        )
    )
    return mc


def test_montecarlo_toma_victoria_inmediata():
    mc = cargar_montecarlo()
    estado = Estado.desde_dict(
        {
            "blancas": ["e8", "a1"],
            "negras": ["i9", "a9"],
            "turno": "blancas",
            "puntos": {"blancas": 2, "negras": 0},
        }
    )
    # Reloj casi en cero: solo el atajo de victoria inmediata puede encontrarla.
    jugada = mc.jugar(estado, 0.01)
    assert all(h.ganador() == "blancas" for _, h in estado.siguiente(jugada))


def test_montecarlo_con_poco_reloj_es_rapido_y_legal():
    mc = cargar_montecarlo()
    estado = Estado.inicial()
    for restante in (0.01, 0.0):
        t = time.perf_counter()
        jugada = mc.jugar(estado, restante)
        assert time.perf_counter() - t < 0.05
        assert jugada in estado.jugadas()


def test_montecarlo_respeta_reloj():
    rs = [partida("montecarlo", "random", 100), partida("random", "montecarlo", 101)]
    assert max(t for r in rs for t in r.reloj_usado.values()) < LIMITES.reloj_s


def test_plantillas_completas():
    for nombre in ("random", "montecarlo"):
        carpeta = ESTUDIANTES / nombre
        equipo = tomllib.loads((carpeta / "equipo.toml").read_text(encoding="utf-8"))
        assert equipo["nombre"] == nombre
        assert len(equipo["integrantes"]) == 2
        assert all({"nombre", "clave_unica"} <= set(i) for i in equipo["integrantes"])
        informe = (carpeta / "INFORME.md").read_text(encoding="utf-8")
        for n in range(1, 10):
            assert f"## {n}. " in informe
    assert len((ESTUDIANTES / "montecarlo" / "strategy.py").read_text().splitlines()) <= 60
    assert len((ESTUDIANTES / "random" / "strategy.py").read_text().splitlines()) <= 15


def test_montecarlo_reporta_muestras_y_eval():
    from motor import tomar_reporte

    mc = cargar_montecarlo()
    tomar_reporte()
    mc.jugar(Estado.inicial(), 3.0)
    datos = tomar_reporte()
    assert datos is not None and datos["muestras"] > 0 and 0 <= datos["eval"] <= 1
