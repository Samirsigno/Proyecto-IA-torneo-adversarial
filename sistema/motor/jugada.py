"""Jugada: mover un peón de `origen` a `destino`."""

from __future__ import annotations

import numbers
import re
from typing import NamedTuple

COLUMNAS = "abcdefghi"
_FORMATO = re.compile(r"^([a-i])([1-9])-([a-i])([1-9])$")


def nombre_casilla(casilla: int) -> str:
    """Número de casilla → texto. Ejemplo: `nombre_casilla(13) == "e2"`."""
    if not isinstance(casilla, numbers.Integral) or not 0 <= casilla < 81:
        raise ValueError(f"Casilla fuera del tablero: {casilla!r}. Debe ser un entero de 0 a 80.")
    return f"{COLUMNAS[casilla % 9]}{casilla // 9 + 1}"


def casilla_de_texto(texto: str) -> int:
    """Texto → número de casilla. Ejemplo: `casilla_de_texto("e2") == 13`."""
    if not isinstance(texto, str) or not re.fullmatch(r"[a-i][1-9]", texto):
        raise ValueError(
            f"Casilla mal escrita: {texto!r}. Usa columna a–i y fila 1–9, p. ej. 'e2'."
        )
    return (int(texto[1]) - 1) * 9 + COLUMNAS.index(texto[0])


class Jugada(NamedTuple):
    """Una jugada. Las casillas son números: `fila*9 + col`, empezando en 0.

    Ejemplos:
        >>> j = Jugada.desde_texto("e2-e3")
        >>> j.origen, j.destino
        (13, 22)
        >>> str(j)
        'e2-e3'
    """

    origen: int
    destino: int

    def __str__(self) -> str:
        return f"{nombre_casilla(self.origen)}-{nombre_casilla(self.destino)}"

    def __repr__(self) -> str:
        return f"Jugada({self})"

    @classmethod
    def desde_texto(cls, texto: str) -> Jugada:
        """Lee una jugada escrita como "e2-e3". ValueError si está mal escrita."""
        coincide = _FORMATO.match(texto.strip().lower()) if isinstance(texto, str) else None
        if coincide is None:
            raise ValueError(
                f"Jugada mal escrita: {texto!r}. Usa el formato 'e2-e3' (columna a–i, fila 1–9)."
            )
        c1, f1, c2, f2 = coincide.groups()
        return cls(casilla_de_texto(c1 + f1), casilla_de_texto(c2 + f2))
