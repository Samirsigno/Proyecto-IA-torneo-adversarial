"""Bot de prueba: reporta un diccionario anidado 500 niveles y juega normal."""

from motor import reportar


def jugar(estado, tiempo_restante):
    anidado = {}
    actual = anidado
    for _ in range(500):
        actual["x"] = {}
        actual = actual["x"]
    reportar(arbol=anidado)
    return estado.jugadas()[0]
