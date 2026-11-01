# Reporte de trabajo — PASO 3: entrenamiento offline (`herramientas/`)

Bitácora de lo que hace el agente en el PASO 3. Rutas relativas a `estudiantes/primer_lugar/`
salvo que se diga otra cosa. Cada entrada dice qué se hizo, con qué evidencia y qué quedó
pendiente.

---

## 2026-10-27 — Sesión 1

### 1. Funciones puras de `herramientas/entrenamiento.py`

- **Estado encontrado:** `entrenamiento.py` ya tenía `inicializar_tabla`,
  `calcular_esperanza_bellman` y `fusionar_arreglos` (commit `9f903d0`). Se revisaron contra
  CONTEXTO.MD §5–§6 y **no se modificaron**.
- **Prueba:** `pytest herramientas/test_entrenamiento.py` → **3 passed**. Toda la carpeta
  `herramientas/` (incluye `test_specs.py`) → **8 passed**.
- **Archivos de solo lectura** (`specs.py`, `test_specs.py`, `test_entrenamiento.py`): sin tocar.

### 2. Entorno de pruebas

- El Python del WSL (3.14) no tiene numpy ni pytest, y le falta `ensurepip` (no se puede crear un
  `.venv` sin `sudo apt install python3.14-venv`). Se creó un `.venv` que quedó roto y se borró
  en el momento; no queda nada en el repo.
- Las pruebas se corren en la imagen del torneo `torneo-base:local` (Python 3.12.15,
  numpy 2.4.6, las mismas versiones que la liga). pytest se instala dentro del contenedor y se
  descarta al salir. Desde la raíz del repo:

  ```bash
  docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 \
    -v "$PWD:/torneo" -w /torneo/estudiantes/primer_lugar torneo-base:local \
    sh -c 'pip install -q --user pytest && python -m pytest -p no:cacheprovider herramientas -v'
  ```

  (El repo se monta en `/torneo` porque la imagen encuentra `motor` con
  `PYTHONPATH=/torneo/sistema`.)

### 3. Decisiones del usuario (respuestas a dos observaciones)

1. **Faros ±1000 de `inicializar_tabla`:** la tabla guarda V, que es un valor esperado; el ±1000
   lo da R al terminar la partida. → Los faros son solo el valor inicial de esas celdas; el
   entrenamiento los puede sobrescribir.
2. **El 0.0 como «no explorado» en `fusionar_arreglos`:** no debe pasar que una celda explorada
   se pierda en la fusión (el programa corre toda la noche). → Una celda visitada nunca se
   guardará como 0.0 exacto.

### 4. Lectura de `docs/` y del motor

- Leídos completos: `docs/reglas.md`, `empezar.md`, `avanzado.md`, `entregar.md`, `probar.md`,
  `calificacion.md`, `preguntas.md`; `sistema/motor/estado.py`, `nucleo.py`, `jugada.py`;
  `sistema/Dockerfile` y `./torneo`.
- Hallazgos que afectan al entrenamiento:
  - **Con al menos un peón siempre hay jugada legal**: el peón más avanzado siempre puede ir en
    diagonal (la casilla está vacía o tiene un rival, y no puede tener uno propio más avanzado).
    Así que «dejar al rival sin jugadas» solo ocurre cuando el rival se queda sin peones.
  - La imagen del torneo guarda la caché de numba en `/tmp/numba`, que se pierde con cada
    contenedor; para el entrenamiento conviene apuntarla a `resultados/.cache/` (ignorada por
    git).
  - Esta máquina: 12 CPUs y 7.4 GB de RAM disponibles para Docker.

### 5. Archivos creados (sin commit)

