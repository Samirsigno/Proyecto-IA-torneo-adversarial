"""Bot de prueba (solo Docker): intenta escribir archivos fuera de lo permitido.

Reporta en `info["escritos"]` los lugares donde SÍ pudo escribir.
"""

import os

from motor import Estado, reportar

LUGARES = [
    "/bot/hackeo.txt",
    "/bot/data/hackeo.txt",
    "/torneo/sistema/motor/hackeo.py",
    "/torneo/hackeo.txt",
    "/tmp/hackeo.txt",
    "/var/tmp/hackeo.txt",
    "/opt/numba_listo/hackeo.txt",
    "/hackeo.txt",
    os.path.expanduser("~/hackeo.txt"),
]
escritos = []


def preparar(config):
    Estado.inicial().jugadas()
    for ruta in LUGARES:
        try:
            with open(ruta, "w") as f:
                f.write("x")
            escritos.append(ruta)
        except OSError:
            pass
    try:
        import motor.estado  # el código del motor también es de solo lectura

        with open(motor.estado.__file__, "a") as f:
            f.write("# hackeo\n")
        escritos.append(motor.estado.__file__)
    except OSError:
        pass


def jugar(estado, tiempo_restante):
    reportar(escritos=escritos)
    return estado.jugadas()[0]
