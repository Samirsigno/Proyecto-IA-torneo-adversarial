"""Compara la carpeta entregada en un PR con el commit que el alumno registró.

El profesor lo corre en su máquina, desde un clon del repo del torneo con el PR bajado
(`gh pr checkout <n>`), usando su `gh` (que puede leer el repo privado del alumno):

    python3 sistema/herramientas/comparar_entrega.py \\
        --repo alumno/su_repo_privado --sha <sha_registrado> --carpeta estudiantes/<equipo>

Compara el árbol de `--carpeta` en ese SHA (vía la API de GitHub) con el de `--ref`
(default HEAD) del clon local y reporta si coinciden o qué archivos cambiaron.

`--huella estudiantes/<equipo>` solo imprime la huella local; `revisar-pr.yml` la imprime
igual, así que basta comparar las dos líneas.

Huella = sha256 de las líneas «modo sha_git ruta» de cada archivo de la carpeta (rutas
relativas, ordenadas). Usa solo la biblioteca estándar.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

Arbol = dict[str, tuple[str, str]]  # ruta relativa → (modo, sha del blob o del commit)
# Archivos y submódulos (gitlinks, modo 160000): igual en los dos árboles, así un
# submódulo cuenta como diferencia en vez de desaparecer de un lado.
TIPOS = ("blob", "commit")


def _carpeta(carpeta: str) -> str:
    return carpeta.strip("/") + "/"


def arbol_local(repo: Path | str, ref: str, carpeta: str) -> Arbol:
    """Archivos de `carpeta` en `ref` de un clon local (según git, no el disco)."""
    prefijo = _carpeta(carpeta)
    salida = subprocess.run(
        ["git", "-C", str(repo), "ls-tree", "-r", "-z", ref, "--", prefijo],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    arbol: Arbol = {}
    for linea in filter(None, salida.split("\0")):
        datos, ruta = linea.split("\t", 1)
        modo, tipo, objeto = datos.split()
        if tipo in TIPOS:
            arbol[ruta[len(prefijo) :]] = (modo, objeto)
    return arbol


def _gh_api(ruta: str) -> dict:
    r = subprocess.run(["gh", "api", ruta], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"`gh api {ruta}` falló: {r.stderr.strip()}")
    return json.loads(r.stdout)


def arbol_remoto(repo: str, sha: str, carpeta: str, gh: Callable[[str], dict] = _gh_api) -> Arbol:
    """Archivos de `carpeta` en el commit `sha` de `repo` (dueño/nombre), vía `gh api`."""
    datos = gh(f"repos/{repo}/git/trees/{sha}?recursive=1")
    if datos.get("truncated"):
        raise RuntimeError(
            f"La API regresó el árbol de {repo}@{sha} incompleto (repo muy grande). "
            "Clónalo y usa `git ls-tree` a mano."
        )
    prefijo = _carpeta(carpeta)
    return {
        e["path"][len(prefijo) :]: (e["mode"], e["sha"])
        for e in datos.get("tree", [])
        if e.get("type") in TIPOS and e["path"].startswith(prefijo)
    }


def huella(arbol: Arbol) -> str:
    texto = "".join(f"{modo} {sha} {ruta}\n" for ruta, (modo, sha) in sorted(arbol.items()))
    return hashlib.sha256(texto.encode()).hexdigest()


@dataclass
class Diferencias:
    agregados: list[str] = field(default_factory=list)  # en el PR, no en el SHA registrado
    quitados: list[str] = field(default_factory=list)  # en el SHA registrado, no en el PR
    cambiados: list[str] = field(default_factory=list)

    @property
    def hay(self) -> bool:
        return bool(self.agregados or self.quitados or self.cambiados)


def comparar(registrado: Arbol, entregado: Arbol) -> Diferencias:
    return Diferencias(
        agregados=sorted(set(entregado) - set(registrado)),
        quitados=sorted(set(registrado) - set(entregado)),
        cambiados=sorted(
            r for r in set(registrado) & set(entregado) if registrado[r] != entregado[r]
        ),
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--repo", help="repo privado del alumno (dueño/nombre)")
    p.add_argument("--sha", help="commit registrado por el alumno")
    p.add_argument("--carpeta", help="p. ej. estudiantes/mi_equipo")
    p.add_argument("--ref", default="HEAD", help="qué comparar del clon local (default HEAD)")
    p.add_argument("--local", default=".", help="clon local del repo del torneo")
    p.add_argument("--huella", metavar="CARPETA", help="solo imprime la huella local")
    args = p.parse_args(argv)

    if args.huella:
        arbol = arbol_local(args.local, args.ref, args.huella)
        print(f"Huella de {_carpeta(args.huella)} ({len(arbol)} archivos): {huella(arbol)}")
        return 0
    if not (args.repo and args.sha and args.carpeta):
        p.error("usa --repo, --sha y --carpeta (o solo --huella CARPETA)")

    try:
        registrado = arbol_remoto(args.repo, args.sha, args.carpeta)
        entregado = arbol_local(args.local, args.ref, args.carpeta)
    except (RuntimeError, subprocess.CalledProcessError, OSError) as e:
        print(f"✗ {e}", file=sys.stderr)
        return 2
    print(f"Registrado {args.repo}@{args.sha[:12]}: {huella(registrado)}")
    print(f"Entregado  {args.ref}:                  {huella(entregado)}")
    dif = comparar(registrado, entregado)
    if not dif.hay:
        print(f"✓ Coinciden: {len(entregado)} archivos idénticos en {_carpeta(args.carpeta)}")
        return 0
    print(f"✗ No coinciden en {_carpeta(args.carpeta)}:")
    for titulo, rutas in (
        ("Solo en el PR", dif.agregados),
        ("Solo en el SHA registrado", dif.quitados),
        ("Distintos", dif.cambiados),
    ):
        for ruta in rutas:
            print(f"  {titulo}: {ruta}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
