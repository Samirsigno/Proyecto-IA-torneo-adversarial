"""Equipo de prueba: pasa la revisión estática pero falla al jugar."""


def preparar(config):
    pass


def jugar(estado, tiempo_restante):
    return 1 / 0  # ZeroDivisionError en la primera jugada
