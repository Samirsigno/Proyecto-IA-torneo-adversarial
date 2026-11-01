"""Pruebas de las partes puras de `tuning_mcts.py` (sin Docker ni partidas de verdad)."""

import csv
import importlib.util
import math
from collections import Counter
from pathlib import Path

import pytest

from tuning_mcts import (
    CAMPOS,
    Tarea,
    barra,
    constante_c,
    copiar_bot,
    fila,
    hechas,
    resumen,
    tareas,
    valores_k,
)

EQUIPO = Path(__file__).resolve().parent.parent


def importar(ruta: Path, nombre: str):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class TestValoresDeK:
    def test_de_1_a_6_cada_medio(self):
        assert valores_k(1.0, 6.0, 0.5) == [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0]

    def test_c_es_raiz_de_2k(self):
        assert math.isclose(constante_c(2.5), math.sqrt(5))


class TestCopiaDelBot:
    def test_la_copia_juega_con_su_k(self, tmp_path):
        copiar_bot(EQUIPO, tmp_path / "k2.5", 2.5)
        bot = importar(tmp_path / "k2.5" / "strategy.py", "strategy_k2_5")
        assert bot.K_EXPLORACION == 2.5
        assert math.isclose(bot.EXPLORACION, math.sqrt(5))
        assert not (tmp_path / "k2.5" / "herramientas").exists()  # solo lo que juega

    def test_el_original_no_cambia(self, tmp_path):
        antes = (EQUIPO / "strategy.py").read_text()
        copiar_bot(EQUIPO, tmp_path / "k4.0", 4.0)
        assert (EQUIPO / "strategy.py").read_text() == antes

    def test_sin_la_linea_de_k_es_error(self, tmp_path):
        origen = tmp_path / "bot"
        origen.mkdir()
        (origen / "strategy.py").write_text("EXPLORACION = 1.4\n")
        with pytest.raises(ValueError, match="K_EXPLORACION"):
            copiar_bot(origen, tmp_path / "copia", 2.0)


class TestTareas:
    def test_30_por_k_mitad_con_cada_color(self):
        lista = tareas([1.0, 1.5, 2.0], partidas_por_k=30)
        assert len(lista) == 90
        por_k_color = Counter((t.k, t.color_uct) for t in lista)
        assert set(por_k_color.values()) == {15}

    def test_todos_los_k_juegan_con_los_mismos_dados(self):
        lista = tareas([1.0, 3.5], partidas_por_k=30)
        dados = {k: sorted((t.juego, t.color_uct) for t in lista if t.k == k) for k in (1.0, 3.5)}
        assert dados[1.0] == dados[3.5]
        assert len(set(dados[1.0])) == 30  # sin repetir dados y color

    def test_intercaladas_por_k(self):
        valores = valores_k(1.0, 6.0, 0.5)
        lista = tareas(valores, partidas_por_k=30)
        assert [t.k for t in lista[: len(valores)]] == valores  # si se corta, todos los K avanzan

    def test_partidas_impares_es_error(self):
        with pytest.raises(ValueError):
            tareas([1.0], partidas_por_k=7)


def registro_falso(color_uct):
    rival = "negras" if color_uct == "blancas" else "blancas"
    jugadas = []
    for n in range(1, 7):
        color = "blancas" if n % 2 else "negras"
        info = {"nodos": 100 * n, "prof": 3} if color == color_uct else None
        jugadas.append({"n": n, "color": color, "tiempo": 0.1 * n, "info": info})
    return {
        "ganador": color_uct,
        "motivo": "puntos",
        "puntos": {color_uct: 3, rival: 1},
        "reloj_usado": {color_uct: 12.5, rival: 9.0},
        "jugadas": jugadas,
    }


class TestFila:
    def test_metricas_de_la_partida(self):
        tarea = Tarea(k=2.0, juego=4, color_uct="blancas")
        f = fila(tarea, registro_falso("blancas"), duracion_s=40.0, intentos=1)
        assert f["k"] == 2.0 and math.isclose(f["c"], 2.0)
        assert f["gano_uct"] == 1 and f["ganador"] == "blancas" and f["motivo"] == "puntos"
        assert (f["puntos_uct"], f["puntos_rival"]) == (3, 1)
        assert (f["jugadas"], f["jugadas_uct"]) == (6, 3)
        assert math.isclose(f["t_turno_prom_uct_s"], (0.1 + 0.3 + 0.5) / 3)
        assert math.isclose(f["t_turno_prom_rival_s"], (0.2 + 0.4 + 0.6) / 3)
        assert math.isclose(f["nodos_prom_uct"], (100 + 300 + 500) / 3)
        assert (f["reloj_uct_s"], f["reloj_rival_s"]) == (12.5, 9.0)
        assert set(f) == set(CAMPOS)

    def test_con_negras(self):
        f = fila(Tarea(1.0, 0, "negras"), registro_falso("negras"), 30.0, 1)
        assert f["gano_uct"] == 1 and f["jugadas_uct"] == 3
        assert math.isclose(f["nodos_prom_uct"], (200 + 400 + 600) / 3)


class TestReanudar:
    def test_lee_las_partidas_ya_hechas(self, tmp_path):
        ruta = tmp_path / "partidas.csv"
        assert hechas(ruta) == set()
        with ruta.open("w", newline="") as archivo:
            w = csv.DictWriter(archivo, CAMPOS)
            w.writeheader()
            w.writerow(fila(Tarea(1.5, 2, "negras"), registro_falso("negras"), 30.0, 1))
        assert hechas(ruta) == {Tarea(1.5, 2, "negras")}


class TestBarra:
    def test_avance_y_tiempo_restante(self):
        texto = barra(30, 330, transcurrido_s=300.0, ancho=20)
        assert "30/330" in texto and "9%" in texto
        assert "ETA 0:50:00" in texto  # 10 s por partida × 300 que faltan

    def test_al_inicio_no_hay_eta(self):
        assert "ETA --:--:--" in barra(0, 330, transcurrido_s=5.0)


class TestResumen:
    def test_win_rate_y_error_estandar_por_k(self):
        filas = [{"k": 2.0, "gano_uct": g} for g in (1, 1, 1, 0)] + [{"k": 1.0, "gano_uct": 0}]
        r = resumen(filas)
        assert [x["k"] for x in r] == [1.0, 2.0]
        dos = r[1]
        assert (dos["partidas"], dos["ganadas"]) == (4, 3)
        assert math.isclose(dos["win_rate"], 0.75)
        assert math.isclose(dos["error_estandar"], math.sqrt(0.75 * 0.25 / 4))
