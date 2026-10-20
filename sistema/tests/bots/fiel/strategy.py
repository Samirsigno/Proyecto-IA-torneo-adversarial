"""Bot de prueba: juega la primera jugada legal."""

from motor import Estado


def preparar(config):
    Estado.inicial().jugadas()  # compila el motor (numba) dentro de preparar


def jugar(estado, tiempo_restante):
    return estado.jugadas()[0]
