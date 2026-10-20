"""Bot de prueba: un hilo sigue trabajando después de responder.

Reporta en `info`: cuánto avanzó el hilo desde su respuesta anterior hasta que
empezó este turno (`fuera`), cuánto avanzó durante `jugar` (`dentro`) y cuánto
duró `jugar` (`duracion`, en segundos).
"""

import threading
import time

from motor import Estado, reportar

contador = 0
al_responder = 0


def trabajar():
    global contador
    while True:
        contador += 1


def preparar(config):
    Estado.inicial().jugadas()
    threading.Thread(target=trabajar, daemon=True).start()


def jugar(estado, tiempo_restante):
    global al_responder
    t0, inicio = time.monotonic(), contador
    time.sleep(0.05)  # deja trabajar al hilo dentro del turno
    fin, duracion = contador, time.monotonic() - t0
    reportar(fuera=inicio - al_responder, dentro=fin - inicio, duracion=duracion)
    al_responder = contador
    return estado.jugadas()[0]
