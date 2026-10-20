"""Bot de prueba: jugada al azar con la semilla de config (determinista)."""

import random

from motor import Estado

azar = None


def preparar(config):
    global azar
    azar = random.Random(config.semilla)
    Estado.inicial().jugadas()


def jugar(estado, tiempo_restante):
    return azar.choice(estado.jugadas())
