"""Bot de prueba (solo Docker): crea procesos hasta que el sistema no deja más."""

import os
import time


def jugar(estado, tiempo_restante):
    hijos = 0
    while hijos < 1000:
        try:
            pid = os.fork()
        except OSError:
            break
        if pid == 0:
            time.sleep(1000)
            os._exit(0)
        hijos += 1
    while True:
        pass
