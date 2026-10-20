"""Bot de prueba: imprime sin parar, sin saltos de línea, empezando con un comando de Actions."""

import sys


def jugar(estado, tiempo_restante):
    print("::error::te gané", end="")
    while True:
        sys.stdout.write("::warning::ñ" * 1000)
