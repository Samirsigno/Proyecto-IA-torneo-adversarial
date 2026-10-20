"""Visor HTML: autocontenido, seguro con salida hostil y con índice completo."""

import json
import re
from pathlib import Path
from urllib.parse import unquote

import pytest

from arbitro.azar import Dados, semilla_bots
from arbitro.partida import jugar_partida
from arbitro.procesos import BotLocal
from arbitro.registro import a_json
from config import limites_prueba
from visor.generar import indice, visor_partida

BOTS = Path(__file__).parent / "bots"
LIMITES = limites_prueba()
HOSTIL = "</script><script>alert(1)</script><!--   fin"


@pytest.fixture(scope="module")
def registro() -> dict:
    r = jugar_partida(
        BotLocal(BOTS / "fiel"),
        BotLocal(BOTS / "azaroso"),
        Dados(1, 0, 0),
        LIMITES,
        LIMITES.efectivos(),
        semilla_bots(1, 0, 0),
    )
    meta = {"blancas": "fiel", "negras": "azaroso", "pareja": 0, "juego": 0, "semilla_maestra": 1}
    return a_json(r, meta)


def datos_incrustados(html: str) -> dict:
    m = re.search(r'<script id="datos" type="application/json">(.*?)</script>', html, re.S)
    assert m
    return json.loads(m.group(1))


def test_visor_autocontenido(registro, tmp_path):
    html = visor_partida(registro, tmp_path).read_text(encoding="utf-8")
    assert not re.search(r"""(src|href)=["']?(https?:)?//""", html)
    assert "@import" not in html and "url(http" not in html
    d = datos_incrustados(html)
    assert len(d["fotos"]) == len(registro["jugadas"]) + 1
    assert len(d["fotos"][0]["legales"]) > 0 and len(d["fotos"][0]["b"]) == 18


def test_visor_escapa_salida(registro, tmp_path):
    hostil = {**registro, "salidas": {"blancas": HOSTIL, "negras": "ok"}}
    hostil["jugadas"] = [dict(j) for j in registro["jugadas"]]
    hostil["jugadas"][0]["info"] = {"eval": 0.5, "nota": HOSTIL}
    html = visor_partida(hostil, tmp_path / "x.html").read_text(encoding="utf-8")
    # Solo los dos <script> de la plantilla (datos y código): ninguno viene del bot.
    assert html.count("<script") == 2 and html.count("</script") == 2
    assert "<script>alert" not in html and "<!--" not in html and " " not in html
    assert datos_incrustados(html)["registro"]["salidas"]["blancas"] == HOSTIL


def test_fotos_coinciden_con_resultado(registro, tmp_path):
    d = datos_incrustados(visor_partida(registro, tmp_path).read_text(encoding="utf-8"))
    assert d["fotos"][-1]["pts"] == [registro["puntos"]["blancas"], registro["puntos"]["negras"]]
    assert any(j["combate"] for j in registro["jugadas"])


def test_indice_enlaza_todas(registro, tmp_path):
    otro = {**registro, "meta": {**registro["meta"], "juego": 1}}
    ruta = indice([registro, otro], tmp_path)
    html = ruta.read_text(encoding="utf-8")
    enlaces = re.findall(r'href="([^"]+)"', html)
    assert len(enlaces) == 2 and len(set(enlaces)) == 2
    assert all((tmp_path / e).is_file() for e in enlaces)


def test_indice_no_sobrescribe_partidas_con_la_misma_meta(registro, tmp_path):
    # `jugar x x`: x contra x en los dos colores tiene la misma meta.
    otro = {**registro, "ganador": "negras"}
    ruta = indice([registro, otro], tmp_path)
    enlaces = re.findall(r'href="([^"]+)"', ruta.read_text(encoding="utf-8"))
    assert len(set(enlaces)) == 2
    ganadores = [
        datos_incrustados((tmp_path / e).read_text())["registro"]["ganador"] for e in enlaces
    ]
    assert ganadores == [registro["ganador"], "negras"]


NOMBRES_HOSTILES = ["../x", "a/b", "#?%", "{{DATOS}}", "..", "{{N}}"]


def test_nombres_hostiles_visor_e_indice(registro, tmp_path):
    carpeta = tmp_path / "salida"
    regs = []
    for i, nombre in enumerate(NOMBRES_HOSTILES):
        meta = {**registro["meta"], "blancas": nombre, "negras": nombre[::-1], "juego": i}
        regs.append({**registro, "meta": meta})
    for r in regs:
        ruta = visor_partida(r, carpeta)
        assert ruta.parent == carpeta and ruta.is_file()
        d = datos_incrustados(ruta.read_text(encoding="utf-8"))
        assert d["registro"]["meta"]["blancas"] == r["meta"]["blancas"]  # datos intactos
    ruta = indice(regs, carpeta)
    enlaces = [unquote(e) for e in re.findall(r'href="([^"]+)"', ruta.read_text(encoding="utf-8"))]
    assert len(enlaces) == len(regs)
    assert all("/" not in e and (carpeta / e).is_file() for e in enlaces)
    assert not (tmp_path / "x_vs_x..html").exists() and sorted(tmp_path.iterdir()) == [carpeta]


def test_indice_sobrevive_a_registro_malo_y_no_finitos(registro, tmp_path):
    con_nan = {**registro, "meta": {**registro["meta"], "juego": 5}}
    con_nan["jugadas"] = [dict(j) for j in registro["jugadas"]]
    con_nan["jugadas"][0]["info"] = {"eval": float("nan"), "x": float("inf")}
    malo = {"meta": registro["meta"]}
    ruta = indice([malo, con_nan], tmp_path)
    html = ruta.read_text(encoding="utf-8")
    assert "No se pudo generar" in html and html.count("Ver partida") == 1
    visor = next(tmp_path.glob("002_0_5_*.html")).read_text(encoding="utf-8")
    assert datos_incrustados(visor)["registro"]["jugadas"][0]["info"] == {"eval": None, "x": None}


def test_plantilla_reloj_final_y_probabilidades_por_flecha():
    plantilla = (Path(__file__).parents[1] / "visor" / "plantilla.html").read_text()
    # Posición final: el reloj del árbitro (incluye el turno en que se perdió por reloj).
    assert "pos === N && R.reloj_usado" in plantilla
    # La probabilidad va a media flecha (origen + destino) / 2, no sobre el destino.
    assert "x = (x1 + x2) / 2, y = (y1 + y2) / 2" in plantilla
