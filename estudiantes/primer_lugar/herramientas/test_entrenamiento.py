import pytest
import numpy as np

# Claude deberá implementar estas funciones puras en herramientas/entrenamiento.py
# ANTES de escribir el código de concurrencia (multiprocessing)
from entrenamiento import (
    inicializar_tabla,
    calcular_esperanza_bellman,
    fusionar_arreglos
)

# Importamos la abstracción ya validada de la Fase 1
from specs import estado_a_indice, material_a_indice

class TestBootstrappingMemoria:
    
    def test_dimension_y_anclaje_terminal(self):
        """
        Valida que el arreglo plano sea del tamaño exacto (8991) 
        y que los faros de convergencia (+1000 y -1000) estén inyectados.
        """
        tabla = inicializar_tabla()
        
        # 1. Tamaño y tipo de dato estricto para la memoria compartida
        assert tabla.shape == (8991,), "La tabla debe tener exactamente 8,991 índices."
        assert tabla.dtype == np.float32, "Debe ser float32 para optimizar RAM."
        
        # 2. Anclaje de estados terminales
        # Mejor estado posible: max avance, rival en 0, +18 material, max apoyo
        idx_victoria = estado_a_indice(8, 0, material_a_indice(18), 2)
        # Peor estado posible: 0 avance, rival en max, -18 material, 0 apoyo
        idx_derrota = estado_a_indice(0, 8, material_a_indice(-18), 0)
        
        assert tabla[idx_victoria] == 1000.0, "Fallo en Bootstrapping: La victoria absoluta no está anclada en +1000."
        assert tabla[idx_derrota] == -1000.0, "Fallo en Bootstrapping: La derrota absoluta no está anclada en -1000."


class TestEcuacionBellmanNegamax:

    def test_calculo_esperanza_con_perspectiva_relativa(self):
        """
        Prueba matemática pura de la ecuación:
        V(s) = Sum P(s'|s,a) * [ R(s,s') - gamma * V(s'_rival) ]
        """
        gamma = 0.95
        
        # Simulamos un escenario físico devuelto por estado.siguiente(j)
        # Escenario: Atacamos. 80% de ganar la pelea, 20% de perderla.
        prob_exito = 0.8
        recompensa_exito = 15.0 # Comimos pieza
        val_rival_exito = -50.0 # El rival quedó en una posición que para ÉL vale -50
        
        prob_fracaso = 0.2
        recompensa_fracaso = -15.0 # Perdimos nuestra pieza
        val_rival_fracaso = 100.0 # El rival quedó en una posición que para ÉL vale +100
        
        # Simulación de las transiciones entregadas al worker
        transiciones = [
            (prob_exito, recompensa_exito, val_rival_exito),
            (prob_fracaso, recompensa_fracaso, val_rival_fracaso)
        ]
        
        esperanza_calculada = calcular_esperanza_bellman(transiciones, gamma)
        
        # CÁLCULO MANUAL (Primeros Principios):
        # Brazo Éxito: 0.8 * [15.0 - (0.95 * -50.0)] = 0.8 * [15.0 + 47.5] = 0.8 * 62.5 = 50.0
        # Brazo Fracaso: 0.2 * [-15.0 - (0.95 * 100.0)] = 0.2 * [-15.0 - 95.0] = 0.2 * -110.0 = -22.0
        # Total Esperado: 50.0 - 22.0 = 28.0
        esperanza_real = 28.0
        
        assert np.isclose(esperanza_calculada, esperanza_real), \
            f"Error en ecuación Negamax. Se esperaba {esperanza_real}, se obtuvo {esperanza_calculada}"


class TestFederatedLearning:

    def test_fusion_ignora_ceros(self):
        """
        Valida que al fusionar las tablas de dos computadoras, 
        el promedio ignore los estados no explorados (ceros).
        """
        tabla_a = np.zeros(8991, dtype=np.float32)
        tabla_b = np.zeros(8991, dtype=np.float32)
        
        # Escenario 1: Ambos exploraron (se promedia)
        tabla_a[10] = 100.0
        tabla_b[10] = 50.0
        
        # Escenario 2: Solo A exploró
        tabla_a[20] = 100.0
        tabla_b[20] = 0.0
        
        # Escenario 3: Solo B exploró
        tabla_a[30] = 0.0
        tabla_b[30] = 50.0
        
        tabla_maestra = fusionar_arreglos(tabla_a, tabla_b)
        
        assert tabla_maestra[10] == 75.0, "Fallo al promediar valores compartidos."
        assert tabla_maestra[20] == 100.0, "Fallo al heredar valor aislado de A. No debe diluirse con 0."
        assert tabla_maestra[30] == 50.0, "Fallo al heredar valor aislado de B. No debe diluirse con 0."
        assert tabla_maestra[40] == 0.0, "Los estados inexplorados por ambos deben permanecer en 0."