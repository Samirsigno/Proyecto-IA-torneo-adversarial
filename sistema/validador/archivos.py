"""Revisión de los archivos de la carpeta: enlaces, cachés, binarios, tamaños y permisos.

Recorre la carpeta UNA vez y regresa la lista de archivos normales; lo demás
(enlaces, `__pycache__`, archivos especiales) es error. Nunca lanza excepciones:
un archivo que no se puede leer es un error del reporte.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass, field
from pathlib import Path

from config import Limites
from validador import reglas

MB = 1024 * 1024
_PYC_SUELTO = "Borra los .pyc y .pyo: no se permite código Python compilado."


@dataclass
class Inventario:
    archivos: list[Path] = field(default_factory=list)  # archivos normales, ordenados
    errores: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def _rel(carpeta: Path, ruta: Path) -> str:
    return ruta.relative_to(carpeta).as_posix()


def revisar_archivos(carpeta: Path, limites: Limites) -> Inventario:
    inv = Inventario()
    total = 0
    sin_lectura: list[str] = []
    cache: list[str] = []
    sueltos: list[str] = []
    fallas: list[OSError] = []
    for raiz, dirs, archivos in os.walk(carpeta, onerror=fallas.append):
        base = Path(raiz)
        for nombre in sorted(dirs):
            ruta = base / nombre
            rel = _rel(carpeta, ruta)
            try:
                info = ruta.lstat()
            except OSError:
                inv.errores.append(f"{rel}: no se pudo leer. Revisa sus permisos.")
                continue
            if stat.S_ISLNK(info.st_mode):
                inv.errores.append(
                    f"{rel} es un enlace simbólico. No se permiten enlaces: pon la carpeta real."
                )
            elif nombre == "__pycache__":
                cache.append(rel + "/")
            elif info.st_mode & (stat.S_IROTH | stat.S_IXOTH) != stat.S_IROTH | stat.S_IXOTH:
                sin_lectura.append(rel + "/")
        # No se entra a enlaces (ya son error). A __pycache__ sí: cuenta para el tamaño.
        dirs[:] = sorted(d for d in dirs if not (base / d).is_symlink())
        en_cache = base.name == "__pycache__"
        for nombre in sorted(archivos):
            ruta = base / nombre
            rel = _rel(carpeta, ruta)
            try:
                info = ruta.lstat()
            except OSError:
                inv.errores.append(f"{rel}: no se pudo leer. Revisa sus permisos.")
                continue
            if stat.S_ISLNK(info.st_mode):
                inv.errores.append(
                    f"{rel} es un enlace simbólico. No se permiten enlaces: pon el archivo real."
                )
                continue
            if not stat.S_ISREG(info.st_mode):
                inv.errores.append(f"{rel} no es un archivo normal. Bórralo.")
                continue
            if len(inv.archivos) >= reglas.MAX_ARCHIVOS:
                inv.errores.append(
                    f"Tu carpeta tiene más de {reglas.MAX_ARCHIVOS} archivos. Junta tus datos "
                    "en menos archivos (por ejemplo, un solo .npz o .pkl)."
                )
                return inv
            inv.archivos.append(ruta)
            if info.st_mode & stat.S_IROTH == 0:
                sin_lectura.append(rel)
            total += info.st_size
            if info.st_size > limites.archivo_mb * MB:
                inv.errores.append(
                    f"{rel} ocupa {info.st_size / MB:.1f} MB y el límite por archivo es "
                    f"{limites.archivo_mb} MB. Hazlo más chico o pártelo."
                )
            if ruta.suffix.lower() in (".pyc", ".pyo"):
                if not en_cache:
                    sueltos.append(rel)
                continue
            _revisar_binario(ruta, rel, info.st_size, inv.errores)
    for falla in fallas:
        inv.errores.append(f"No se pudo leer {falla.filename}. Revisa sus permisos.")
    if total > limites.carpeta_mb * MB:
        inv.errores.append(
            f"La carpeta ocupa {total / MB:.1f} MB y el límite es {limites.carpeta_mb} MB. "
            "Reduce data/."
        )
    if sueltos:
        muestra = ", ".join(sueltos[:5]) + (" ..." if len(sueltos) > 5 else "")
        inv.errores.append(f"Hay código Python compilado suelto ({muestra}). {_PYC_SUELTO}")
    if cache:
        muestra = ", ".join(cache[:5]) + (" ..." if len(cache) > 5 else "")
        inv.avisos.append(
            f"Hay carpetas __pycache__ ({muestra}): se ignoran, el torneo no usa tus .pyc. "
            "Puedes borrarlas."
        )
    if sin_lectura:
        muestra = ", ".join(sin_lectura[:5]) + (" ..." if len(sin_lectura) > 5 else "")
        inv.avisos.append(
            f"Estos archivos no los pueden leer otros usuarios: {muestra}. En la liga tu bot "
            f"corre con otro usuario y no los podrá abrir. Arréglalo con: chmod -R a+rX "
            f"estudiantes/{carpeta.resolve().name}"
        )
    return inv


def _revisar_binario(ruta: Path, rel: str, tamano: int, errores: list[str]) -> None:
    sufijo = ruta.suffix.lower()
    if sufijo in reglas.EXTENSIONES_BINARIAS:
        errores.append(
            f"{rel}: no se permiten archivos {sufijo} (código nativo). Solo Python (y numba)."
        )
        return
    try:
        with ruta.open("rb") as f:
            inicio = f.read(4096)
            firma_pe = b""
            pe = reglas.desplazamiento_pe(inicio)
            if pe is not None and pe + 4 <= tamano:
                f.seek(pe)
                firma_pe = f.read(4)
    except OSError:
        errores.append(f"{rel}: no se pudo leer. Revisa sus permisos.")
        return
    tipo = reglas.firma_binaria(inicio, firma_pe)
    if tipo:
        errores.append(
            f"{rel} es un programa ejecutable ({tipo}). No se permite código nativo: bórralo."
        )
