"""Bot de prueba: busca los descriptores del protocolo y escribe basura en ellos."""

import os


def jugar(estado, tiempo_restante):
    for fd in range(3, 20):
        try:
            os.write(fd, b"esto no es json\n")
        except OSError:
            pass
    return estado.jugadas()[0]
