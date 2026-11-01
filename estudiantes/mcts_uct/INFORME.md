# Informe: mcts_uct

Bot de práctica del equipo `primer_lugar`: un MCTS clásico con UCT, para tener un rival más
fuerte que `montecarlo` contra el cual medir y entrenar a `primer_lugar`.

## 1. Integrantes
Paris López y Alejandro Martínez (equipo `primer_lugar`).

## 2. Idea en un párrafo
Construimos un árbol de búsqueda en cada turno. En cada iteración bajamos por las jugadas que
equilibran mejor «ha ganado mucho» y «se ha probado poco» (UCB1), probamos una jugada nueva,
jugamos partidas al azar desde ahí y sumamos el resultado a todo el camino. Al acabar el tiempo
jugamos la jugada más visitada.

## 3. Búsqueda (algoritmo y por qué)
UCT (Kocsis y Szepesvári, 2006): MCTS con UCB1 en cada tablero, x̄ + c·√(ln N / n), c = √2.
Respecto a `montecarlo` (de donde se copió) cambia dos cosas: reparte las muestras hacia las
jugadas prometedoras en lugar de por turnos, y mira varias jugadas adelante (también las del
rival, que elige lo mejor para él). Los ataques son nodos de azar: al bajar por un ataque se
tira el dado con su `p` real y cada resultado tiene su propio subárbol. Cada iteración expande
una sola jugada nueva.

## 4. Función de evaluación
4 partidas al azar (`simular_al_azar`) desde la hoja: la fracción que ganan las blancas. Cada
jugada del camino suma esa fracción si la hizo blancas, o 1 − fracción si la hizo negras. Un
tablero terminado vale 1 o 0 sin simular.

## 5. Precomputación (qué y cómo regenerarla)
Nada en `data/`. En `preparar` calentamos numba (`simular_al_azar` y un ataque).

## 6. Manejo del reloj
Igual que `montecarlo`: una reserva del 30 % del reloj inicial que no se gasta pensando y, del
resto, `1/25` de lo disponible por jugada. Si una jugada gana sin importar el dado, se juega al
instante. Si solo queda la reserva, se juega al azar.

## 7. Resultados vs random y montecarlo
Con Docker y el reloj de 30 s: contra `random`, 1 de 1 (3–0, 77 jugadas, reloj máximo 17.7 s).
Contra `montecarlo` (`--semilla 11`, 4 partidas alternando colores), **perdió 1–3**, con reloj
máximo de 19.6 s. Con el reloj de prueba de 3 s se queda sin reloj contra `random`: cada jugada
cuesta ~45 ms de comunicación y la reserva de 0.9 s no alcanza para partidas de ~100 jugadas.

## 8. Qué intentamos y no funcionó
Primera versión; nada descartado todavía.

## 9. Fuentes y uso de IA
Kocsis y Szepesvári (2006), «Bandit based Monte-Carlo Planning», ECML. Browne et al. (2012),
«A Survey of Monte Carlo Tree Search Methods», IEEE TCIAIG. Partimos del `strategy.py` de
`montecarlo` (equipo del curso). Código y pruebas escritos con ayuda de Claude Code.
