"""Revisa que un PR solo toque UNA carpeta de equipo: `estudiantes/<equipo>/`.

Lee de la entrada estándar la salida de
    git diff --raw --no-renames --no-abbrev -z <base>...<head>
(un renombre aparece como borrar + agregar, así que se revisan las dos rutas). Rechaza
submódulos (modo 160000): su contenido no estaría en el repo.

Con `--base <sha>`, rechaza además una carpeta que ya existe en ese commit (la de otro
equipo ya aceptado): la entrega es una sola vez, con una carpeta nueva.

Si todo está bien, imprime el nombre del equipo y sale con 0. Si no, explica en español
qué rutas sobran y sale con 1. Solo biblioteca estándar (corre con el Python del runner).
"""

from __future__ import annotations

import re
import subprocess
import sys

NOMBRE = re.compile(r"^[a-z0-9_]{3,30}$")
RESERVADOS = ("random", "montecarlo", "humano")
SUBMODULO = "160000"
ESTADOS = {"A": "agregado", "M": "modificado", "D": "borrado", "T": "cambió de tipo"}


def es_reservado(nombre: str) -> bool:
    return nombre in RESERVADOS or nombre.startswith(("tier_", "_"))


def leer_cambios(texto: str) -> list[tuple[str, str, tuple[str, str]]]:
    """Salida de `git diff --raw -z` → [(estado, ruta, (modo_antes, modo_despues))]."""
    partes = texto.split("\0")
    cambios = []
    i = 0
    while i < len(partes) and partes[i]:
        meta = partes[i].lstrip(":").split()
        modos, estado = (meta[0], meta[1]), meta[4][:1]
        if estado in ("R", "C"):  # por si acaso llegan con renombres: dos rutas
            cambios += [(estado, partes[i + 1], modos), (estado, partes[i + 2], modos)]
            i += 3
        else:
            cambios.append((estado, partes[i + 1], modos))
            i += 2
    return cambios


def equipos_en(base: str) -> frozenset[str]:
    """Carpetas de `estudiantes/` que ya existen en el commit `base`."""
    salida = subprocess.run(
        ["git", "ls-tree", "-z", "--name-only", f"{base}:estudiantes"],
        capture_output=True,
        check=True,
    ).stdout.decode()
    return frozenset(filter(None, salida.split("\0")))


def revisar(
    cambios: list[tuple[str, str, tuple[str, str]]], existentes: frozenset[str] = frozenset()
) -> tuple[str | None, list[str]]:
    """(equipo, errores). `equipo` es None si hay errores.

    `existentes`: carpetas de equipo que ya están en la base; un PR no puede tocarlas.
    """
    if not cambios:
        return None, ["El PR no cambia ningún archivo."]
    por_equipo: dict[str, list[str]] = {}
    fuera: list[str] = []
    submodulos: list[str] = []
    for estado, ruta, modos in cambios:
        if SUBMODULO in modos:
            submodulos.append(ruta)
        partes = ruta.split("/")
        if len(partes) >= 3 and partes[0] == "estudiantes" and partes[1]:
            por_equipo.setdefault(partes[1], []).append(ruta)
        else:
            fuera.append(f"{ruta} ({ESTADOS.get(estado, estado)})")

    errores = []
    if submodulos:
        errores.append(
            "El PR agrega o cambia submódulos de git; no se aceptan (copia los archivos "
            "dentro de tu carpeta):\n" + "\n".join(f"  - {r}" for r in submodulos)
        )
    if fuera:
        errores.append(
            "El PR toca archivos fuera de estudiantes/<tu_equipo>/. Quítalos del PR "
            "(solo puedes cambiar tu carpeta):\n" + "\n".join(f"  - {r}" for r in fuera)
        )
    if len(por_equipo) > 1:
        errores.append(
            "El PR toca varias carpetas de equipo; solo puede tocar UNA (la tuya): "
            + ", ".join(f"estudiantes/{e}/" for e in sorted(por_equipo))
        )
    for equipo in sorted(por_equipo):
        if not NOMBRE.fullmatch(equipo):
            errores.append(
                f"El nombre de carpeta «{equipo}» no es válido. Usa de 3 a 30 caracteres: "
                "solo minúsculas sin acentos, dígitos y guion bajo (ej.: los_alfa_beta)."
            )
        elif es_reservado(equipo):
            errores.append(
                f"estudiantes/{equipo}/ es una carpeta reservada del curso (random, "
                "montecarlo, humano, tier_*, o que empiece con _). No la cambies: "
                "pon tu bot en estudiantes/<tu_equipo>/."
            )
        elif equipo in existentes:
            errores.append(
                f"estudiantes/{equipo}/ ya existe en el repo del torneo (otro equipo ya "
                "entregó con ese nombre, o ya entregaste). Tu PR solo puede agregar una "
                "carpeta NUEVA; si necesitas corregir una entrega aceptada, avisa al profesor."
            )
    if errores:
        return None, errores
    (equipo,) = por_equipo
    return equipo, []


def main(argv: list[str]) -> int:
    existentes: frozenset[str] = frozenset()
    if argv[:1] == ["--base"] and len(argv) == 2:
        existentes = equipos_en(argv[1])
    elif argv:
        print("uso: revisar_rutas.py [--base <sha>] < diff", file=sys.stderr)
        return 2
    equipo, errores = revisar(leer_cambios(sys.stdin.read()), existentes)
    if errores:
        for error in errores:
            print(f"✗ {error}", file=sys.stderr)
        return 1
    print(equipo)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