- `herramientas/test_abstraccion.py`: pruebas (TDD) para el módulo `abstraccion.py`, que todavía
  **no existe**. Aún no se han corrido; fallarán al importar `abstraccion`. Casos, con valores
  calculados a mano sobre los ejemplos de `docs/reglas.md`:
  - tupla ŝ de la posición inicial, del ejemplo 3 de combate, de un tablero sin peones rivales,
    del redondeo del soporte y desde la perspectiva de Negras;
  - R(s, s') del ejemplo 3 (ataque gana: +14; pierde: −20), anotar caminando (+288), tercer
    punto (+1000), comer el último peón (+1000), perder el último peón (−23) y bloquear un peón
    rival (+7);
  - propiedades sobre partidas al azar: el tablero reflejado (colores cambiados) da la misma
    tupla y la misma R, y el fin de partida coincide con `estado.ganador()` del motor.

  Estas pruebas fijan las interpretaciones de la sección 7 (avance, vanguardia, redondeo). Si
  el usuario decide otra cosa, se ajustan.

### 6. Para qué es `abstraccion.py` (explicación pedida por el usuario)

Para entrenar (CONTEXTO §6), cada tablero s' que devuelve `estado.siguiente(j)` hay que:
(a) convertirlo a la tupla ŝ' = (x1, x2, x3, x4) para leer V(ŝ'_rival) en la tabla, y
(b) calcular R(s, s') con los deltas de puntos, material, bloqueos, soporte y avance.

`specs.py` tiene la segunda mitad de cada paso: tupla → índice (`estado_a_indice`) y deltas →
recompensa (`calcular_recompensa`). **Falta el puente desde el tablero del motor**: nada en el
repo calcula hoy x1–x4 ni los deltas a partir de un `Estado`. Eso es `abstraccion.py`.

Por qué un archivo aparte en la raíz del equipo y no dentro de `herramientas/entrenamiento.py`:

- `strategy.py` (el MCTS de la liga) necesita **exactamente la misma** función tablero → índice
  para consultar V en las hojas (CONTEXTO §4: «mapeando el tablero a su índice abstracto»).
- El código de la liga no puede importar `herramientas/` (por eso `specs.py` vive en la raíz).
- Si la función viviera en `entrenamiento.py`, `strategy.py` tendría que copiarla. Si las dos
  copias difieren en un detalle (por ejemplo, el desempate de la vanguardia), el bot leería V en
  celdas equivocadas sin ningún error visible.
- `specs.py` es de solo lectura, así que no puede ir ahí.

Contenido previsto: `rasgos(tablero, color)` compilada con numba (avance máximo, soporte de
vanguardia, número de peones y peones bloqueados de un color), y funciones para obtener la tupla
y el índice desde quien tiene el turno, el resultado de la partida (GANA/SIGUE/PIERDE) y R(s, s')
llamando a `specs.calcular_recompensa`.

### 7. Preguntas abiertas (CONTEXTO.MD no las resuelve)

1. **Avance x1, x2 («0 a 8»).** Propuesta: número de fila propia del peón más avanzado (1 = fila
   de fondo, 8 = a un paso de anotar), y 0 si no quedan peones. Alternativa: filas recorridas
   (0 a 7); con esa, el 8 nunca ocurre (un peón en la última fila ya anotó y salió) y la celda
   del faro de victoria (8, 0, +18, 2) nunca se visita.
2. **Vanguardia x4.** Propuesta: los 3 peones más avanzados; empates por columna (a → i); con
   menos de 3 peones, el promedio de los que haya; 0 sin peones; un .5 se redondea hacia arriba
   (solo pasa con 2 peones).
3. **Regla de actualización «←».** Muchos tableros reales caen en la misma celda ŝ. Propuesta:
   V(ŝ) ← V(ŝ) + α·(objetivo − V(ŝ)), con α = max(1/n, α_min) y n = visitas de la celda: la primera
   visita reemplaza el valor inicial, luego promedia, y al final es una media móvil. Alternativa:
   asignación directa (V salta al valor del último tablero visto).
4. **Qué tableros visitan los workers.** Propuesta: partidas contra sí mismos desde la posición
   inicial; en cada turno, respaldo de Bellman del tablero actual y jugada ε-greedy según las Q
   calculadas; los ataques se resuelven con la p del motor.
5. **Hiperparámetros por omisión:** γ = 0.95 (el del test), α_min = 0.01, ε = 0.1.

Interpretaciones que se toman tal cual de CONTEXTO.MD (no requieren respuesta salvo objeción):
el delta de bloqueos cuenta peones **rivales** sin jugadas; el delta de soporte y el de avance
son los del jugador que movió.

### Estado al cierre de esta entrada

Detenido a petición del usuario, esperando respuesta a las secciones 6 y 7. Nada commiteado.

---

## 2026-10-27 — Sesión 1 (continuación)

### 8. Respuestas del usuario a la sección 7

1. **Avance x1, x2:** referencia al peón más alto: 0 en la fila de fondo, 8 en la fila final.
   → Avance = filas recorridas. En el tablero llega a 7 (en la 8 el peón anota y sale). Sin
   peones también es 0.
2. **Vanguardia x4:** como se propuso (3 más avanzados, empate por columna a → i, .5 hacia
   arriba).
3. **Actualización de V:** la ecuación se queda tal cual; **asignación directa**
   V(ŝ) ← max_a Σ P·[R − γ·V(ŝ'_rival)]. No hay α.
4. **Qué tableros visitan los workers:** se usará **MCTS**, sin ε-greedy; los workers corren y se
   comunican con la tabla compartida para irla construyendo.
5. **Hiperparámetros:** γ = 0.95. α y ε no existen en este problema.

Se releyeron `CONTEXTO.MD` y `docs/reglas.md` a petición del usuario.

### 9. `abstraccion.py` (raíz del equipo) — hecho con TDD

- **Pruebas** `herramientas/test_abstraccion.py`, ajustadas a la definición de avance de la
  respuesta 1 (valores recalculados a mano: la posición inicial es (1, 1, 18, 2); perder el
  último peón desde e4 vale −15 − 6 = −21).
- **RED:** `ModuleNotFoundError: No module named 'abstraccion'` (el módulo no existía).
- **Implementación:**
  - `rasgos(tablero, color)` (numba): avance máximo, soporte de vanguardia, peones y peones
    bloqueados de un color. Usa `apoyo` y `paso` del motor oficial (`motor.nucleo`), así que las
    reglas de apoyo no se duplican.
  - `resumir(estado)`: lee los atributos internos `_tablero`, `_puntos` y `_color` del motor
    (el motor no expone el arreglo; son de solo lectura).
  - `tupla`, `indice` (desde quien tiene el turno), `resultado` (GANA/SIGUE/PIERDE) y
    `recompensa(antes, despues)`, que llama a `specs.calcular_recompensa`.
- **GREEN:** 15/15. Toda la carpeta `herramientas/` (specs + entrenamiento + abstracción):
  **23 passed**.
- **Prueba de que los tests detectan errores** (mutación): con el redondeo cambiado a «hacia
  abajo» fallan 6 tests; con la fila negra sin reflejar fallan 7. Se restauró el archivo
  (verificado con `cmp`).
- **Benchmark** (Docker, 1 núcleo, tablero de medio juego con 30 jugadas legales):

  | Operación | Costo |
  |---|---|
  | `rasgos` (numba, 1 color) | 0.8 µs |
  | `resumir` | 3.6 µs |
  | `indice` | 1.2 µs |
  | `estado.siguiente(j)`, 1 jugada | 5.2 µs |
  | Respaldo de Bellman completo (30 jugadas, todos los s') | 500 µs |

  Un respaldo cuesta ~0.5 ms: ~2 000 por segundo por worker, ~24 000/s con 12 workers.

### 10. Preguntas abiertas sobre el MCTS de los workers

CONTEXTO.MD §4 describe el MCTS solo para la liga. Se preguntó al usuario cómo se usa en los
workers (qué celdas escriben, si es el mismo código que `strategy.py`, cuánto busca por jugada y
cómo trata los ataques).

### 11. Respuestas del usuario sobre el MCTS

1. **Qué se escribe en V:** todos los nodos que el MCTS expande reciben su respaldo de Bellman.
2. **Código:** un solo `mcts.py` en la raíz del equipo, el mismo para los workers y para
   `strategy.py`.
3. **Presupuesto en entrenamiento:** 200 iteraciones fijas por jugada.
4. **Ataques:** esperanza exacta con p (los dos resultados cuentan en Q).

### 12. `mcts.py` (raíz del equipo) — hecho con TDD

- **Pruebas** `herramientas/test_mcts.py` (valores a mano): Q(e4-f5) del ejemplo 3 = 2.1 con la
  tabla en 0 y −7.4 con la tabla en 10; un s' terminal no lee la tabla (Q = 252 con la tabla en
  500); se avisa cada expansión con su valor; la búsqueda cuenta sus iteraciones; encuentra el
  tercer punto con la tabla en 0, −1000 y +1000; los resultados de un ataque se visitan en
  proporción a p (13 y 7 de 20 con p = 0.65).
- **RED:** `ModuleNotFoundError: No module named 'mcts'`. **GREEN:** 7/7.
- **Mutación:** con el signo de γ·V invertido en la ecuación de Bellman fallan 2 tests.
- **Diseño:**
  - **Expansión = respaldo de Bellman.** Se generan todos los s' con `estado.siguiente(j)` y cada
    uno vale V(ŝ'_rival) de la tabla (0 si la partida terminó: el ±1000 viene en R). Cada jugada
    queda con Q = Σ p·[R − γ·valor(s')], y el nodo vale max Q, que se avisa con `al_expandir`.
  - **Selección:** UCT, Q/1000 + √2·√(ln N / (n + 1)). En un ataque se baja al resultado con
    mayor p / (visitas + 1).
  - **Retropropagación:** en cada ancestro se recalcula el Q de la jugada recorrida y el máximo.
  - **Jugada elegida:** la de mayor Q (con empate, la más visitada).
- `calcular_esperanza_bellman` se **movió** de `herramientas/entrenamiento.py` a `mcts.py`,
  porque el código de la liga no puede importar `herramientas/`. `entrenamiento.py` la
  reexporta: `test_entrenamiento.py` (solo lectura) no se tocó y sigue pasando.

### 13. Workers en paralelo (`herramientas/entrenamiento.py`) — hecho con TDD

- **Pruebas** `herramientas/test_trabajadores.py`:
  - **Escritura protegida** (respuesta 2 de la sección 3): un 0.0, o un valor que en float32 se
    vuelve 0, se guarda como el mínimo positivo de float32 (1.2e−38). La fusión ya no pierde esa
    celda: (0 + 50) / 2 = 25, no 50.
  - **Integración con procesos reales:** 2 workers construyen la tabla. Reanudar suma partidas y
    no borra lo explorado. `desde_cero` ignora lo guardado. `--horas` se detiene y guarda. No
    queda memoria compartida en `/dev/shm`.
- **RED:** `ImportError: cannot import name 'MINIMO_EXPLORADO'`. **GREEN:** carpeta completa
  **39 passed**, sin avisos de memoria compartida filtrada en la salida de los procesos.
- **Diseño:**
  - **Memoria compartida:** la tabla V es un bloque float32[8 991] de 35 964 bytes. Aparte, un
    bloque int64 con los contadores de cada worker (respaldos, partidas, listo); cada worker
    escribe solo su fila. Los workers se conectan por nombre y nadie copia la tabla.
  - **Procesos:** `multiprocessing` con `spawn`. Cada worker ignora Ctrl+C (lo atiende el
    principal) y juega contra sí mismo desde la posición inicial: 200 iteraciones de MCTS por
    jugada, con el subárbol reusado entre jugadas. El dado de los ataques sale de su propio
    generador con la p del motor.
  - **Escritura:** cada expansión asigna `V(ŝ) ← max_a Q` directo en la tabla compartida, sin
    candados. Escribir un float32 alineado es atómico.
  - **Proceso principal:** reporta cada 60 s (partidas, respaldos por segundo, celdas exploradas
    y cambio medio de V). Guarda cada 5 min de forma atómica (escribe un temporal y lo
    renombra). Al recibir Ctrl+C / SIGTERM, o al cumplir `--horas` (que se cuentan desde que
    todos los workers están listos), detiene a los workers, guarda y libera la memoria.
  - **Reanudar:** si `herramientas/tablas/<etiqueta>.npy` existe, continúa desde ahí.
- **Lanzador** `herramientas/entrenar.sh`: corre `entrenamiento.py` en la imagen
  `torneo-base:local`. Monta el repo en `/torneo`, usa la caché de numba en
  `resultados/.cache/` y la etiqueta es el usuario del sistema (`whoami`).

### 14. Prueba real: 12 workers en esta máquina (Docker)

Corrida de 2 min 46 s detenida con SIGINT (`timeout -s INT`):

| Medida | Valor |
|---|---|
| Respaldos por segundo (12 workers) | 5 500 – 5 800 |
| Partidas completas | 58 (~21 por minuto) |
| Celdas exploradas | 864 al minuto 1, 955 al minuto 2 |
| Cambio medio de V entre reportes | 119.4 → 87.4 (bajando) |
| Memoria del contenedor (a los 100 s) | 923 MiB (≈ 70 MiB por worker) |
| CPU | 1 316 % (los 12 hilos ocupados) |
| Tamaño de la tabla guardada | 36 092 bytes |

- Ctrl+C / SIGINT detuvo, guardó y dejó `/dev/shm` limpio.
- Proyección para 8 horas: ~10 000 partidas y ~160 millones de respaldos.
- Los archivos de esta prueba (`tablas/prueba_humo.*`) se borraron.

### 15. Decisiones que tomó el agente sin preguntar

- **Constante de UCT:** √2 sobre Q normalizado por 1000. Es la constante clásica de UCT; con
  200 iteraciones y ~30 jugadas la búsqueda resulta más ancha que profunda.
- **Jugada que se juega:** la de mayor Q (con empate, la más visitada), porque los Q son
  esperanzas exactas con máximo, no promedios muestreados.
- **Resultados de un ataque:** se visitan en proporción a p, de forma determinista.
- **Reuso del subárbol** entre jugadas de la misma partida.
- **Faros:** con el avance de la respuesta 1, un peón en el tablero llega a lo más a 7. Las dos
  celdas de faros (x1 = 8 o x2 = 8) nunca se visitan: se quedan en ±1000 y no afectan nada.
- **Si un worker falla**, los demás siguen; se avisa en el momento y, al final, `entrenar` lanza
  un error después de guardar la tabla.
- **Revisión final:** la hizo el mismo agente (no un revisor nuevo), así que es más débil que
  una revisión independiente. Corrigió dos detalles: los manejadores de señales se instalaban
  antes de crear la memoria compartida (si fallaba, no se restauraban), y la fecha del `.json`
  no decía su zona horaria (el contenedor está en UTC).

### 16. Cómo correr el entrenamiento (para el compañero)

```bash
git fetch && git checkout paso-1-specs && git pull
./torneo construir          # solo si nunca has corrido ./torneo (crea la imagen torneo-base:local)
estudiantes/primer_lugar/herramientas/entrenar.sh --horas 8
```

- Usa todos los núcleos que tenga Docker (`--workers N` para usar menos) y unos 70 MB por
  worker.
- Cada 5 minutos guarda en `estudiantes/primer_lugar/herramientas/tablas/<tu usuario>.npy` y
  `.json`. Ctrl+C guarda antes de salir; si lo vuelves a correr, continúa donde se quedó.
- Que la computadora no se suspenda en la noche. En Mac:
  `caffeinate -i estudiantes/primer_lugar/herramientas/entrenar.sh --horas 8`.
- Al terminar, sube la tabla para fusionarla con las de las demás máquinas:
  `git add estudiantes/primer_lugar/herramientas/tablas/ && git commit -m "Tabla V de <nombre>" && git push`.

### 17. ¿Más RAM o más workers aceleran el entrenamiento? (pregunta del usuario)

- **Máquina:** Ryzen 5 7535HS (6 núcleos físicos, 12 hilos) con 15.3 GB de RAM. WSL2 recibe la
  mitad de la RAM (7.4 GB, porque no hay `.wslconfig`) y los 12 hilos.
- **Benchmark** (Docker, 72 s por corrida, `--desde-cero`, archivos borrados al terminar):

  | Workers | Respaldos/s | Partidas | Memoria | CPU |
  |---|---|---|---|---|
  | 6 | 3 831 | 19 | 494 MiB | 605 % |
  | 12 | 5 289 | 18 | 922 MiB | 1 268 % |
  | 24 | 5 064 | 9 | 1.7 GiB | 1 281 % |

- **Conclusión:** el límite es la CPU, no la RAM. Con 12 workers, uno por hilo, se obtiene el
  máximo; los hilos «extra» del hyperthreading dan un 38 % más que 6. Con 24, la memoria se
  duplica y el ritmo baja un 4 %. Más RAM para WSL no acelera el entrenamiento.
- **Lo que sí aumenta el trabajo en paralelo:** más máquinas corriendo `entrenar.sh`, cada una
  con su etiqueta, y fusionar sus tablas con `fusionar_arreglos`. Otra vía sería expandir los
  nodos en numba sobre el arreglo del tablero en lugar de con objetos `Estado`, pero CONTEXTO §4
  pide usar `estado.siguiente(j)`: es decisión del usuario.

### 18. Exploración off-policy: ε-greedy y tableros caóticos (pedido del usuario)

- **Motivo (dicho por el usuario):** la tabla se estancó en ~1 067 celdas exploradas; los
  workers caen en óptimos locales. **Esto cambia la decisión de la sección 8, respuesta 4**
  («no hay necesidad de ε-greedy»).
- **Diseño aprobado** (cambio acotado; solo `herramientas/entrenamiento.py` y sus pruebas, sin
  tocar `mcts.py`, `strategy.py` ni los archivos de specs). El usuario pidió ε = 0.3 y 20 % de
  caos; al aprobar lo cambió a **ε = 0.1** y **5 % de caos / 95 % posición inicial**.
  - **Turno del worker** (`jugar_turno`): (1) `buscar` del MCTS, que en cada expansión escribe
    `V(ŝ) ← max_a Q` sobre todas las jugadas legales; (2) `elegir_rama`: con probabilidad ε
    una jugada legal al azar y si no la de mayor Q; (3) el dado del ataque.
  - **Por qué la jugada al azar no contamina el max_a:** el paso (2) llega cuando la tabla ya
    está escrita, solo elige a qué tablero avanzar y no escribe nada. Los valores que el MCTS
    recalcula al retropropagar se quedan en memoria del árbol: a la tabla solo se escribe al
    expandir.
  - **`generar_tablero_aleatorio`:** de 2 a 18 peones por bando en casillas al azar, sin
    peones en la fila donde anotarían, turno 50/50 y 0 a 0 en puntos. Nunca es terminal.
  - **`tablero_de_inicio`:** cada partida empieza en un tablero caótico con probabilidad 5 %.
  - Los números aleatorios salen del generador con semilla de cada worker, no del módulo global
    `random`.
  - Opciones nuevas `--epsilon` y `--caos` (0 y 0 vuelven al comportamiento anterior). El `.json`
    guarda `epsilon` y `prob_caos`.
- **Pruebas (TDD), en `test_trabajadores.py`:**
  - **Tablero aleatorio:** 500 muestras; rangos de 2 a 18 peones, filas permitidas, nunca
    terminal, los dos turnos y todos los tamaños.
  - **Inicio:** 4 000 sorteos al 5 %.
  - **ε-greedy:** ε = 0 juega siempre la mejor; ε = 1 llega a todas las jugadas legales.
  - **No contaminación:** con ε = 1, 30 semillas: la celda de la raíz vale exactamente el
    max_a Q aunque se juegue otra jugada, y sí hubo jugadas no óptimas.
  - **Integración:** workers reales con ε = 0.5 y 100 % de caos.
  - **RED:** `ImportError: cannot import name 'elegir_rama'`. **GREEN:** carpeta completa
    **45 passed**.
  - **Mutación:** si `elegir_rama` ignora ε, fallan 2 tests. Se restauró el archivo (`cmp`).
- **Advertencias dichas al usuario:** (a) con asignación directa, un tablero caótico que cae en
  la misma celda que uno real sobrescribe su valor; (b) como el avance 8 nunca aparece en el
  tablero, a lo más hay 8·8·37·3 = 7 104 celdas alcanzables, y muchas no ocurren en partidas
  reales.

### 19. Corrida de 7 horas (2026-10-27, 23:57)

- **Respaldo previo** (copia idéntica, verificada con `cmp`):
  `herramientas/tablas/respaldos/alexs_2026-10-27_2357.npy` y `.json`. Contenía 185 partidas y
  12 251 498 respaldos, entrenados con 800 iteraciones.
- **Comando** (desacoplado de la terminal con `setsid nohup`, así que sigue aunque se cierre VS
  Code):
  `entrenar.sh --horas 7 --epsilon 0.1 --caos 0.05 --iteraciones 800`. Continúa desde
  `tablas/alexs.npy`. Se mantuvieron las 800 iteraciones de la corrida anterior del usuario.
- **Log:** `resultados/entrenamiento_2026-10-27_2357.log`.
- **Detenerla antes de tiempo** (guarda al salir):
  `docker stop -t 60 $(docker ps -q --filter ancestor=torneo-base:local)`.
- **Primeros reportes:** a los 1, 2 y 3 minutos, 1 197 → 1 200 → 1 200 celdas exploradas
  (antes ~1 067). Ritmo de 4 500 a 4 800 respaldos/s. Memoria 1.2 GiB, CPU 1 323 %.
- **Error encontrado y corregido:** al reanudar, el ritmo del primer reporte contaba los
  respaldos de las corridas anteriores (salió 208 487/s; en realidad eran ~4 850/s). Solo afecta
  esa línea del log, no al entrenamiento. Prueba nueva
  `test_el_ritmo_no_cuenta_lo_de_corridas_anteriores`. **RED:** 22 702/s × 0.3 s > 5 043
  respaldos hechos. **GREEN:** carpeta completa **46 passed**. La corrida en curso conserva el
  código anterior (el error solo estaba en su primera línea).
- **Cancelada a petición del usuario** a los 6 minutos, para correrla él en su terminal.
  `docker stop -t 60` la detuvo limpia: guardó `alexs.npy` con 204 partidas, 13 940 444
  respaldos y 0:38:42 de entrenamiento acumulado. No quedó ningún proceso vivo ni memoria
  compartida en `/dev/shm`.
- **Corrida del usuario en su terminal** (2026-10-28 00:09, mismos parámetros). A las 00:21 el
  usuario creyó que se había detenido. Se revisó y **seguía corriendo**: contenedor activo
  desde hacía 17 min, CPU 1 209 %, 1.2 GiB, y el último guardado a las 00:19 (247 partidas,
  16.9 M respaldos). Solo se consultó, no se cambió nada.
- Código de esta sección sin commit.

### 20. Docker no respondía: revisión del entorno de entrenamiento (2026-10-31)

- **Causa:** Docker Desktop no estaba abierto en Windows. No había ningún proceso de Docker y el
  enlace `/usr/bin/docker → /mnt/wsl/docker-desktop/...` estaba roto (esa carpeta solo existe
  mientras Docker Desktop corre). WSL respondía «docker could not be found in this WSL 2
  distro».
- **Arreglo:** se abrió `Docker Desktop.exe` desde WSL. El daemon respondió a los ~8 s (cliente
  y servidor 29.1.3, 12 CPUs, 7.4 GiB).
- **Verificado:**
  - La imagen `torneo-base:local` existe y no había ningún contenedor ni bloque `psm_` en
    `/dev/shm`.
  - `tablas/alexs.npy` es float32 de (8991,), sin NaN ni inf, con 2 064 celdas distintas de
    cero y rango [−1 138.6, 1 377.4]. Lleva 4 230 partidas y su último guardado fue el
    2026-10-28 a las 22:56 UTC. Ese avance aún no tiene commit.
  - Las pruebas en Docker dan **46 passed**. pytest no viene en la imagen: el ayudante del
    agente lo instala en cada corrida, dentro del contenedor.
  - **Prueba de humo** de `entrenar.sh --etiqueta prueba_humo --horas 0.006 --workers 12`:
    3 partidas y 141 938 respaldos en 21.7 s (~6 500/s). Guardó y salió limpio.
  - `alexs.npy` quedó intacta (mismo sha256 antes y después). La tabla de prueba se borró.
- **Para entrenar:** abrir Docker Desktop antes de correr
  `estudiantes/primer_lugar/herramientas/entrenar.sh`.

### 21. Bot de práctica `estudiantes/mcts_uct` (UCT clásico) — hecho con TDD (2026-11-01)

- **Origen:** copia de `estudiantes/montecarlo`. `montecarlo_naive` solo tenía carpetas vacías.
  Es independiente de `primer_lugar`: no usa la tabla V.
- **Algoritmo** (`strategy.py`):
  - Selección con UCB1, c = √2.
  - Los ataques son nodos de azar: el dado se tira con la `p` real y cada resultado tiene su
    propio subárbol.
  - Expansión de una jugada nueva por iteración, en orden al azar.
  - Simulación con 4 partidas de `simular_al_azar`.
  - Retropropagación: cada jugada suma la fracción que ganó quien la hizo.
  - Juega la jugada más visitada.
  - El reloj se reparte como en `montecarlo` (reserva del 30 % y 1/25 por jugada).
  - `preparar` calienta numba, también con un ataque.
- **Pruebas** (`herramientas/test_strategy.py`, 8):
  - La fórmula UCB1.
  - Las visitas cuadran entre raíz, ramas e hijos.
  - Prueba cada jugada antes de repetir.
  - El dado de un ataque con p = 0.65 da 2 500–2 700 de 4 000.
  - Un nodo terminal no se expande.
  - Cada color anota su tercer punto antes de que lo anote el rival.
  - `jugar` regresa una jugada legal dentro de su presupuesto.
  - Sin tiempo contesta al instante.
- **RED:** ImportError. **GREEN:** 8 passed.
- **Corrección de una prueba:** la primera versión esperaba solo `e8-e9`. También anotan
  `e8-d9` y `e8-f9`, y en esa posición todas las jugadas ganaban. Se cambió a una posición
  donde ambos amenazan el tercer punto y se acepta cualquier jugada que anote.
- **Mutación:** invertir la perspectiva en la retropropagación hace fallar esa prueba.
- **`./torneo validar mcts_uct`:** pasa. Avisa ⚠ que se queda sin reloj con los 3 s de prueba:
  cada jugada cuesta ~45 ms de comunicación y la reserva de 0.9 s no alcanza para ~100
  jugadas. Con 30 s, la reserva de 9 s alcanza para ~200.
- **Partidas con 30 s:**
  - Contra `random`: ganó 1 de 1, 3–0, con unas 3 500 iteraciones por jugada al inicio.
  - Contra `montecarlo` (`--semilla 11`, 4 partidas): **perdió 1–3**, con reloj máximo de
    19.6 s.
- `equipo.toml` usa a los integrantes de `primer_lugar`.
- Sin commit.

### Pendiente

- Comando para fusionar las tablas de las dos máquinas (`fusionar_arreglos` ya existe) y dejar
  el resultado en `data/`.
- `strategy.py` con `mcts.py` y un límite por tiempo para la liga.
- `CONTEXTO.MD` tiene un cambio del usuario (ruta de `specs.py`) que no se incluyó en el commit
  del agente.
