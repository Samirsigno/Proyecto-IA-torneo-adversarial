"""Calificación de los alumnos (ver docs/calificacion.md).

- Lugares 1, 2 y 3 entre ALUMNOS (posición de la tabla, ya con desempates) → 10.
- Los demás: la calificación más alta entre las referencias a las que les «ganan».
  «Ganarle» = estrictamente más puntos de liga. Empatar en puntos no es ganarle,
  aunque el desempate lo ponga arriba.
- Si no le gana a ninguna referencia → 0.
- Las referencias que no jugaron esta liga (no están en la tabla o tienen 0 partidas
  válidas) se ignoran: nunca cuentan como «ganadas».
- `no_calificables` (p. ej. sin INFORME.md o equipo.toml válido): juegan y salen en la
  tabla, pero no reciben calificación ni ocupan lugar en el top 3 de alumnos.
"""

from __future__ import annotations

from liga.tabla import FilaTabla

LUGARES_CON_10 = 3
CALIFICACION_TOP = 10.0


def calificar(
    tabla: list[FilaTabla],
    referencias: dict[str, float],
    alumnos: set[str],
    no_calificables: set[str] = frozenset(),
) -> dict[str, float]:
    """Calificación de cada alumno calificable.

    `referencias`: rival → calificación (calificacion.toml). Los equipos en
    `no_calificables` no se califican aunque estén en `alumnos`.
    """
    alumnos = set(alumnos) - set(no_calificables)
    filas = {f.equipo: f for f in tabla}
    faltan = sorted(alumnos - filas.keys())
    if faltan:
        raise ValueError(f"Equipos de alumnos sin fila en la tabla: {', '.join(faltan)}.")
    mal = sorted(alumnos & referencias.keys())
    if mal:
        raise ValueError(f"Estos equipos son referencias, no alumnos: {', '.join(mal)}.")

    por_posicion = sorted((filas[a] for a in alumnos), key=lambda f: f.posicion)
    top = {f.equipo for f in por_posicion[:LUGARES_CON_10]}
    return {
        alumno: CALIFICACION_TOP
        if alumno in top
        else nota_por_referencias(tabla, referencias, alumno)
        for alumno in alumnos
    }


def referencias_vencidas(
    tabla: list[FilaTabla], referencias: dict[str, float], equipo: str
) -> list[str]:
    """Referencias a las que `equipo` les «gana» (estrictamente más puntos).

    Se ignoran las que no jugaron (no están en la tabla o tienen 0 partidas válidas).
    """
    filas = {f.equipo: f for f in tabla}
    puntos = filas[equipo].puntos
    return [
        r for r in referencias if r in filas and filas[r].partidas > 0 and puntos > filas[r].puntos
    ]


def nota_por_referencias(
    tabla: list[FilaTabla], referencias: dict[str, float], equipo: str
) -> float:
    """Calificación por referencias vencidas, SIN la regla del top 3 (0 si no vence a nadie)."""
    vencidas = referencias_vencidas(tabla, referencias, equipo)
    return max((referencias[r] for r in vencidas), default=0.0)
