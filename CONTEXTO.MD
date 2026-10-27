# Contexto Maestro y Arquitectura: Bot para Breakthrough de Combate
**Metodología:** Specification-Driven Development (SDD) vía Superpowers.
**Restricción Crítica:** CERO REDES NEURONALES[cite: 1].

## 1. Perfil de Dominio Técnico
Superpowers gestionará tu flujo de trabajo metodológico. Tu conocimiento técnico y mentalidad para ejecutar dicho flujo deben regirse por los siguientes principios:
* **Especialidad Fundamental:** Inteligencia Artificial Simbólica, Reinforcement Learning (Q-Learning, Value Iteration) y Monte Carlo Tree Search (MCTS).
* **Filosofía de Ingeniería:** Adopta un enfoque estrictamente analítico y de primeros principios. Rechaza activamente los atajos; prioriza la construcción de estructuras de datos personalizadas y arquitecturas desde cero para tener control absoluto sobre cada byte y ciclo de reloj.
* **Optimización en Python Puro:** Dominio avanzado de la gestión de memoria plana (`multiprocessing.shared_memory`), vectorización y compilación JIT con `numba`[cite: 1] para sortear el GIL y exprimir 12 hilos físicos sin causar un *Out Of Memory* en un entorno con 8 GB de RAM.
* **Rigor y Validación:** Cada componente del Proceso de Decisión de Markov (MDP) debe someterse a *benchmarking* empírico y contar con *suites* de pruebas exhaustivas para casos límite, respaldando la lógica estocástica con pruebas matemáticas sólidas.
* **Alineación Absoluta:** Las reglas descritas en `docs/reglas.md` son inquebrantables y marcan los límites físicos y legales del sistema[cite: 1].

## 2. Límites del Entorno (Fase Online / Torneo)
Estas restricciones aplican EXCLUSIVAMENTE a la ejecución de `strategy.py` durante las partidas de la liga[cite: 1]:
* **CPU:** 1 núcleo físico[cite: 1].
* **Memoria RAM:** 1024 MB máximo[cite: 1].
* **Tiempo de reloj:** 30 segundos en total por partida (estilo ajedrez, solo corre en nuestro turno)[cite: 1].
* **Tiempo de preparación:** 10 segundos para la función `preparar(config)` (fuera del reloj de 30s)[cite: 1].
* **Almacenamiento (Carpeta `data/`):** 100 MB máximo en total[cite: 1]. Solo lectura durante la partida[cite: 1].

## 3. Mecánicas Estocásticas del Dominio
El juego ocurre en un tablero 9x9 con 18 peones por bando[cite: 1]. 
* Los peones atacan en diagonal[cite: 1].
* **Combate:** El ataque se decide mediante la probabilidad $p = 0.5 + 0.15 \times (\text{apoyo}_{\text{atacante}} - \text{apoyo}_{\text{defensor}})$[cite: 1]. 
* **Apoyo:** Cantidad de peones propios en las dos diagonales traseras de la pieza (0, 1 o 2)[cite: 1].
* **Condición de Victoria:** Llegar a 3 puntos (llevando peones a la fila final rival) o dejar al rival sin jugadas[cite: 1]. No hay empates[cite: 1].

## 4. Arquitectura del Sistema Híbrido (100% Python)
Dado el límite de 1 núcleo y 30 segundos por partida en el torneo[cite: 1], resolver el árbol de juego completo en tiempo real es imposible. Dividiremos la arquitectura en dos fases:

### Fase Offline (Entrenamiento en `herramientas/`)
El código en `herramientas/` no se ejecuta en la liga[cite: 1], dándonos libertad para precomputar datos explotando múltiples núcleos.
* **Lenguaje:** Python puro.
* **Restricción de Hardware:** Máximo ~8 GB de RAM disponibles y 12 hilos lógicos. 
* **Paralelismo y Memoria:** Está estrictamente prohibido usar `multiprocessing` estándar para clonar la tabla de valores, ya que causará un Out Of Memory (OOM). Se utilizará `multiprocessing.shared_memory` o arreglos de `multiprocessing.Array` para crear un buffer a nivel de bytes (memoria compartida) donde todos los procesos (workers) actualicen la función de valor simultáneamente.
* **Optimización:** Las rutinas críticas del Proceso de Decisión de Markov (MDP) y cálculos estocásticos deben estar vectorizadas con arreglos de NumPy y aceleradas usando compilación Just-In-Time con `numba`[cite: 1].
* **Salida:** La tabla convergida del Asynchronous Value Iteration se exportará a un archivo binario optimizado (`.pkl` o `.npy`) menor a 100 MB dentro de la carpeta `data/`[cite: 1].

### Fase Online (Inferencia en `strategy.py`)
Solo `strategy.py` se ejecuta en la liga bajo estrictos límites[cite: 1].
* **`preparar(config)`:** Carga el archivo binario desde la carpeta de datos precomputados a un diccionario nativo de Python o un arreglo de NumPy en $O(1)$ dentro del límite de 10 segundos[cite: 1].
* **`jugar(estado, tiempo_restante)`:** Implementa un **Monte Carlo Tree Search (MCTS)**. 
* **Poda y Evaluación:** En la fase de simulación (rollout) del MCTS, truncaremos la búsqueda utilizando los valores precomputados (Value Iteration) para evaluar las hojas de forma instantánea y retropropagar la recompensa, optimizando el reloj de 30 segundos[cite: 1].

## 5. Abstracción del Estado (Reducción de Dimensionalidad)
El espacio de estados $3^{81}$ no cabe en 100 MB[cite: 1]. El simulador en Python mapeará el tablero exacto a la siguiente tupla comprimida $S'$ para el Value Iteration:
1.  **Avance máximo aliado:** Distancia (0-8) a la meta.
2.  **Avance máximo rival:** Distancia (0-8) a nuestra meta.
3.  **Diferencial de material:** (Peones aliados - Peones rivales), rango de -18 a 18[cite: 1].
4.  **Índice de soporte local:** Promedio redondeado (0-3) del apoyo de las 3 piezas más adelantadas.

## 6. Modelo Matemático (Ecuación de Bellman)
Para calcular el valor en Python, usaremos el Proceso de Decisión de Markov:
$$V(s) = \max_a \sum_{s'} P(s'|s,a) \left[ R(s,a,s') + \gamma V(s') \right]$$
*   $P(s'|s,a)$ está dictado estocásticamente por la fórmula de probabilidad de combate[cite: 1].
*   $R(s,a,s')$ recompensará la ganancia de puntos, la supervivencia y penalizará la pérdida de material.

## 7. Flujo de Ejecución bajo Superpowers (SDD)
Antes de generar código, el Agente DEBE:
1.  **Analizar las Especificaciones:** Validar matemáticamente si la tarea asignada viola la memoria, el límite de 100 MB en disco[cite: 1], o la probabilidad de combate[cite: 1].
2.  **Escribir Tests (TDD):** Redactar aserciones lógicas (por ejemplo, asegurar que la probabilidad nunca sea $< 0$ ni $> 1$).
3.  **Generar Código:** Limpio, modular, y documentado, respetando la separación entre la fase offline y la fase online (Python).