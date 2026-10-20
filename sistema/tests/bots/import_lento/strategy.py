"""Bot de prueba: tarda 12 s al importar strategy.py (trabajo a nivel de módulo)."""

import time

time.sleep(12)


def jugar(estado, tiempo_restante):
    return estado.jugadas()[0]
