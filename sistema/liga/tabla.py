"""Tabla de la liga con desempates (ver docs/calificacion.md).

Victoria = 1 punto. Orden, de mayor a menor:
1. puntos;
2. puntos en las partidas entre TODOS los empatados en puntos (alumnos y referencias por
   igual; se calcula una vez sobre el grupo completo, no se reaplica a subgrupos);
3. Sonneborn-Berger: por cada partida ganada, los puntos finales del rival;
4. peones anotados en todas sus partidas;
5. sorteo con la semilla maestra (sha256 de «semilla:equipo»; no depende de los demás).

Una partida con falla de infraestructura (`ganador == ""`) nunca entra: se descarta la
pareja COMPLETA a la que pertenece (sus partidas se repiten juntas o no cuentan).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

COLORES = ("blancas", "negras")


@dataclass(frozen=True)
class FilaTabla:
    equipo: str
    puntos: int
    victorias: int
    sb: float
    anotados: int
    posicion: int
    partidas: int = 0


@dataclass(frozen=True)
class _Partida:
    ganador: str
    perdedor: str
    anotados: dict[str, int]


def _partidas_validas(registros: list[dict]) -> list[_Partida]:
    rotas = {r["meta"]["pareja"] for r in registros if r.get("ganador") not in COLORES}
    partidas = []
    for r in registros:
        if r["meta"]["pareja"] in rotas:
            continue
        equipos = {c: r["meta"][c] for c in COLORES}
        ganador = r["ganador"]
        perdedor = COLORES[1 - COLORES.index(ganador)]
        partidas.append(
            _Partida(
                ganador=equipos[ganador],
                perdedor=equipos[perdedor],
                anotados={equipos[c]: int(r["puntos"][c]) for c in COLORES},
            )
        )
    return partidas


def _sorteo(semilla_maestra: int, equipo: str) -> str:
    return hashlib.sha256(f"{semilla_maestra}:{equipo}".encode()).hexdigest()


def construir_tabla(
    registros: list[dict], semilla_maestra: int, participantes: list[str] | None = None
) -> list[FilaTabla]:
    """Tabla ordenada (posición 1 primero) a partir de registros v1.

    `participantes` agrega equipos que no tengan ninguna partida válida (con 0 puntos).
    """
    partidas = _partidas_validas(registros)
    equipos = set(participantes or [])
    for p in partidas:
        equipos |= {p.ganador, p.perdedor}

    puntos: dict[str, int] = dict.fromkeys(equipos, 0)
    jugadas: dict[str, int] = dict.fromkeys(equipos, 0)
    anotados: dict[str, int] = dict.fromkeys(equipos, 0)
    for p in partidas:
        puntos[p.ganador] += 1
        for equipo, n in p.anotados.items():
            jugadas[equipo] += 1
            anotados[equipo] += n

    sb: dict[str, float] = dict.fromkeys(equipos, 0.0)
    for p in partidas:
        sb[p.ganador] += puntos[p.perdedor]

    # Dos equipos con los mismos puntos están en el mismo grupo de empatados.
    entre_empatados: dict[str, int] = dict.fromkeys(equipos, 0)
    for p in partidas:
        if puntos[p.ganador] == puntos[p.perdedor]:
            entre_empatados[p.ganador] += 1

    def clave(equipo: str) -> tuple:
        return (
            -puntos[equipo],
            -entre_empatados[equipo],
            -sb[equipo],
            -anotados[equipo],
            _sorteo(semilla_maestra, equipo),
        )

    return [
        FilaTabla(
            equipo=equipo,
            puntos=puntos[equipo],
            victorias=puntos[equipo],
            sb=sb[equipo],
            anotados=anotados[equipo],
            posicion=i + 1,
            partidas=jugadas[equipo],
        )
        for i, equipo in enumerate(sorted(equipos, key=clave))
    ]
