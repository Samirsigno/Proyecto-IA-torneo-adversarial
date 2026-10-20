"""Bot de prueba: responde y un hilo hace os._exit(0) unos ms después (justo en la pausa).

La demora (5 a 12 ms, donde cae `docker pause`) sale de config.semilla:
cada partida prueba otro momento.
"""

import os
import random
import threading
import time

from motor import Estado

demora = 0.0


def preparar(config):
    global demora
    Estado.inicial().jugadas()  # compila el motor aquí, no en su turno
    demora = random.Random(config.semilla).uniform(0.005, 0.012)


def morir():
    inicio = time.perf_counter()
    while time.perf_counter() - inicio < demora:
        pass
    os._exit(0)


def jugar(estado, tiempo_restante):
    jugada = estado.jugadas()[0]
    threading.Thread(target=morir, daemon=True).start()
    return jugada
