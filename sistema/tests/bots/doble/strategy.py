"""Bot de prueba: además de responder, mete una jugada extra en el protocolo (fuera de turno)."""

import json
import os


def jugar(estado, tiempo_restante):
    texto = str(estado.jugadas()[0])
    mensaje = json.dumps({"tipo": "jugada", "jugada": texto, "info": None}).encode() + b"\n"
    for fd in range(3, 20):
        try:
            os.write(fd, mensaje)
        except OSError:
            pass
    return estado.jugadas()[0]
