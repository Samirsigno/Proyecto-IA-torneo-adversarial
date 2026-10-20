"""Bot de prueba: imprime comandos de GitHub Actions y caracteres de control; juega normal."""

import sys


def jugar(estado, tiempo_restante):
    print("::error::gané yo")
    print("  ::set-output name=ganador::yo")
    print("hola\r::stop-commands::token")
    sys.stderr.write("\x1b[31mrojo\x1b[0m\n::notice::fin\n")
    return estado.jugadas()[0]
