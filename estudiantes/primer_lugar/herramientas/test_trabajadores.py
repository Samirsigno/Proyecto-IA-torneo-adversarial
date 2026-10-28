"""Pruebas del entrenamiento en paralelo: escritura en la tabla compartida y ciclo de los workers.

Las de `TestEntrenamientoParalelo` lanzan procesos de verdad (2 workers con pocas iteraciones):
tardan unos segundos.
"""

import json
import os
import random
import re
import time

import numpy as np
from motor import Estado

import abstraccion
import mcts
import specs
from entrenamiento import (
    GAMMA,
    MINIMO_EXPLORADO,
    celdas_exploradas,
    elegir_rama,
    entrenar,
    escribir_valor,
    fusionar_arreglos,
    generar_tablero_aleatorio,
    inicializar_tabla,
    jugar_turno,
    tablero_de_inicio,
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


class TestTableroAleatorio:
    def test_es_valido_caotico_y_nunca_terminal(self):
        dado = random.Random(1)
        cuantos, turnos = set(), set()
        for _ in range(500):
            e = generar_tablero_aleatorio(dado)
            blancas, negras = e.piezas("blancas"), e.piezas("negras")
            assert 2 <= len(blancas) <= 18 and 2 <= len(negras) <= 18
            assert not any(c.endswith("9") for c in blancas)  # fila donde anotarían
            assert not any(c.endswith("1") for c in negras)
            assert e.puntos == {"blancas": 0, "negras": 0}
            assert not e.terminado()
            cuantos.update((len(blancas), len(negras)))
            turnos.add(e.turno)
        assert cuantos == set(range(2, 19))
        assert turnos == {"blancas", "negras"}

    def test_inicio_95_estandar_5_caos(self):
        dado = random.Random(2)
        inicios = [tablero_de_inicio(dado, prob_caos=0.05) for _ in range(4000)]
        caoticos = sum(e != Estado.inicial() for e in inicios)
        assert 140 <= caoticos <= 260  # esperado 200 (±4.3 desviaciones estándar)


class TestEpsilonGreedy:
    """La política que se juega es ε-greedy; la tabla se actualiza siempre con max_a."""

    def busqueda_y_raiz(self, tabla):
        def al_expandir(nodo):
            escribir_valor(tabla, abstraccion.indice(nodo.resumen), nodo.valor)

        busqueda = mcts.MCTS(tabla, GAMMA, al_expandir)
        e = Estado.desde_dict(
            {"blancas": ["e4", "d3", "f3"], "negras": ["f5", "g6"], "turno": "blancas"}
        )
        return busqueda, busqueda.nodo(e)

    def test_epsilon_cero_juega_la_mejor(self):
        dado = random.Random(3)
        busqueda, raiz = self.busqueda_y_raiz(inicializar_tabla())
        mejor = busqueda.buscar(raiz, iteraciones=1)
        assert all(elegir_rama(raiz, mejor, dado, epsilon=0.0) is mejor for _ in range(100))

    def test_epsilon_uno_puede_jugar_cualquier_jugada_legal(self):
        dado = random.Random(4)
        busqueda, raiz = self.busqueda_y_raiz(inicializar_tabla())
        mejor = busqueda.buscar(raiz, iteraciones=1)
        elegidas = {id(elegir_rama(raiz, mejor, dado, epsilon=1.0)) for _ in range(500)}
        assert elegidas == {id(r) for r in raiz.jugadas}

    def test_la_jugada_exploratoria_no_contamina_el_max(self):
        jugadas_no_optimas = 0
        for semilla in range(30):
            tabla = inicializar_tabla()
            busqueda, raiz = self.busqueda_y_raiz(tabla)
            celda = abstraccion.indice(raiz.resumen)
            siguiente = jugar_turno(busqueda, raiz, random.Random(semilla), 1, epsilon=1.0)
            max_q = max(r.q for r in raiz.jugadas)
            assert tabla[celda] == np.float32(max_q)  # lo escrito es max_a, no la jugada jugada
            jugada = next(r for r in raiz.jugadas if any(h is siguiente for _, _, h in r.resultados))
            jugadas_no_optimas += jugada.q < max_q
        assert jugadas_no_optimas > 0  # sí se jugaron jugadas exploratorias


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

    def test_workers_con_exploracion_y_caos(self, tmp_path):
        salida = tmp_path / "prueba.npy"
        entrenar(
            salida, trabajadores=2, iteraciones=5, partidas_por_trabajador=1,
            epsilon=0.5, prob_caos=1.0,
        )  # fmt: skip
        tabla, meta = leer(salida)
        assert meta["partidas"] == 2
        assert (meta["epsilon"], meta["prob_caos"]) == (0.5, 1.0)
        assert celdas_exploradas(tabla) > 0

    def test_el_ritmo_no_cuenta_lo_de_corridas_anteriores(self, tmp_path, capsys):
        salida = tmp_path / "prueba.npy"
        entrenar(salida, trabajadores=2, iteraciones=5, partidas_por_trabajador=8)
        previos = leer(salida)[1]["respaldos"]
        capsys.readouterr()
        entrenar(salida, trabajadores=2, iteraciones=5, partidas_por_trabajador=4,
                 reportar_cada_s=0.3)  # fmt: skip
        de_esta_corrida = leer(salida)[1]["respaldos"] - previos
        ritmos = re.findall(r"\(([\d,]+)/s\)", capsys.readouterr().out)
        assert ritmos, "no hubo ningún reporte"
        # El primer intervalo dura al menos 0.3 s: ritmo × 0.3 no puede pasar de lo hecho.
        assert int(ritmos[0].replace(",", "")) * 0.3 <= de_esta_corrida

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
