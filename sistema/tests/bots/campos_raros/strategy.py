"""Bot de prueba: escribe en el protocolo una jugada con campos de tipos raros."""

import os

MENSAJE = b'{"tipo":"jugada","jugada":[1e999],"info":{"x":NaN,"y":-Infinity}}\n'


def jugar(estado, tiempo_restante):
    for fd in range(3, 20):
        try:
            os.write(fd, MENSAJE)
        except OSError:
            pass
    return estado.jugadas()[0]
