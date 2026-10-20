"""Bot de prueba: gasta 3.1 s en su primera jugada y reporta el tiempo_restante que ve."""

import time

from motor import Estado, reportar

primera = True


def preparar(config):
    Estado.inicial().jugadas()


def jugar(estado, tiempo_restante):
    global primera
    if primera:
        primera = False
        time.sleep(3.1)
    reportar(tiempo_restante=tiempo_restante)
    return estado.jugadas()[0]
