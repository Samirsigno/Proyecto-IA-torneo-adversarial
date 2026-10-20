"""Bot de prueba: preparar tarda 12 s."""

import time


def preparar(config):
    time.sleep(12)


def jugar(estado, tiempo_restante):
    return estado.jugadas()[0]
