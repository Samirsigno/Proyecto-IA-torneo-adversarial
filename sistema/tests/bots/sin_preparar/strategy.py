"""Bot de prueba: sin `preparar`; su primera llamada al motor es en su turno (como `random`)."""


def jugar(estado, tiempo_restante):
    return estado.jugadas()[0]
