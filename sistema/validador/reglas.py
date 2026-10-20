"""Reglas fijas del validador: nombres, listas negras, binarios e informe.

Solo datos y funciones pequeñas sin dependencias (lo usa también
`validador.requirements`, que corre al construir la imagen del equipo).
"""

from __future__ import annotations

import re

# Nombre de carpeta/equipo: minúsculas, dígitos y guion bajo, 3–30 caracteres.
PATRON_NOMBRE = re.compile(r"^[a-z0-9_]{3,30}$")

# Paquetes que no se pueden instalar (nombres normalizados, PEP 503).
LISTA_NEGRA_PAQUETES: frozenset[str] = frozenset(
    {
        "torch",
        "tensorflow",
        "keras",
        "jax",
        "jaxlib",
        "onnxruntime",
        "cython",
        "pythran",
        "mypyc",
        "ray",
        "dask",
        "requests",
        "httpx",
        "urllib3",
        "aiohttp",
    }
)

# Paquetes preinstalados cuya versión no se puede cambiar.
PREINSTALADOS: tuple[str, ...] = ("numpy", "scipy", "numba", "llvmlite")

# Módulos prohibidos (primer nombre del import) y por qué.
# - Redes neuronales: error en el código de la liga; en herramientas/ (offline,
#   donde se permite «absolutamente todo») solo es aviso para revisión manual.
# - Sistema del torneo: error en cualquier archivo (está dentro de la imagen).
IMPORTS_REDES: dict[str, str] = dict.fromkeys(
    ("torch", "tensorflow", "keras", "jax", "jaxlib", "onnxruntime"),
    "es una librería de redes neuronales",
)
IMPORTS_SISTEMA: dict[str, str] = {
    **dict.fromkeys(
        ("arbitro", "liga", "validador", "cli", "visor"),
        "es código del sistema del torneo, no de tu bot",
    ),
    "estudiantes": "es la carpeta de otros equipos",
}
IMPORTS_PROHIBIDOS: dict[str, str] = {**IMPORTS_REDES, **IMPORTS_SISTEMA}

# Carpeta de herramientas offline: no se ejecuta en la liga.
CARPETA_HERRAMIENTAS = "herramientas"

# Llamadas que ejecutan o importan código elegido en tiempo de ejecución.
LLAMADAS_IMPORTAR = frozenset({"__import__", "import_module"})
LLAMADAS_EJECUTAR = frozenset({"exec", "eval", "compile"})
LLAMADAS_CARGAR = frozenset(
    {
        "run_path",
        "run_module",
        "spec_from_file_location",
        "exec_module",
        "load_module",
        "resolve_name",  # pkgutil.resolve_name("modulo:objeto")
        "InteractiveInterpreter",  # code.InteractiveInterpreter().runsource(...)
        "InteractiveConsole",
    }
)
# `x[...]` sobre estos objetos llega a funciones sin escribir su nombre.
NOMBRES_DICCIONARIO_GLOBAL = frozenset({"__builtins__"})
LLAMADAS_DICCIONARIO_GLOBAL = frozenset({"vars", "globals", "locals"})

# Máximo de archivos en la carpeta de un equipo.
MAX_ARCHIVOS = 2000

# Binarios: extensiones y firmas («números mágicos») al inicio del archivo.
EXTENSIONES_BINARIAS: frozenset[str] = frozenset({".so", ".dylib", ".dll", ".exe", ".pyd"})
FIRMAS_BINARIAS: dict[bytes, str] = {
    b"\x7fELF": "ELF (Linux)",
    b"\xfe\xed\xfa\xce": "Mach-O (Mac)",
    b"\xfe\xed\xfa\xcf": "Mach-O (Mac)",
    b"\xce\xfa\xed\xfe": "Mach-O (Mac)",
    b"\xcf\xfa\xed\xfe": "Mach-O (Mac)",
}
MAGIA_UNIVERSAL = b"\xca\xfe\xba\xbe"  # Mach-O universal… o un .class de Java

# Secciones obligatorias de INFORME.md (se buscan por número: «## 3. ...»).
SECCIONES_INFORME: tuple[str, ...] = (
    "Integrantes",
    "Idea en un párrafo",
    "Búsqueda (algoritmo y por qué)",
    "Función de evaluación",
    "Precomputación (qué y cómo regenerarla)",
    "Manejo del reloj",
    "Resultados vs random y montecarlo",
    "Qué intentamos y no funcionó",
    "Fuentes y uso de IA",
)

# Texto de la plantilla (el informe de ejemplo de montecarlo) que no debe quedar.
TEXTOS_PLANTILLA: tuple[str, ...] = (
    "Ejemplo de cómo llenar el informe",
    "El tuyo debe ser más específico",
    "participante público de referencia",
    "Escrito por el equipo del curso",
)

# Un informe con esta similitud (0–1) o más con el de montecarlo es una copia.
SIMILITUD_MAXIMA_INFORME = 0.85


def normalizar_paquete(nombre: str) -> str:
    """Nombre de paquete normalizado (PEP 503): `Foo_Bar.baz` → `foo-bar-baz`."""
    return re.sub(r"[-_.]+", "-", nombre).lower()


def firma_binaria(inicio: bytes, firma_pe: bytes = b"") -> str | None:
    """Tipo de binario si los primeros bytes son de un ejecutable; si no, None.

    `firma_pe`: los 4 bytes en la posición que indica `desplazamiento_pe(inicio)`
    (la cabecera PE puede estar más allá de lo que se leyó al inicio).
    """
    for magia, tipo in FIRMAS_BINARIAS.items():
        if inicio.startswith(magia):
            return tipo
    # Universal: luego viene el número de arquitecturas (pocas). En un .class de
    # Java ahí va la versión (≥ 45), así que no se confunden.
    if inicio.startswith(MAGIA_UNIVERSAL) and 0 < int.from_bytes(inicio[4:8], "big") < 30:
        return "Mach-O universal (Mac)"
    if inicio.startswith(b"MZ") and firma_pe == b"PE\x00\x00":
        return "PE (Windows)"
    return None


def desplazamiento_pe(inicio: bytes) -> int | None:
    """Posición de la firma «PE\\0\\0» si el archivo empieza con «MZ» (DOS/Windows)."""
    if inicio.startswith(b"MZ") and len(inicio) >= 0x40:
        return int.from_bytes(inicio[0x3C:0x40], "little")
    return None
