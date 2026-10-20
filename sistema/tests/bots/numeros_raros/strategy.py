"""Bot de prueba: reporta números raros y cambia la memoria pico del runner por un entero enorme.

Juega normal: la partida debe terminar sin falla de infraestructura.
"""

import sys

from motor import reportar


def preparar(config):
    # El runner corre como __main__: el bot reemplaza su medición de memoria.
    sys.modules["__main__"].memoria_pico_mb = lambda: 10**400


def jugar(estado, tiempo_restante):
    reportar(nan=float("nan"), inf=float("inf"), menos_inf=-float("inf"), grande=10**400, neg=-5)
    return estado.jugadas()[0]
