"""Perfiles de rendimiento de specs.py: costo por llamada de cada función.

Uso, desde la carpeta del equipo:

    python herramientas/perfilar_specs.py

Cada perfil mide una llamada típica. Una llamada tarda menos de un microsegundo, del mismo orden
que leer el reloj, así que una sola medición es casi puro ruido: timeit la repite N veces
(autorange elige N para que tarde al menos 0.2 s) y divide entre N. Eso se repite REPETICIONES
veces y se reporta el mínimo, la medición con menos interferencia del sistema operativo.
A cada perfil se le resta el costo de una llamada vacía (`base`), que timeit también mide.
"""

import sys
import timeit
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # specs.py vive en la raíz

import specs  # noqa: E402

REPETICIONES = 5

# Nombre del perfil → llamada que mide.
PERFILES = {
    "specs.estado_a_indice": lambda: specs.estado_a_indice(8, 8, 36, 2),
    "specs.indice_a_estado": lambda: specs.indice_a_estado(specs.NUM_ESTADOS - 1),
    "specs.material_a_indice": lambda: specs.material_a_indice(-18),
    "specs.calcular_probabilidad_combate": lambda: specs.calcular_probabilidad_combate(2, 0),
    "specs.calcular_recompensa": lambda: specs.calcular_recompensa(1, -1, 2, 1, 1),
    "specs.calcular_recompensa[victoria]": lambda: specs.calcular_recompensa(
        0, 1, 0, resultado=specs.GANA
    ),
}


def medir(llamada) -> float:
    """Nanosegundos por llamada: mínimo de REPETICIONES mediciones de N llamadas cada una."""
    temporizador = timeit.Timer(llamada)
    n, _ = temporizador.autorange()
    return min(temporizador.repeat(repeat=REPETICIONES, number=n)) / n * 1e9


def main() -> None:
    base = medir(lambda: None)
    print(f"base (llamada vacía): {base:.1f} ns, ya restada abajo\n")
    print(f"{'perfil':<40}{'ns/llamada':>12}{'llamadas/s':>16}")
    for nombre, llamada in PERFILES.items():
        neto = max(medir(llamada) - base, 0.0)
        por_segundo = f"{1e9 / neto:,.0f}" if neto else "∞"
        print(f"{nombre:<40}{neto:>12.1f}{por_segundo:>16}")


if __name__ == "__main__":
    main()
