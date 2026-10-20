"""`manifest.json`: con qué se jugó la liga (para auditar y reproducir).

Guarda el sha256 de cada entrega, la versión del motor, el digest de la imagen de los
bots y la semilla maestra (se publica al terminar).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import motor

IMAGEN_BOTS = "torneo-bot-base:local"
_IGNORAR = {"__pycache__", ".pytest_cache", ".DS_Store"}


def hash_carpeta(carpeta: Path) -> str:
    """sha256 del árbol: rutas relativas (orden fijo) y contenido de cada archivo.

    Ignora `__pycache__`; los enlaces simbólicos cuentan por su destino escrito.
    """
    carpeta = Path(carpeta)
    h = hashlib.sha256()
    for ruta in sorted(carpeta.rglob("*"), key=lambda r: r.relative_to(carpeta).as_posix()):
        relativa = ruta.relative_to(carpeta)
        if _IGNORAR & set(relativa.parts):
            continue
        if ruta.is_symlink():
            h.update(b"L" + relativa.as_posix().encode() + b"\0" + os.readlink(ruta).encode())
        elif ruta.is_file():
            h.update(b"F" + relativa.as_posix().encode() + b"\0")
            h.update(hashlib.sha256(ruta.read_bytes()).digest())
    return h.hexdigest()


def digest_imagen(imagen: str = IMAGEN_BOTS) -> str | None:
    """`$TORNEO_IMAGEN_DIGEST` o el digest que reporta Docker; None si no se puede saber."""
    if os.environ.get("TORNEO_IMAGEN_DIGEST"):
        return os.environ["TORNEO_IMAGEN_DIGEST"]
    try:
        r = subprocess.run(
            ["docker", "image", "inspect", "--format", "{{.Id}}", imagen],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip() or None


def escribir_manifest(
    salida: Path,
    participantes: dict[str, Path],
    semilla_maestra: int,
    imagen: str = IMAGEN_BOTS,
) -> Path:
    """Escribe `salida/manifest.json` y regresa su ruta."""
    datos = {
        "version": 1,
        "semilla_maestra": semilla_maestra,
        "motor": motor.__version__,
        "imagen": {"nombre": imagen, "digest": digest_imagen(imagen)},
        "participantes": {
            equipo: {"sha256": hash_carpeta(carpeta)}
            for equipo, carpeta in sorted(participantes.items())
        },
    }
    ruta = Path(salida) / "manifest.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return ruta
