"""Auditoría de `requirements.txt` de un equipo.

Dos revisiones, en este orden (las llama `sistema/Dockerfile.equipo`):

1. `python -m validador.requirements --lineas <requirements.txt> [--salida <limpio.txt>]`
   Revisa los bytes CRUDOS: UTF-8 estricto, sin declaraciones `coding:`, y cada
   línea es `paquete==versión`, un comentario o vacía. Con `--salida` escribe un
   archivo LIMPIO con solo `paquete==versión`: pip lee ese archivo y nunca ve los
   bytes del equipo (así no hay trucos de codificación, opciones ni URLs).
2. `python -m validador.requirements <resolucion.json>`
   Revisa la resolución COMPLETA de pip (`pip install --dry-run --report`),
   dependencias indirectas incluidas: lista negra, que no cambien
   numpy/scipy/numba/llvmlite y que todo sea un wheel de files.pythonhosted.org.

Solo usa la biblioteca estándar y `config`: corre al construir la imagen.
Sale con código 1 e imprime los errores (en español) si algo no pasa.
"""

from __future__ import annotations

import codecs
import json
import re
import sys
from pathlib import Path

from config import SISTEMA
from validador.reglas import LISTA_NEGRA_PAQUETES, PREINSTALADOS, normalizar_paquete

# `paquete==versión`. Nombre PEP 508 sin extras; versión PEP 440 exacta, sin
# comodines ni «+local».
_LINEA = re.compile(
    r"(?P<nombre>[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)"
    r"==(?P<version>"
    r"(?:[0-9]+!)?[0-9]+(?:\.[0-9]+)*"  # época y release: 1!2.0.3
    r"(?:[-_.]?(?:a|b|c|rc|alpha|beta|pre|preview)[-_.]?[0-9]*)?"  # pre: 2.0rc1
    r"(?:[-_.]?(?:post|rev|r)[-_.]?[0-9]*)?"  # post: 2.0.post1
    r"(?:[-_.]?dev[-_.]?[0-9]*)?"  # dev: 2.0.dev3
    r")",
    re.IGNORECASE,
)
# Comentario como lo entiende pip: `#` al inicio o después de un espacio.
_COMENTARIO = re.compile(r"(^|\s+)#.*$")
# Declaración de codificación (PEP 263), que pip respeta en las 2 primeras líneas.
_CODIFICACION = re.compile(rb"coding[:=]")
_BOMS_PROHIBIDOS = (
    codecs.BOM_UTF32_LE,
    codecs.BOM_UTF32_BE,
    codecs.BOM_UTF16_LE,
    codecs.BOM_UTF16_BE,
)
PYPI = "https://files.pythonhosted.org/"

_FORMATO = (
    "Escribe una librería por línea, con versión exacta, así: paquete==1.2.3 "
    "(sin espacios, sin opciones, sin URLs)."
)


def fijadas(ruta: Path | None = None) -> dict[str, str]:
    """Versiones fijas de las librerías preinstaladas (`sistema/constraints.txt`)."""
    texto = (ruta or SISTEMA / "constraints.txt").read_text(encoding="utf-8")
    versiones: dict[str, str] = {}
    for linea in texto.splitlines():
        linea = linea.split("#", 1)[0].strip()
        if "==" in linea:
            nombre, version = linea.split("==", 1)
            versiones[normalizar_paquete(nombre.strip())] = version.strip()
    return versiones


def normalizar_version(version: str) -> str:
    """Forma normal mínima de una versión (PEP 440): `v2.4.0` → `2.4`, `1.0alpha1` → `1a1`.

    Solo para comparar igualdad cuando `packaging` no está (la imagen de bots no la trae).
    """
    v = version.strip().lower().removeprefix("v")
    v = re.sub(r"^0!", "", v)
    coincide = re.match(r"(\d+(?:\.\d+)*)(.*)", v)
    if coincide is None:
        return v
    partes = [int(p) for p in coincide[1].split(".")]
    while len(partes) > 1 and partes[-1] == 0:
        partes.pop()
    resto = coincide[2]
    for largo, corto in (("alpha", "a"), ("beta", "b"), ("preview", "rc"), ("pre", "rc")):
        resto = resto.replace(largo, corto)
    resto = re.sub(r"(?<![a-z])c(?=\d|$)", "rc", resto)
    resto = re.sub(r"[-_.]", "", resto)
    return ".".join(map(str, partes)) + resto


def misma_version(a: str, b: str) -> bool:
    """True si `a` y `b` son la misma versión según PEP 440."""
    try:
        from packaging.version import InvalidVersion, Version
    except ImportError:
        return normalizar_version(a) == normalizar_version(b)
    try:
        return Version(a) == Version(b)
    except InvalidVersion:
        return normalizar_version(a) == normalizar_version(b)


def _auditar_paquete(nombre: str, version: str, donde: str, versiones: dict[str, str]) -> list[str]:
    """Lista negra y librerías preinstaladas para un paquete ya leído."""
    normal = normalizar_paquete(nombre)
    if normal in LISTA_NEGRA_PAQUETES:
        return [
            f"{donde}: «{nombre}» está prohibido en el torneo (lista negra: compiladores, "
            "redes neuronales y red). Quítalo (si lo pide otra librería, quita esa librería); "
            "si crees que lo necesitas, pregúntale al profesor."
        ]
    fija = versiones.get(normal)
    if normal in PREINSTALADOS and fija and not misma_version(version, fija):
        return [
            f"{donde}: pide {nombre}=={version}, pero la imagen ya trae "
            f"{nombre}=={fija} y esa versión no se puede cambiar. "
            f"Borra esa línea (ya viene instalada) o cambia la librería que la pide."
        ]
    return []


