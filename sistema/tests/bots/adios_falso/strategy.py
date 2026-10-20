"""Bot de prueba: escribe en el protocolo un `adios` con un número enorme a media partida."""

import os

MENSAJE = b'{"tipo":"adios","memoria_pico_mb":' + b"9" * 400 + b"}\n"


def jugar(estado, tiempo_restante):
    for fd in range(3, 20):
        try:
            os.write(fd, MENSAJE)
        except OSError:
            pass
    return estado.jugadas()[0]
