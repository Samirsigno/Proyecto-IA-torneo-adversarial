"""Bot de prueba: piensa 30 ms por jugada (sin usar CPU) y juega la primera legal."""

import time

from motor import Estado


def preparar(config):
    Estado.inicial().jugadas()


def jugar(estado, tiempo_restante):
    time.sleep(0.03)
    return estado.jugadas()[0]
