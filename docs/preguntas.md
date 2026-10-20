# Preguntas frecuentes

### ¿Por dónde empiezo?

Sigue los 3 pasos del [README](../README.md#empieza-en-3-pasos). Luego lee
`estudiantes/montecarlo/strategy.py`: son pocas líneas, comentadas, y marcan con
`AQUÍ PUEDES MEJORAR` dónde hay margen. Juega tú contra él (`./torneo jugar humano montecarlo`) para
entender el juego.

### ¿Qué algoritmo debo usar?

No te lo decimos: investígalo. Todo lo de la unidad de juegos sirve (minimax, alfa-beta,
profundización iterativa, tablas de transposición, expectiminimax, MCTS/UCT) y también sus
variantes. Lo que gana es medir: cambia una cosa, juega muchas partidas, compara.

### ¿Mi bot tiene que recordar el tablero o de qué color es?

No. Cada vez que se llama `jugar` recibes el estado completo (tablero, puntos y turno) y siempre es
tu turno: `estado.turno == config.color`. Puedes guardar cosas en memoria durante la partida si te
sirve (por ejemplo, una tabla de transposición), pero no es necesario.

### ¿Cómo sé si un ataque ganó?

En tu siguiente turno: el `estado` que recibes ya trae el resultado. Antes de atacar sabes la
probabilidad con `estado.prob_ataque(j)`, y `estado.siguiente(j)` te da los dos resultados posibles
con su probabilidad.

### ¿Puedo saber o predecir los dados?

No. Los dados los tira el árbitro con una semilla que se genera al lanzar la liga y que tu bot nunca
ve. `config.semilla` es para tu propio azar (por ejemplo, `random.Random(config.semilla)`) y no
tiene nada que ver con los dados. Intentar adivinarlos o manipularlos es trampa.

### ¿Qué pasa si mi bot se pasa del reloj, lanza un error o regresa una jugada ilegal?

Pierde **esa** partida y sigue en la liga. Lo mismo si se pasa de memoria o si `preparar` tarda más
de 10 s. Ver [docs/probar.md](probar.md#cómo-depurar).

### `./torneo` tarda mucho la primera vez. ¿Es normal?

Sí. La primera vez construye las imágenes de Docker en tu máquina (la primera vez unos minutos) y
prepara numba. Si ves
`Preparando la caché de numba…`, espera: es normal (≈1 min). Después empieza en segundos.

Además, cada partida dura hasta un minuto (30 s de reloj por bot). Mientras programas, usa
`--partidas 1` o `--partidas 2` ([docs/probar.md](probar.md#cuánto-tarda)).

### Algo raro con Docker o después de actualizar el sistema

Corre `./torneo construir`: reconstruye desde cero, en tu máquina, las imágenes del torneo y la
caché de numba (unos minutos). Normalmente no hace falta: `./torneo` reconstruye solo las
imágenes cuando cambia `sistema/`.

### ¿Cómo actualizo el sistema cuando el curso publica una corrección?

Tu repo se creó con «Use this template», así que no recibe las correcciones por sí solo. Tráelas así,
desde la raíz de tu repo privado:

```bash
git remote add curso https://github.com/raya-lucaria/ia_o26_torneo_adversarial.git   # solo la primera vez
git fetch curso
git checkout curso/main -- sistema torneo docker-compose.yml .github .devcontainer docs README.md .gitattributes .gitignore .dockerignore
git commit -m "Actualizo el sistema del curso"
git push
```

> [!WARNING]
> **Nunca** agregues `estudiantes` a ese `git checkout`: podrías sobrescribir tu carpeta
> `estudiantes/<tu_equipo>/`. Copia solo lo que dice el comando.

La siguiente vez que corras `./torneo`, puede tardar un poco más: baja las imágenes nuevas.

### Dice «Docker no responde» o «No encontré Docker».

Abre Docker Desktop y espera a que diga que está corriendo (en Linux: `sudo systemctl start
docker`). En Windows, corre `./torneo` dentro de Ubuntu (WSL2), no en PowerShell. Si no puedes
instalar Docker, usa Codespaces ([docs/empezar.md](empezar.md#codespaces)).

### ¿Por qué mi bot va bien con `--sin-docker` y pierde por reloj con Docker?

`--sin-docker` no tiene límites: tu bot puede usar todos tus núcleos y toda tu memoria. Con Docker
tiene 1 núcleo y 1024 MB, como en la liga. Lo que cuenta es lo que pasa con Docker o en GitHub.

### Mi editor dice que no encuentra `motor`.

Instálalo una vez en tu entorno de Python con `pip install -e sistema`, desde la raíz de tu repo
([docs/avanzado.md](avanzado.md#usar-el-motor-en-tu-editor)). Dentro de `./torneo` siempre
funciona.

### ¿Puedo cambiar el motor?

Sí, pero en una copia dentro de tu carpeta con otro nombre (por ejemplo `mi_motor.py`). El `motor`
instalado no se puede cambiar: es el que usa el árbitro. Ver
[docs/avanzado.md](avanzado.md#modificar-el-motor).

### ¿Puedo usar un modelo entrenado?

Sí, si **no** es una red neuronal: pesos lineales o logísticos, tablas de patrones, árboles de
decisión… Lo entrenas offline, guardas el resultado en `data/` y lo explicas en tu informe. Redes
neuronales no, ni escritas a mano.

### ¿Puedo usar otras librerías?

En la liga: numpy, scipy y numba ya están; otras, con `requirements.txt` y fuera de la lista negra
([docs/avanzado.md](avanzado.md#librerías-requirementstxt)). Offline, para generar `data/`: la que
quieras.

### ¿Puedo usar ChatGPT, Claude, Copilot u otra IA?

Sí, y te lo recomendamos para escribir código. Que la IA escriba código; tú piensa la estrategia.
Dilo en la sección 9 de tu informe. Tú respondes por todo lo que entregas.

### ¿Puedo usar código de internet?

Código genérico (por ejemplo, una implementación de alfa-beta), sí: cítalo en tu informe. Código o
datos de otro equipo, no: es trampa, aunque te lo hayan pasado.

### ¿Podemos ser 3? ¿Puedo trabajar solo?

Los equipos son de exactamente 2. Otro número solo con permiso del profesor.

### ¿Los demás pueden ver mi código?

No, si trabajas en un repo **privado** creado con «Use this template». Un *fork* de un repo público
es público: haz el *fork* solo el día de la entrega ([docs/entregar.md](entregar.md)).

### ¿Puedo cambiar algo fuera de mi carpeta, como arreglar un error en los docs?

En tu repo privado puedes hacer lo que quieras, pero tu pull request solo puede cambiar
`estudiantes/<tu_equipo>/`; si toca algo más, la revisión `revisar-entrega` falla. Si encuentras un
error en el motor o en los docs, avísanos con un *issue*: lo arreglamos para todos.

### ¿Y si empato en puntos con un tier?

No le ganas: «ganarle» es tener **estrictamente** más puntos. Ver
[docs/calificacion.md](calificacion.md#calificación).

### ¿Cómo son los tiers?

Son bots más fuertes, de menor a mayor. Los detalles se anuncian en clase. Su código no se
publica; aparecen el día de la liga y juegan con las mismas reglas y límites que tú. Lo que se
califica es que tu bot juegue bien de verdad: no hay atajo que reemplace pensar la estrategia.

### Tengo una duda que no está aquí.

Pregunta antes de entregar, en un *issue* del repo del torneo o por correo al profesor. Si es de
reglas, la respuesta se publica para todos.
