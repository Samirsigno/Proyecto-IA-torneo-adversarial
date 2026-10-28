# Contexto Maestro y Arquitectura: Bot para Breakthrough de Combate
**Metodología:** Specification-Driven Development (SDD) vía Superpowers.

**Restricción Crítica:** CERO REDES NEURONALES[cite: 1].
## ESTADO ACTUAL DEL PROYECTO
* **Fases 1 y 2 (Completadas):** Las abstracciones matemáticas ya están implementadas y validadas.
* **Archivos Protegidos:** `herramientas/test_specs.py` y `herramientas/specs.py` son ahora de **SOLO LECTURA**. Tienes estrictamente prohibido modificarlos bajo ninguna circunstancia. Tu trabajo debe acoplarse a las funciones ya exportadas por estos módulos.

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
* **Paralelismo y Memoria:** Está estrictamente prohibido usar `multiprocessing` estándar para clonar la tabla de valores, ya que causará un Out Of Memory (OOM). Se utilizará un arreglo 1D en `multiprocessing.shared_memory` creando un buffer a nivel de bytes donde todos los procesos (workers) actualicen la función de valor simultáneamente.
* **Optimización:** Las rutinas críticas del Proceso de Decisión de Markov (MDP) y cálculos estocásticos deben estar vectorizadas con arreglos de NumPy y aceleradas usando compilación Just-In-Time con `numba`[cite: 1].
* **Motor de Transiciones:** Las simulaciones *offline* usarán directamente la API del motor oficial (`estado.siguiente(j)`)[cite: 1] para obtener las jugadas legales, los tableros físicos resultantes y sus probabilidades exactas.
* **Memoria:** Se utilizará un arreglo 1D plano en `multiprocessing.shared_memory` de tipo `float32`.
* **Salida:** Al no usar una Q-Table, la tabla de valor ($V$) resultante pesará apenas **~35 KB**, cumpliendo holgadamente el límite de 100 MB en `data/`[cite: 1].

### Fase Online (Inferencia en `strategy.py`)
Solo `strategy.py` se ejecuta en la liga bajo estrictos límites[cite: 1].
* **`preparar(config)`:** Carga el archivo binario desde la carpeta de datos a un arreglo nativo de NumPy en memoria en tiempo $O(1)$ dentro de los 10 segundos de preparación[cite: 1].
* **`jugar(estado, tiempo_restante)`:** Implementa un **Monte Carlo Tree Search (MCTS)**. 
* **Poda y Evaluación:** En la fase de simulación (rollout) del MCTS, truncaremos la búsqueda mapeando el tablero a su índice abstracto y consultando la memoria precomputada para evaluar las hojas de forma instantánea y retropropagar la recompensa, garantizando no agotar el reloj de 30 segundos[cite: 1].

## 5. Abstracción del Estado y Manejo de Memoria Plana
El espacio de estados original ($3^{81}$) es intratable. Para que la memoria compartida converja, mapearemos el tablero exacto a una tupla abstracta $\hat{s} = (x_1, x_2, x_3, x_4)$ utilizando reducción de dimensionalidad:
1.  **$x_1$ (Avance máximo aliado):** Máximo avance aliado(0 a 8).
2.  **$x_2$ (Avance máximo rival):** Máximo avance rival (0 a 8).
3.  **$x_3$ (Diferencial de material):** (Peones aliados - Peones rivales), rango de -18 a 18[cite: 1].
4.  **$x_4$ (Índice de soporte local):** Promedio redondeado del apoyo de las 3 piezas de vanguardia (0 a 2).

**Biyectividad a Índice 1D:**
Para leer/escribir en el bloque de memoria compartida en tiempo $O(1)$, la tupla se codificará en un índice lineal único $i$ usando una suma polinomial de base mixta:
$$i = x_1 \cdot (9 \cdot 37 \cdot 3) + x_2 \cdot (37 \cdot 3) + (x_3 + 18) \cdot 3 + x_4$$
Esto genera un espacio acotado de $8,991$ estados, previniendo colisiones lógicas y asegurando que la huella de memoria sea minúscula.

## 6. Modelo Matemático (Perspectiva Relativa / Negamax)
Entrenaremos una Tabla de Valor pura $V(\hat{s})$, sin abstraer acciones, que evaluará la estructura del tablero **siempre desde la perspectiva del jugador en turno**. 

El entrenamiento fluirá extrayendo los tableros resultantes y sus probabilidades físicas $P(s'|s,a)$ directamente del motor oficial (`estado.siguiente(j)`)[cite: 1], mapeando los destinos a sus índices abstractos, e invirtiendo la perspectiva para evaluar el estado futuro del rival:

$$V(\hat{s}) \leftarrow \max_a \sum_{s'} P(s'|s,a) \left[ R(s, s') - \gamma V(\hat{s}'_{rival}) \right]$$

**Jerarquía Estricta de Recompensas $R(s, s')$ (Deltas):**
Para evitar *Reward Hacking* (ej. farmear piezas sin avanzar) y mantener la estabilidad numérica, las recompensas base están escaladas sobre 1000:
*   Victoria / Derrota absoluta: $+1000$ / $-1000$[cite: 1]
*   Obtener / Recibir 1 punto: $+300$ / $-300$ (Anula la penalización de perder la pieza anotadora)[cite: 1]
*   Comer / Ser comido: $+15$ / $-15$[cite: 1]
*   Bloquear pieza rival (dejarla sin jugadas legales): $+5$ por pieza
*   Apoyo de vanguardia (delta de incremento): $+3$[cite: 1]
*   Avance máximo (delta hacia la fila final): $+2$

## 7. Flujo de Ejecución bajo Superpowers (SDD)
Antes de generar código, el Agente DEBE:
1.  **Analizar las Especificaciones:** Validar matemáticamente si la tarea asignada viola la memoria, el límite de 100 MB en disco[cite: 1], o la probabilidad de combate[cite: 1].
2.  **Escribir Tests (TDD):** Redactar aserciones lógicas (por ejemplo, asegurar que la biyectividad nunca genere colisiones y que $p \in [0.2, 0.8]$).
3.  **Generar Código:** Limpio, modular, documentado en Python puro, y optimizado matemáticamente desde primeros principios.