"""Estado de una partida: tablero, turno y puntos. Nunca cambia: cada jugada crea uno nuevo."""

from __future__ import annotations

import numbers

import numpy as np

from motor import nucleo
from motor.jugada import Jugada, casilla_de_texto, nombre_casilla

COLORES = ("blancas", "negras")


def _color(nombre: str) -> int:
    if nombre not in COLORES:
        raise ValueError(f"Color desconocido: {nombre!r}. Usa 'blancas' o 'negras'.")
    return COLORES.index(nombre)


class Estado:
    """Una posición del juego. Es inmutable: `aplicar` y `siguiente` regresan estados nuevos.

    Ejemplo:
        >>> e = Estado.inicial()
        >>> e.turno
        'blancas'
        >>> j = e.jugadas()[0]
        >>> nuevo = e.aplicar(j)        # e no cambia
        >>> nuevo.turno
        'negras'
    """

    __slots__ = ("_tablero", "_color", "_puntos", "_jugadas", "_legales", "_clave")

    def __init__(self, tablero: np.ndarray, color: int, puntos: np.ndarray) -> None:
        # Uso interno: los alumnos crean estados con `inicial()` o `desde_dict()`.
        tablero.flags.writeable = False
        puntos.flags.writeable = False
        self._tablero = tablero
        self._color = color
        self._puntos = puntos
        self._jugadas: tuple[Jugada, ...] | None = None
        self._legales: frozenset[Jugada] | None = None  # para verificar legalidad en O(1)
        self._clave: int | None = None

    # --- Crear ------------------------------------------------------------------

    @classmethod
    def inicial(cls) -> Estado:
        """Posición de salida: Blancas en filas 1–2, Negras en 8–9, empiezan Blancas."""
        tablero = np.zeros(nucleo.CASILLAS, np.int8)
        tablero[: 2 * nucleo.LADO] = 1
        tablero[-2 * nucleo.LADO :] = 2
        return cls(tablero, 0, np.zeros(2, np.int64))

    @classmethod
    def desde_dict(cls, d: dict) -> Estado:
        """Arma un estado a partir de un diccionario como el de `a_dict()`.

        Ejemplo:
            >>> e = Estado.desde_dict({"blancas": ["e4", "d3"], "negras": ["f5"],
            ...                        "turno": "blancas", "puntos": {"blancas": 0, "negras": 1}})

        `puntos` es opcional (0 y 0). ValueError si algo no cuadra.
        """
        if not isinstance(d, dict):
            raise ValueError("desde_dict espera un diccionario.")
        tablero = np.zeros(nucleo.CASILLAS, np.int8)
        for color, nombre in enumerate(COLORES):
            casillas = d.get(nombre)
            if not isinstance(casillas, list | tuple):
                raise ValueError(f"Falta la lista de casillas de {nombre}, p. ej. ['e2', 'e3'].")
            if len(casillas) > nucleo.PEONES:
                raise ValueError(f"{nombre} tiene más de {nucleo.PEONES} peones.")
            meta = nucleo.LADO - 1 if color == 0 else 0
            for texto in casillas:
                c = casilla_de_texto(texto)
                if tablero[c] != nucleo.VACIA:
                    raise ValueError(f"La casilla {texto} aparece dos veces.")
                if c // nucleo.LADO == meta:
                    raise ValueError(
                        f"{nombre} no puede tener un peón en {texto}: ya habría anotado."
                    )
                tablero[c] = color + 1
        puntos = np.zeros(2, np.int64)
        datos_puntos = d.get("puntos", {})
        if not isinstance(datos_puntos, dict):
            raise ValueError("'puntos' debe ser un diccionario {'blancas': n, 'negras': n}.")
        for color, nombre in enumerate(COLORES):
            valor = datos_puntos.get(nombre, 0)
            if type(valor) is not int or not 0 <= valor <= nucleo.PUNTOS_PARA_GANAR:
                raise ValueError(f"Puntos de {nombre} inválidos: {valor!r} (entero de 0 a 3).")
            puntos[color] = valor
        if puntos.min() >= nucleo.PUNTOS_PARA_GANAR:
            raise ValueError("Los dos colores no pueden tener 3 puntos.")
        return cls(tablero, _color(d.get("turno")), puntos)

    def a_dict(self) -> dict:
        """Estado como diccionario (se puede guardar en JSON).

        Ejemplo: {"blancas": ["a1", ...], "negras": [...], "turno": "blancas",
        "puntos": {"blancas": 0, "negras": 0}}. Casillas en orden a1, b1, …, i9.
        """
        return {
            "blancas": self.piezas("blancas"),
            "negras": self.piezas("negras"),
            "turno": self.turno,
            "puntos": self.puntos,
        }

    # --- Consultar --------------------------------------------------------------

    @property
    def turno(self) -> str:
        """A quién le toca: "blancas" o "negras"."""
        return COLORES[self._color]

    @property
    def puntos(self) -> dict[str, int]:
        """Puntos de cada color, p. ej. {"blancas": 1, "negras": 0}."""
        return {COLORES[0]: int(self._puntos[0]), COLORES[1]: int(self._puntos[1])}

    def piezas(self, color: str) -> list[str]:
        """Casillas donde tiene peones `color` ("blancas" o "negras"), en orden a1, b1, …, i9.

        Ejemplo:
            >>> Estado.inicial().piezas("negras")[:3]
            ['a8', 'b8', 'c8']
        """
        pieza = _color(color) + 1
        return [nombre_casilla(int(c)) for c in np.flatnonzero(self._tablero == pieza)]

    @property
    def clave(self) -> int:
        """Número de 64 bits que identifica el estado (tablero, turno y puntos).

        Útil como llave de un diccionario (tabla de transposición).
        """
        if self._clave is None:
            self._clave = int(
                nucleo.clave(
                    self._tablero,
                    self._color,
                    self._puntos,
                    nucleo.Z_PIEZAS,
                    nucleo.Z_TURNO,
                    nucleo.Z_PUNTOS,
                )
            )
        return self._clave

    def jugadas(self) -> list[Jugada]:
        """Lista de jugadas legales del jugador en turno. Vacía si la partida terminó."""
        if self._jugadas is None:
            if self._puntos.max() >= nucleo.PUNTOS_PARA_GANAR:
                self._jugadas = ()
            else:
                origenes = np.empty(nucleo.MAX_JUGADAS, np.int64)
                destinos = np.empty(nucleo.MAX_JUGADAS, np.int64)
                n = nucleo.generar(self._tablero, self._color, origenes, destinos)
                self._jugadas = tuple(
                    Jugada(int(o), int(d)) for o, d in zip(origenes[:n], destinos[:n], strict=True)
                )
        return list(self._jugadas)

    def es_ataque(self, jugada: Jugada) -> bool:
        """True si la jugada ataca un peón rival (se resuelve con dado)."""
        j = self._legal(jugada)
        return bool(self._tablero[j.destino] != nucleo.VACIA)

    def prob_ataque(self, jugada: Jugada) -> float:
        """Probabilidad de que la jugada salga bien: p si es ataque, 1.0 si no."""
        j = self._legal(jugada)
        return float(nucleo.prob_jugada(self._tablero, self._color, j.origen, j.destino))

    def ganador(self) -> str | None:
        """Quién ganó: "blancas", "negras" o None si la partida sigue.

        Gana quien llega a 3 puntos, o el rival de quien ya no tiene jugadas en su turno.
        """
        for color in (0, 1):
            if self._puntos[color] >= nucleo.PUNTOS_PARA_GANAR:
                return COLORES[color]
        if not self.jugadas():
            return COLORES[1 - self._color]
        return None

    def terminado(self) -> bool:
        """True si la partida ya tiene ganador."""
        return self.ganador() is not None

    # --- Jugar ------------------------------------------------------------------

    def aplicar(self, jugada: Jugada, gana_ataque: bool | None = None) -> Estado:
        """Estado después de la jugada. En un ataque debes decir si gana: `gana_ataque=True/False`.

        Ejemplo:
            >>> e = Estado.inicial()
            >>> e.aplicar(Jugada.desde_texto("e2-e3")).turno
            'negras'
            >>> e.aplicar("e2-e3").turno       # también acepta texto
            'negras'

        En un ataque (# ejemplo, `j` es un ataque legal):
            gana = e.aplicar(j, gana_ataque=True)

        ValueError si la jugada es ilegal o si falta `gana_ataque` en un ataque.
        """
        j = self._legal(jugada)
        es_ataque = self._tablero[j.destino] != nucleo.VACIA
        if es_ataque and gana_ataque is None:
            raise ValueError(f"{j} es un ataque: indica gana_ataque=True o gana_ataque=False.")
        tablero = self._tablero.copy()
        puntos = self._puntos.copy()
        nucleo.aplicar(tablero, puntos, self._color, j.origen, j.destino, bool(gana_ataque))
        return Estado(tablero, 1 - self._color, puntos)

    def siguiente(self, jugada: Jugada) -> list[tuple[float, Estado]]:
        """Resultados posibles de la jugada como [(probabilidad, estado), ...].

        Sin ataque: un elemento [(1.0, estado)].
        Con ataque: dos, primero si gana y luego si pierde: [(p, gana), (1 - p, pierde)].

        Ejemplo (# ejemplo: valor esperado con tu propia función `evaluar`):
            valor = sum(p * evaluar(s) for p, s in estado.siguiente(j))
        """
        j = self._legal(jugada)
        if self._tablero[j.destino] == nucleo.VACIA:
            return [(1.0, self.aplicar(j))]
        p = self.prob_ataque(j)
        return [
            (p, self.aplicar(j, gana_ataque=True)),
            (1.0 - p, self.aplicar(j, gana_ataque=False)),
        ]

    # --- Mostrar ------------------------------------------------------------------

    def dibujar(self) -> str:
        """Tablero en texto (B = blancas, N = negras, . = vacía), con turno y puntos."""
        simbolos = ".BN"
        letras = "  " + " ".join("abcdefghi")
        filas = [letras]
        for fila in range(nucleo.LADO - 1, -1, -1):
            casillas = self._tablero[fila * nucleo.LADO : (fila + 1) * nucleo.LADO]
            filas.append(f"{fila + 1} {' '.join(simbolos[v] for v in casillas)} {fila + 1}")
        filas.append(letras)
        pts = self.puntos
        filas.append(
            f"Turno: {self.turno} · Puntos: blancas {pts['blancas']}, negras {pts['negras']}"
        )
        return "\n".join(filas)

    def __str__(self) -> str:
        return self.dibujar()

    def __repr__(self) -> str:
        return f"Estado(turno={self.turno!r}, puntos={self.puntos}, clave={self.clave})"

    def __eq__(self, otro: object) -> bool:
        if not isinstance(otro, Estado):
            return NotImplemented
        return (
            self._color == otro._color
            and np.array_equal(self._puntos, otro._puntos)
            and np.array_equal(self._tablero, otro._tablero)
        )

    def __hash__(self) -> int:
        return hash(self.clave)

    # --- Interno ------------------------------------------------------------------

    def _legal(self, jugada: Jugada | str) -> Jugada:
        """Convierte a Jugada y verifica que sea legal; si no, ValueError con explicación.

        Solo acepta `Jugada` o texto "e2-e3"; una tupla suelta es un error.
        """
        if isinstance(jugada, str):
            jugada = Jugada.desde_texto(jugada)
        elif not isinstance(jugada, Jugada):
            raise ValueError(
                f"Jugada inválida: {jugada!r}. Usa una Jugada de estado.jugadas() o texto 'e2-e3'."
            )
        if self._legales is None:
            self._legales = frozenset(self.jugadas())
        if jugada not in self._legales:
            if self.terminado():
                raise ValueError(f"La partida ya terminó (ganó {self.ganador()}); no hay jugadas.")
            raise ValueError(f"Jugada ilegal: {jugada}. Usa una de estado.jugadas().")
        return jugada


