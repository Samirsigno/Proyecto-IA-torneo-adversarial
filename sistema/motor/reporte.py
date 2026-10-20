"""Reporte opcional del bot: lo que pensó en su turno (lo muestran el visor y `-v`)."""

from __future__ import annotations

_reporte: dict | None = None


def reportar(**datos) -> None:
    """Guarda datos de tu turno para el visor. Ejemplo: `reportar(prof=4, nodos=12000)`.

    Si llamas varias veces en el mismo turno, se queda la última.
    """
    global _reporte
    _reporte = dict(datos)


def tomar_reporte() -> dict | None:
    """Regresa el último reporte y lo borra (lo usa el runner al final de cada turno)."""
    global _reporte
    reporte, _reporte = _reporte, None
    return reporte
