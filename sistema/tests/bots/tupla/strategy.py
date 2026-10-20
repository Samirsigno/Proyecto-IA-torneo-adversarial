"""Bot de prueba: regresa una tupla (origen, destino) en vez de una Jugada."""


def jugar(estado, tiempo_restante):
    j = estado.jugadas()[0]
    return (j.origen, j.destino)
