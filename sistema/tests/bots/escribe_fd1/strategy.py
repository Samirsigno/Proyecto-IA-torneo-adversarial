"""Bot de prueba: escribe basura directo al descriptor 1 (stdout) y juega normal."""

import os


def jugar(estado, tiempo_restante):
    os.write(1, b"basura sin salto de linea {")
    os.write(1, b'{"tipo":"jugada","jugada":"a1-a9","info":null}\n')
    print("y un print normal")
    return estado.jugadas()[0]
