"""Validador de entregas: revisa la carpeta de un equipo antes de la liga.

- `validar`: `validar_equipo(carpeta, limites, ...) -> Reporte` y `validar_nombre_nuevo`.
- `requirements`: auditoría de `requirements.txt` (corre al construir la imagen del equipo).
- `reglas`: listas negras, firmas binarias, secciones del informe.

Este archivo no importa `validar` de inmediato: `validador.requirements` corre al
construir la imagen y no debe cargar el motor ni el árbitro.
"""

from __future__ import annotations

from typing import Any

__all__ = ["Reporte", "validar_equipo", "validar_nombre_nuevo"]


def __getattr__(nombre: str) -> Any:
    if nombre in __all__:
        from validador import validar

        return getattr(validar, nombre)
    raise AttributeError(f"module 'validador' has no attribute {nombre!r}")
