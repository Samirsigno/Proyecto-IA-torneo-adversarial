import pytest
import numpy as np

# Claude deberá implementar estas funciones en herramientas/specs.py
from specs import (
    estado_a_indice, 
    calcular_recompensa, 
    calcular_probabilidad_combate
)

class TestAbstraccionEstado:
    
    def test_limite_memoria_100mb(self):
        """Valida que el espacio de estados comprimido no rompa las reglas del torneo."""
        # Máximos teóricos: avance aliado=8, avance rival=8, material=36 (offset de -18 a 18), soporte=2
        max_idx = estado_a_indice(8, 8, 36, 2)
        
        # Si usamos float32, cada índice ocupa 4 bytes
        bytes_totales = max_idx * 4
        megabytes = bytes_totales / (1024 * 1024)
        
        # Límite estricto del torneo es 100MB
        assert megabytes < 100.0, f"Fallo de arquitectura: El arreglo ocupará {megabytes:.2f} MB, excediendo el límite."

    def test_biyectividad_indice_sin_colisiones(self):
        """Valida que cada tupla posible genere un índice 1D estrictamente único."""
        indices_vistos = set()
        total_estados_esperados = 9 * 9 * 37 * 3
        
        for avance_aliado in range(9):
            for avance_rival in range(9):
                for material in range(37):
                    for soporte in range(3):
                        idx = estado_a_indice(avance_aliado, avance_rival, material, soporte)
                        assert idx not in indices_vistos, f"COLISIÓN: El índice {idx} ya fue generado por otra tupla."
                        indices_vistos.add(idx)
                        
        assert len(indices_vistos) == total_estados_esperados, "Faltan estados en el mapeo espacial."

class TestMotorEstocastico:

    def test_probabilidad_combate_limites_estrictos(self):
        """Valida que la fórmula p = 0.5 + 0.15 * (delta) no salga del dominio [0.2, 0.8]."""
        # Mejor escenario: atacante 2, defensor 0
        p_max = calcular_probabilidad_combate(apoyo_atacante=2, apoyo_defensor=0)
        assert np.isclose(p_max, 0.8), f"Límite superior fallido: esperado 0.8, obtenido {p_max}"
        
        # Peor escenario: atacante 0, defensor 2
        p_min = calcular_probabilidad_combate(apoyo_atacante=0, apoyo_defensor=2)
        assert np.isclose(p_min, 0.2), f"Límite inferior fallido: esperado 0.2, obtenido {p_min}"
        
        # Escenario neutro: empates de apoyo
        p_neutro = calcular_probabilidad_combate(apoyo_atacante=1, apoyo_defensor=1)
        assert np.isclose(p_neutro, 0.5), "El escenario de apoyos iguales debe ser exactamente 0.5"

class TestJerarquiaRecompensas:

    def test_victoria_es_suprema(self):
        """La victoria absoluta debe ser superior a cualquier farmeo de jugadas."""
        victoria = calcular_recompensa(delta_puntos=3, delta_material=0, delta_bloqueos=0)
        farmeo_material = calcular_recompensa(delta_puntos=0, delta_material=10, delta_bloqueos=0)
        assert victoria > farmeo_material, "Reward Hacking: El bot prefiere comer piezas que ganar el juego."
        assert victoria == 1000, "La recompensa por victoria debe anclarse en 1000."

    def test_anotar_punto_compensa_perdida_material(self):
        """
        Al llegar a la última fila, se anota 1 punto y el peón sale del tablero.
        Esto significa delta_puntos = +1 y delta_material = -1.
        El neto debe ser fuertemente positivo.
        """
        # +300 por punto
        recompensa_neta = calcular_recompensa(delta_puntos=1, delta_material=-1, delta_bloqueos=0)
        assert recompensa_neta == 300, f"Cálculo de deltas erróneo. Esperado 300, obtenido {recompensa_neta}"