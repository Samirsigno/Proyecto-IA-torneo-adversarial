"""Configuración del torneo: límites, calificación y nombres reservados."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, fields, replace
from pathlib import Path

# Carpeta `sistema/` (donde vive este archivo) y raíz del repo.
# `sistema/` se instala en modo editable (`pip install -e sistema`), así que
# __file__ siempre apunta al archivo real dentro del repo.
SISTEMA: Path = Path(__file__).resolve().parent
RAIZ: Path = SISTEMA.parent

RESERVADOS: tuple[str, ...] = ("random", "montecarlo", "humano")


@dataclass(frozen=True)
class Limites:
    """Límites de recursos de cada bot (ver `sistema/limites.toml`)."""

    reloj_s: float
    preparar_s: float
    memoria_mb: int
    carpeta_mb: int
    archivo_mb: int
    salida_kb: int
    requirements_mb: int
    escala_limites: float

    def efectivos(self) -> Limites:
        """Límites que aplica el árbitro: `escala_limites` multiplica reloj y memoria.

        `preparar_s` no cambia (regla global del torneo).
        """
        f = self.escala_limites
        return replace(self, reloj_s=self.reloj_s * f, memoria_mb=int(self.memoria_mb * f))


def _leer_toml(ruta: Path) -> dict:
    with ruta.open("rb") as archivo:
        return tomllib.load(archivo)


def _validar_numero(ruta: Path, nombre: str, valor: object, tipo: str) -> float | int:
    """Revisa que el valor sea un número positivo del tipo correcto."""
    entero = isinstance(valor, int) and not isinstance(valor, bool)
    real = isinstance(valor, float)
    if tipo == "int" and not entero:
        raise ValueError(f"{ruta}: {nombre} debe ser un número entero, no {valor!r}.")
    if tipo == "float" and not (entero or real):
        raise ValueError(f"{ruta}: {nombre} debe ser un número, no {valor!r}.")
    if valor <= 0:
        raise ValueError(f"{ruta}: {nombre} debe ser mayor que 0, no {valor!r}.")
    return float(valor) if tipo == "float" else valor


def cargar_limites(ruta: Path | None = None) -> Limites:
    """Lee los límites. Sin `ruta`: `$TORNEO_LIMITES` o `sistema/limites.toml`."""
    if ruta is None:
        ruta = Path(os.environ.get("TORNEO_LIMITES") or SISTEMA / "limites.toml")
    datos = _leer_toml(ruta)
    campos = {c.name: c.type for c in fields(Limites)}
    faltan = [nombre for nombre in campos if nombre not in datos]
    sobran = [nombre for nombre in datos if nombre not in campos]
    if faltan or sobran:
        raise ValueError(
            f"{ruta}: límites mal escritos. "
            f"Faltan: {', '.join(faltan) or 'ninguno'}. "
            f"Sobran: {', '.join(sobran) or 'ninguno'}."
        )
    return Limites(
        **{
            nombre: _validar_numero(ruta, nombre, datos[nombre], tipo)
            for nombre, tipo in campos.items()
        }
    )


def limites_prueba() -> Limites:
    """Límites reducidos para tests que juegan partidas (reloj 3 s, preparar 5 s)."""
    return replace(cargar_limites(), reloj_s=3.0, preparar_s=5.0)


def cargar_calificacion(ruta: Path | None = None) -> dict[str, float]:
    """Calificación que otorga ganarle a cada rival de referencia."""
    datos = _leer_toml(ruta or SISTEMA / "calificacion.toml")
    return {rival: float(nota) for rival, nota in datos.items()}


def es_reservado(nombre: str) -> bool:
    """True si el nombre no se puede usar como equipo de alumnos."""
    return nombre in RESERVADOS or nombre.startswith(("tier_", "_"))
