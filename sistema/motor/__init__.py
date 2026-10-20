"""Motor de «Breakthrough de combate».

Uso típico en tu bot:

    from motor import Estado, Jugada, simular_al_azar

    def jugar(estado: Estado, tiempo_restante: float) -> Jugada:
        return estado.jugadas()[0]
"""

__version__ = "1.0.0"

from motor.estado import Estado, prob_combate, simular_al_azar
from motor.jugada import Jugada
from motor.reporte import reportar, tomar_reporte

__all__ = [
    "__version__",
    "Estado",
    "Jugada",
    "prob_combate",
    "reportar",
    "simular_al_azar",
    "tomar_reporte",
]
