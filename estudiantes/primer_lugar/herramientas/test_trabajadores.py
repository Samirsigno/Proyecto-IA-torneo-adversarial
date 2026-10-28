"""Pruebas del entrenamiento en paralelo: escritura en la tabla compartida y ciclo de los workers.

Las de `TestEntrenamientoParalelo` lanzan procesos de verdad (2 workers con pocas iteraciones):
tardan unos segundos.
"""

import json
import os
import time

import numpy as np

import specs
from entrenamiento import (
    MINIMO_EXPLORADO,
    celdas_exploradas,
    entrenar,
    escribir_valor,
    fusionar_arreglos,
    inicializar_tabla,
)


class TestEscrituraProtegida:
    """Una celda visitada nunca queda en 0.0: `fusionar_arreglos` la tomaría por no explorada."""

    def test_escribe_el_valor(self):
        tabla = np.zeros(specs.NUM_ESTADOS, dtype=np.float32)
        escribir_valor(tabla, 5, -37.5)
        assert tabla[5] == -37.5

    def test_un_cero_se_guarda_como_el_minimo_positivo(self):
        tabla = np.zeros(specs.NUM_ESTADOS, dtype=np.float32)
        escribir_valor(tabla, 5, 0.0)
        assert tabla[5] == MINIMO_EXPLORADO != 0.0

    def test_un_valor_que_en_float32_se_vuelve_cero_tambien(self):
        tabla = np.zeros(specs.NUM_ESTADOS, dtype=np.float32)
        escribir_valor(tabla, 5, 1e-50)
        assert tabla[5] == MINIMO_EXPLORADO

    def test_la_fusion_no_pierde_una_celda_que_vale_cero(self):
        tabla_a = np.zeros(specs.NUM_ESTADOS, dtype=np.float32)
        tabla_b = np.zeros(specs.NUM_ESTADOS, dtype=np.float32)
        escribir_valor(tabla_a, 7, 0.0)
        escribir_valor(tabla_b, 7, 50.0)
        assert np.isclose(fusionar_arreglos(tabla_a, tabla_b)[7], 25.0)

    def test_celdas_exploradas_no_cuenta_los_faros(self):
        tabla = inicializar_tabla()
        assert celdas_exploradas(tabla) == 0
        escribir_valor(tabla, 7, 0.0)
        assert celdas_exploradas(tabla) == 1


def memoria_compartida():
    return {nombre for nombre in os.listdir("/dev/shm") if nombre.startswith("psm_")}


def leer(salida):
    return np.load(salida), json.loads(salida.with_suffix(".json").read_text())


class TestEntrenamientoParalelo:
    def test_dos_workers_construyen_la_tabla(self, tmp_path):
        antes = memoria_compartida()
        salida = tmp_path / "prueba.npy"
        entrenar(salida, trabajadores=2, iteraciones=5, partidas_por_trabajador=1)
        tabla, meta = leer(salida)
        assert tabla.dtype == np.float32 and tabla.shape == (specs.NUM_ESTADOS,)
        assert meta["partidas"] == 2
        assert meta["respaldos"] > 0
        assert celdas_exploradas(tabla) > 0
        assert memoria_compartida() == antes  # los bloques se liberaron

    def test_reanuda_desde_lo_guardado(self, tmp_path):
        salida = tmp_path / "prueba.npy"
        entrenar(salida, trabajadores=2, iteraciones=5, partidas_por_trabajador=1)
        tabla_1, meta_1 = leer(salida)
        entrenar(salida, trabajadores=2, iteraciones=5, partidas_por_trabajador=1)
        tabla_2, meta_2 = leer(salida)
        assert meta_2["partidas"] == 4
        assert meta_2["respaldos"] > meta_1["respaldos"]
        assert np.all(tabla_2[tabla_1 != 0] != 0)  # lo explorado sigue explorado

    def test_desde_cero_ignora_lo_guardado(self, tmp_path):
        salida = tmp_path / "prueba.npy"
        entrenar(salida, trabajadores=2, iteraciones=5, partidas_por_trabajador=1)
        entrenar(salida, trabajadores=2, iteraciones=5, partidas_por_trabajador=1, desde_cero=True)
        assert leer(salida)[1]["partidas"] == 2

    def test_se_detiene_al_cumplir_las_horas_y_guarda(self, tmp_path):
        salida = tmp_path / "prueba.npy"
        inicio = time.monotonic()
        entrenar(salida, trabajadores=2, iteraciones=5, horas=2 / 3600)
        assert time.monotonic() - inicio < 60
        tabla, meta = leer(salida)
        assert meta["segundos"] >= 2
        assert meta["respaldos"] > 0
