"""Calendario de la liga: todos contra todos, 4 partidas por pareja, y reparto en shards."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations


@dataclass(frozen=True)
class PartidaProgramada:
    """Una partida del calendario. `juego` es el juego de dados (0, 1, ...)."""

    pareja: int
    juego: int
    blancas: str
    negras: str


def generar_calendario(participantes: list[str], juegos_dados: int = 2) -> list[PartidaProgramada]:
    """Todos contra todos. Los participantes se ordenan alfabéticamente antes de numerar.

    Por pareja (A, B) con A < B: juego 0 A-B, juego 0 B-A, juego 1 A-B, juego 1 B-A, ...
    Así cada equipo juega cada juego de dados una vez con cada color.
    """
    if juegos_dados < 1:
        raise ValueError(f"juegos_dados debe ser 1 o más, no {juegos_dados}.")
    ordenados = sorted(participantes)
    repetidos = sorted({p for p in ordenados if ordenados.count(p) > 1})
    if repetidos:
        raise ValueError(f"Participantes repetidos: {', '.join(repetidos)}.")
    calendario = []
    for pareja, (a, b) in enumerate(combinations(ordenados, 2)):
        for juego in range(juegos_dados):
            calendario.append(PartidaProgramada(pareja, juego, a, b))
            calendario.append(PartidaProgramada(pareja, juego, b, a))
    return calendario


def repartir(
    calendario: list[PartidaProgramada], shard: int, total: int
) -> list[PartidaProgramada]:
    """Partidas del shard `shard` (de 0 a `total` − 1). Las parejas nunca se parten.

    La pareja `p` va al shard `p % total` (reparto parejo y estable).
    """
    if total < 1 or not 0 <= shard < total:
        raise ValueError(f"Shard inválido: {shard} de {total} (usa 0 ≤ shard < total).")
    return [p for p in calendario if p.pareja % total == shard]
