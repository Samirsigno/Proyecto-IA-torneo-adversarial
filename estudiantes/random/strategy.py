"""Bot «random»: elige una jugada legal al azar. Sirve de ejemplo mínimo."""

import random


def preparar(config):
    """Se llama una vez antes de la partida. Aquí creamos nuestro generador de azar."""
    global rng
    rng = random.Random(config.semilla)  # misma semilla, misma partida


def jugar(estado, tiempo_restante):
    """Te toca: regresa una de las jugadas legales."""
    return rng.choice(estado.jugadas())
