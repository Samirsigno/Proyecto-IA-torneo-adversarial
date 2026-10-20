"""Protocolo árbitro ↔ bot: un mensaje JSON por línea, máximo 64 KB por línea.

Árbitro → bot:
- `{"tipo": "preparar", "config": {"color", "semilla", "carpeta_datos", "reloj_s"}}`
- `{"tipo": "jugar", "estado": {...}, "tiempo_restante": float}`
- `{"tipo": "fin", "resultado": {"ganador", "motivo", "puntos"}}`

Bot (runner) → árbitro:
- `{"tipo": "hola"}`: el runner arrancó (antes de tocar código del alumno). Marca el
  fin del arranque del contenedor, que queda fuera de todo reloj.
- `{"tipo": "listo"}`: terminó `preparar`.
- `{"tipo": "jugada", "jugada": str, "info": dict | null}`
- `{"tipo": "adios", "memoria_pico_mb": float}`: respuesta a `fin` (memoria informativa).

`config.carpeta_datos` lo llena el runner con la ruta real de `data/` del bot; el
árbitro manda `"data"` (relativa a la carpeta del bot).

Una línea más larga que `MAX_BYTES`, que no es JSON o que no es un objeto con
`"tipo"` de texto es un mensaje inválido (`MensajeInvalido`).
"""

from __future__ import annotations

import json
import os

MAX_BYTES = 64 * 1024
_TROZO = 64 * 1024


class MensajeInvalido(ValueError):
    """Línea del protocolo mal formada, demasiado larga o sin `tipo`."""


def codificar(mensaje: dict) -> bytes:
    """Mensaje → línea JSON terminada en `\\n`. MensajeInvalido si pasa de 64 KB."""
    linea = json.dumps(mensaje, ensure_ascii=True, separators=(",", ":"), default=str).encode()
    if len(linea) > MAX_BYTES:
        raise MensajeInvalido(f"Mensaje de {len(linea)} bytes: el máximo es {MAX_BYTES}.")
    return linea + b"\n"


def decodificar(linea: bytes) -> dict:
    """Línea (sin `\\n`) → mensaje. MensajeInvalido si no es un mensaje válido."""
    if len(linea) > MAX_BYTES:
        raise MensajeInvalido(f"Mensaje de {len(linea)} bytes: el máximo es {MAX_BYTES}.")
    try:
        mensaje = json.loads(linea)
    except (ValueError, RecursionError) as e:  # JSON roto, anidado de más o enteros enormes
        raise MensajeInvalido("El mensaje no es JSON válido.") from e
    if not isinstance(mensaje, dict) or not isinstance(mensaje.get("tipo"), str):
        raise MensajeInvalido('El mensaje debe ser un objeto JSON con "tipo".')
    return mensaje


class LectorLineas:
    """Lee líneas de un descriptor sin guardar nunca más de `MAX_BYTES` (+ un trozo).

    `leer()` regresa la línea (sin `\\n`) o None al llegar al fin del archivo.
    Si una línea pasa del máximo, lanza MensajeInvalido una vez y descarta el
    resto de esa línea; la siguiente se lee normal.
    """

    def __init__(self, fd: int, maximo: int = MAX_BYTES) -> None:
        self._fd = fd
        self._maximo = maximo
        self._buf = bytearray()
        self._descartando = False
        self._fin = False

    def leer(self) -> bytes | None:
        while True:
            i = self._buf.find(b"\n")
            if i >= 0:
                linea = bytes(self._buf[:i])
                del self._buf[: i + 1]
                if self._descartando:  # cola de una línea demasiado larga
                    self._descartando = False
                    continue
                if len(linea) > self._maximo:
                    raise MensajeInvalido(f"Línea de más de {self._maximo} bytes.")
                return linea
            if len(self._buf) > self._maximo:
                self._buf.clear()
                if not self._descartando:
                    self._descartando = True
                    raise MensajeInvalido(f"Línea de más de {self._maximo} bytes.")
            if self._fin:
                return None  # un pedazo sin `\n` al final no cuenta como mensaje
            trozo = os.read(self._fd, _TROZO)
            if trozo:
                self._buf += trozo
            else:
                self._fin = True


# --- Constructores de mensajes ------------------------------------------------------


def preparar(color: str, semilla: int, reloj_s: float) -> dict:
    config = {"color": color, "semilla": semilla, "carpeta_datos": "data", "reloj_s": reloj_s}
    return {"tipo": "preparar", "config": config}


def jugar(estado: dict, tiempo_restante: float) -> dict:
    return {"tipo": "jugar", "estado": estado, "tiempo_restante": tiempo_restante}


def fin(resultado: dict) -> dict:
    return {"tipo": "fin", "resultado": resultado}


def hola() -> dict:
    return {"tipo": "hola"}


def listo() -> dict:
    return {"tipo": "listo"}


def jugada(texto: str, info: dict | None) -> dict:
    return {"tipo": "jugada", "jugada": texto, "info": info}


def adios(memoria_pico_mb: float | None) -> dict:
    return {"tipo": "adios", "memoria_pico_mb": memoria_pico_mb}
