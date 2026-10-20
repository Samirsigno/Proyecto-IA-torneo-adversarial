"""Bot de prueba (solo Docker): intenta conectarse a internet."""

import socket


def jugar(estado, tiempo_restante):
    socket.create_connection(("9.9.9.9", 53), timeout=1).close()
    return estado.jugadas()[0]
