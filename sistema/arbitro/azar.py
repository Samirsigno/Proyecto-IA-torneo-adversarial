"""Dados del árbitro y semillas de los bots. El bot nunca ve la semilla de los dados."""

from __future__ import annotations

import numpy as np

COLORES = ("blancas", "negras")
# Etiqueta para que la semilla de los bots nunca coincida con la de los dados.
_ETIQUETA_BOTS = 0xB07


def _indice(color: str) -> int:
    if color not in COLORES:
        raise ValueError(f"Color desconocido: {color!r}. Usa 'blancas' o 'negras'.")
    return COLORES.index(color)


class Dados:
    """Un generador PCG64 por color, sembrado con (semilla_maestra, pareja, juego, color).

    El ataque número k de un color usa el número k de su generador.
    """

    def __init__(self, semilla_maestra: int, pareja: int, juego: int) -> None:
        self._generadores = [
            np.random.Generator(
                np.random.PCG64(np.random.SeedSequence([semilla_maestra, pareja, juego, c]))
            )
            for c in range(len(COLORES))
        ]

    def tirar(self, color: str) -> float:
        """Siguiente número u ~ U[0, 1) del color. El ataque gana si u < p."""
        return float(self._generadores[_indice(color)].random())


def semilla_bots(semilla_maestra: int, pareja: int, juego: int) -> int:
    """Semilla base de los bots de una partida (distinta de la de los dados)."""
    sec = np.random.SeedSequence([semilla_maestra, pareja, juego, _ETIQUETA_BOTS])
    return int(sec.generate_state(1, np.uint64)[0] >> np.uint64(1))


def semilla_de_color(semilla_bots: int, color: str) -> int:
    """Semilla que recibe el bot de `color` en `config.semilla` (entero de 63 bits)."""
    sec = np.random.SeedSequence([semilla_bots, _ETIQUETA_BOTS, _indice(color)])
    return int(sec.generate_state(1, np.uint64)[0] >> np.uint64(1))
