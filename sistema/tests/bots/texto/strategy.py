"""Bot de prueba: regresa la jugada como texto, p. ej. "e2-e3"."""


def jugar(estado, tiempo_restante):
    j = estado.jugadas()[0]
    return f"{j}"
