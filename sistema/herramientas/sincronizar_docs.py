"""Escribe en los docs las tablas de límites y calificación a partir de los TOML.

Uso (desde la carpeta sistema/):
    python -m herramientas.sincronizar_docs              # reescribe README.md y docs/*.md
    python -m herramientas.sincronizar_docs --verificar  # solo revisa; sale con 1 si difieren

Cada tabla vive entre dos marcadores que no se ven en GitHub:
    <!-- limites:inicio -->       ...      <!-- limites:fin -->
    <!-- calificacion:inicio -->  ...      <!-- calificacion:fin -->
Lo que está entre ellos se reemplaza; el resto del archivo no se toca.
Así los docs nunca dicen otra cosa que `limites.toml` y `calificacion.toml`.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from config import RAIZ, SISTEMA, cargar_calificacion, cargar_limites
from liga.calificacion import CALIFICACION_TOP


def _n(valor: float) -> str:
    return f"{valor:g}"


def tabla_limites() -> str:
    """Tabla de límites públicos (el bot siempre ve el reloj publicado)."""
    li = cargar_limites(SISTEMA / "limites.toml")
    filas = [
        ("Reloj", f"{_n(li.reloj_s)} s por partida, estilo ajedrez: solo corre en tu turno"),
        ("`preparar` (incluye importar `strategy.py`)", f"{_n(li.preparar_s)} s, fuera del reloj"),
        ("CPU", "1 núcleo"),
        ("Memoria", f"{li.memoria_mb} MB"),
        ("Tu carpeta", f"{li.carpeta_mb} MB en total y {li.archivo_mb} MB por archivo"),
        ("Lo que imprimes (`print`)", f"se guarda hasta {li.salida_kb} KB por partida"),
        ("Librerías de `requirements.txt`", f"{li.requirements_mb} MB instalados"),
    ]
    lineas = ["| Recurso | Límite |", "|---|---|"]
    lineas += [f"| {recurso} | {limite} |" for recurso, limite in filas]
    return "\n".join(lineas)


# Lo único que se publica de cada participante del curso.
_DESCRIPCIONES = {
    "random": "`random` (juega al azar)",
    "montecarlo": "`montecarlo` (Monte Carlo plano)",
}


def _descripcion(rival: str) -> str:
    if rival in _DESCRIPCIONES:
        return _DESCRIPCIONES[rival]
    if rival.startswith("tier_"):
        return f"Tier {rival.removeprefix('tier_')}"
    return f"`{rival}`"


def tabla_calificacion() -> str:
    """Tabla «mejor bot de referencia al que le ganas → calificación»."""
    notas = cargar_calificacion(SISTEMA / "calificacion.toml")
    lineas = [
        "| Mejor bot de referencia al que le ganas (`random`, `montecarlo` o un tier) "
        "| Calificación |",
        "|---|---|",
        "| ninguno | 0 |",
    ]
    lineas += [f"| {_descripcion(r)} | {_n(nota)} |" for r, nota in notas.items()]
    lineas.append(f"| **Lugares 1, 2 y 3 entre equipos de alumnos** | **{_n(CALIFICACION_TOP)}** |")
    return "\n".join(lineas)


TABLAS: dict[str, Callable[[], str]] = {
    "limites": tabla_limites,
    "calificacion": tabla_calificacion,
}


def _reemplazar(texto: str, inicio: str, fin: str, tabla: str) -> str:
    """Reemplaza lo que hay entre cada par inicio/fin. ValueError si un par está mal puesto."""
    if texto.count(inicio) != texto.count(fin):
        raise ValueError(f"Marcadores sin pareja: cada {inicio} necesita su {fin}.")
    partes, pos = [], 0
    while (i := texto.find(inicio, pos)) != -1:
        f = texto.find(fin, i)
        otro = texto.find(inicio, i + len(inicio))
        if f == -1 or (otro != -1 and otro < f):
            raise ValueError(f"{inicio} no tiene su {fin} después.")
        if texto.find(fin, pos, i) != -1:
            raise ValueError(f"{fin} aparece antes de su {inicio}.")
        if not texto.startswith("\n", i + len(inicio)) or texto[f - 1] != "\n":
            raise ValueError(f"{inicio} y {fin} deben ir cada uno en su propia línea.")
        partes += [texto[pos:i], f"{inicio}\n{tabla}\n{fin}"]
        pos = f + len(fin)
    if texto.find(fin, pos) != -1:
        raise ValueError(f"{fin} aparece antes de su {inicio}.")
    return "".join(partes) + texto[pos:]


def sincronizar(texto: str) -> str:
    """El texto con cada tabla entre sus marcadores regenerada. ValueError si están mal puestos."""
    for nombre, generar in TABLAS.items():
        inicio, fin = f"<!-- {nombre}:inicio -->", f"<!-- {nombre}:fin -->"
        texto = _reemplazar(texto, inicio, fin, generar())
    return texto


def archivos() -> list[Path]:
    return [RAIZ / "README.md", *sorted((RAIZ / "docs").glob("*.md"))]


def verificar() -> list[Path]:
    """Archivos cuyas tablas no coinciden con los TOML."""
    desactualizados = []
    for ruta in archivos():
        texto = ruta.read_text(encoding="utf-8")
        if sincronizar(texto) != texto:
            desactualizados.append(ruta)
    return desactualizados


def main(argv: list[str]) -> int:
    if "--verificar" in argv:
        malos = verificar()
        for ruta in malos:
            print(f"Desactualizado: {ruta.relative_to(RAIZ)}", file=sys.stderr)
        if malos:
            print(
                "Corre `python -m herramientas.sincronizar_docs` desde sistema/.", file=sys.stderr
            )
        return 1 if malos else 0
    for ruta in archivos():
        texto = ruta.read_text(encoding="utf-8")
        nuevo = sincronizar(texto)
        if nuevo != texto:
            ruta.write_text(nuevo, encoding="utf-8")
            print(f"Actualizado: {ruta.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
