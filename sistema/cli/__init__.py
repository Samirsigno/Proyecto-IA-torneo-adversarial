"""CLI del torneo (`./torneo <comando>`).

Módulos:
- `comandos`: lee los argumentos y corre los comandos de alumnos (`main`).
- `oficial`: la liga oficial (shards y publicación).
- `comun`: lo que comparten: rutas, equipos, Docker o local, liga, impresión.
- `salida`: todo lo que se imprime en la terminal (tablas, avisos, tableros).
- `humano`: jugar tú contra un bot desde la terminal, y el tablero en vivo (`--ver`).
- `imagenes`: imágenes de Docker de los equipos, caché de numba y limpieza.
"""


class ErrorCLI(Exception):
    """Error para el alumno: se imprime tal cual (en español) y el CLI sale con código 2."""


class ErrorEquipo(ErrorCLI):
    """El problema es de la carpeta del equipo (p. ej. su requirements.txt no se instala)."""