def prob_combate(apoyo_atacante: int, apoyo_defensor: int) -> float:
    """Probabilidad de que gane el atacante.

    p = 0.5 + 0.15 × (apoyo_atacante − apoyo_defensor), acotada entre 0.2 y 0.9.
    Ejemplo: `prob_combate(2, 1) == 0.65`.
    """
    return float(nucleo.prob_combate(apoyo_atacante, apoyo_defensor))


def simular_al_azar(estado: Estado, n: int, semilla: int, para: str) -> float:
    """Juega `n` partidas al azar desde `estado` y regresa qué fracción gana `para`.

    Ambos colores eligen jugadas al azar (todas con la misma probabilidad) y los
    ataques se resuelven con dado según p. Mismos argumentos → mismo resultado.

    Ejemplo:
        >>> e = Estado.inicial()
        >>> 0.0 <= simular_al_azar(e, 500, semilla=1, para=e.turno) <= 1.0
        True

    `para` es obligatorio ("blancas" o "negras"): así no te confundes de perspectiva.
    Si `estado` ya terminó, regresa 1.0 o 0.0.
    Ojo: cada llamada reinicia con `semilla` el generador global de numba (`np.random`
    dentro de funciones numba).
    """
    objetivo = _color(para)
    if not isinstance(n, numbers.Integral) or isinstance(n, bool) or n < 1:
        raise ValueError(f"n debe ser un entero ≥ 1, no {n!r}.")
    if not isinstance(semilla, numbers.Integral):
        raise ValueError(f"semilla debe ser un entero, no {semilla!r}.")
    ganador = estado.ganador()
    if ganador is not None:
        return 1.0 if ganador == para else 0.0
    return float(
        nucleo.simular(
            estado._tablero, estado._puntos, estado._color, int(n), int(semilla) % 2**32, objetivo
        )
    )
