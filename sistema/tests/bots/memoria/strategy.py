"""Bot de prueba (solo Docker): pide memoria sin parar."""

bloques = []


def jugar(estado, tiempo_restante):
    while True:
        bloques.append(bytearray(64 * 1024 * 1024))  # bytearray escribe ceros: páginas reales