def decodificar(datos: bytes) -> tuple[str | None, list[str]]:
    """Texto de requirements.txt en UTF-8 estricto, o los errores que lo impiden."""
    if datos.startswith(_BOMS_PROHIBIDOS):
        return None, [
            "requirements.txt está guardado en UTF-16/UTF-32. Guárdalo como UTF-8 "
            "(en tu editor: «Save with encoding» → UTF-8)."
        ]
    for n, linea in enumerate(datos.splitlines()[:2], start=1):
        if _CODIFICACION.search(linea):
            return None, [
                f"requirements.txt, línea {n}: no se permite declarar la codificación "
                "(«coding: ...»). Borra esa línea; el archivo debe ser UTF-8 normal."
            ]
    try:
        texto = datos.decode("utf-8")
    except UnicodeDecodeError as e:
        return None, [
            f"requirements.txt no es UTF-8 válido (byte {e.start}). Guárdalo como UTF-8 "
            "y escribe solo letras normales."
        ]
    return texto.removeprefix("﻿"), []


def auditar_lineas(
    texto: str, versiones: dict[str, str] | None = None
) -> tuple[list[str], list[str]]:
    """(errores, líneas limpias `paquete==versión`) de requirements.txt."""
    versiones = fijadas() if versiones is None else versiones
    errores: list[str] = []
    limpias: list[str] = []
    for n, cruda in enumerate(texto.splitlines(), start=1):
        linea = _COMENTARIO.sub("", cruda).strip()
        donde = f"requirements.txt, línea {n}"
        if not linea:
            continue
        muestra = linea[:60]
        if linea.startswith("-"):
            errores.append(
                f"{donde}: «{muestra}» es una opción de pip y no se permite "
                f"(nada de -e, -r, -c, --index-url, ...). {_FORMATO}"
            )
            continue
        if "://" in linea or "@" in linea:
            errores.append(
                f"{donde}: «{muestra}» apunta a una URL o a un archivo. Solo se instalan "
                f"paquetes de PyPI. {_FORMATO}"
            )
            continue
        coincide = _LINEA.fullmatch(linea)
        if coincide is None:
            errores.append(f"{donde}: «{muestra}» no tiene el formato correcto. {_FORMATO}")
            continue
        errores += _auditar_paquete(coincide["nombre"], coincide["version"], donde, versiones)
        limpias.append(f"{coincide['nombre']}=={coincide['version']}")
    return errores, limpias


def auditar_archivo(datos: bytes, versiones: dict[str, str] | None = None):
    """(errores, líneas limpias) a partir de los bytes crudos de requirements.txt."""
    texto, errores = decodificar(datos)
    if texto is None:
        return errores, []
    return auditar_lineas(texto, versiones)


def auditar_resolucion(reporte: dict, versiones: dict[str, str] | None = None) -> list[str]:
    """Errores de la resolución completa de pip (`pip install --dry-run --report`)."""
    versiones = fijadas() if versiones is None else versiones
    errores: list[str] = []
    instalar = reporte.get("install") if isinstance(reporte, dict) else None
    if not isinstance(instalar, list):
        return ["El reporte de pip no tiene la lista «install»: no se puede revisar."]
    for item in instalar:
        item = item if isinstance(item, dict) else {}
        datos = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        nombre, version = str(datos.get("name", "")), str(datos.get("version", ""))
        if not nombre:
            errores.append("El reporte de pip trae un paquete sin nombre: no se puede revisar.")
            continue
        directo = item.get("requested") is True
        donde = "requirements.txt" if directo else f"dependencia indirecta «{nombre}»"
        errores += _auditar_paquete(nombre, version, donde, versiones)
        info = item.get("download_info") if isinstance(item.get("download_info"), dict) else {}
        url = str(info.get("url", ""))
        if (
            "dir_info" in info
            or "vcs_info" in info
            or not url.startswith(PYPI)
            or not url.endswith(".whl")
        ):
            errores.append(
                f"{donde}: «{nombre}» no viene como wheel de PyPI ({url[:80] or 'sin URL'}). "
                "Solo se instalan paquetes de PyPI ya compilados (wheels)."
            )
    return errores


def _salir(errores: list[str]) -> int:
    if not errores:
        return 0
    print("Tu requirements.txt no pasa la revisión:", file=sys.stderr)
    for error in errores:
        print(f"  - {error}", file=sys.stderr)
    return 1


def main(argv: list[str]) -> int:
    if len(argv) in (2, 4) and argv[0] == "--lineas":
        salida = None
        if len(argv) == 4:
            if argv[2] != "--salida":
                return main([])
            salida = Path(argv[3])
        errores, limpias = auditar_archivo(Path(argv[1]).read_bytes())
        if not errores and salida is not None:
            salida.write_text("".join(f"{linea}\n" for linea in limpias), encoding="ascii")
        return _salir(errores)
    if len(argv) == 1 and not argv[0].startswith("-"):
        reporte = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
        return _salir(auditar_resolucion(reporte))
    print(
        "Uso: python -m validador.requirements --lineas <requirements.txt> "
        "[--salida <limpio.txt>]\n"
        "     python -m validador.requirements <resolucion.json>",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
