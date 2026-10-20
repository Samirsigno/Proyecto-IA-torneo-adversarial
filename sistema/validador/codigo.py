"""Revisión del código Python de un equipo (sin ejecutarlo): imports y carga dinámica.

- Error: imports del sistema del torneo (en cualquier archivo); redes neuronales y
  `import herramientas` en el código que corre en la liga.
- Aviso (revisión manual): imports o ejecución de código con nombres calculados
  (`__import__(x)`, `import_module(x)`, `exec(x)`, `getattr(builtins, x)`, ...),
  y redes neuronales dentro de `herramientas/` (offline).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from validador import reglas

_PROFUNDIDAD_MAXIMA = 3  # exec("exec('...')") anidados que se revisan


@dataclass
class Hallazgos:
    errores: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def _texto_literal(nodo: ast.AST | None) -> str | None:
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
        return nodo.value
    return None


def _argumento(llamada: ast.Call, posicion: int, nombre: str) -> ast.AST | None:
    if len(llamada.args) > posicion:
        return llamada.args[posicion]
    return next((k.value for k in llamada.keywords if k.arg == nombre), None)


def _es_builtins(funcion: ast.AST) -> bool:
    """True para `builtins.exec`, `__builtins__.eval`, ... (no para `re.compile`)."""
    base = funcion.value if isinstance(funcion, ast.Attribute) else None
    return isinstance(base, ast.Name) and base.id in ("builtins", "__builtins__")


class _Analizador(ast.NodeVisitor):
    def __init__(self, rel: str, en_herramientas: bool, h: Hallazgos, profundidad: int) -> None:
        self.rel, self.en_herramientas, self.h, self.profundidad = (
            rel,
            en_herramientas,
            h,
            profundidad,
        )
        self.prefijo = " (dentro de un exec)" if profundidad else ""
        # Nombres locales que apuntan a funciones de importar/ejecutar (alias).
        self.importadoras: set[str] = set(reglas.LLAMADAS_IMPORTAR)
        self.ejecutoras: set[str] = set(reglas.LLAMADAS_EJECUTAR)
        self.llamados: set[int] = set()
        # Nombres que el propio archivo define (def compile, eval = ..., from re import
        # compile): no son las funciones de Python.
        self.propios: set[str] = set()

    # --- Mensajes -----------------------------------------------------------------------
    def _donde(self, nodo: ast.AST) -> str:
        return f"{self.rel}, línea {getattr(nodo, 'lineno', '?')}{self.prefijo}"

    def _aviso(self, nodo: ast.AST, que: str) -> None:
        self.h.avisos.append(
            f"{self._donde(nodo)}: {que}. Se revisará a mano; si no hace falta, usa un "
            "import normal."
        )

    def _modulo(self, nodo: ast.AST, modulo: str) -> None:
        raiz = modulo.split(".")[0]
        donde = self._donde(nodo)
        if raiz in reglas.IMPORTS_SISTEMA:
            self.h.errores.append(
                f"{donde}: no se permite importar «{raiz}» ({reglas.IMPORTS_SISTEMA[raiz]}). "
                "Quita ese import."
            )
        elif raiz in reglas.IMPORTS_REDES:
            motivo = reglas.IMPORTS_REDES[raiz]
            if self.en_herramientas:
                self.h.avisos.append(
                    f"{donde}: importa «{raiz}» ({motivo}). En herramientas/ se permite, "
                    "pero se revisará a mano que no llegue a tu bot."
                )
            else:
                self.h.errores.append(
                    f"{donde}: no se permite importar «{raiz}» ({motivo}). Quita ese import."
                )
        elif raiz == reglas.CARPETA_HERRAMIENTAS and not self.en_herramientas:
            self.h.errores.append(
                f"{donde}: no se permite importar herramientas: herramientas/ no se ejecuta "
                "en la liga. Mueve a tu carpeta (fuera de herramientas/) lo que necesite tu bot."
            )

    # --- Imports ------------------------------------------------------------------------
    def visit_Import(self, nodo: ast.Import) -> None:
        for alias in nodo.names:
            self._modulo(nodo, alias.name)

    def visit_ImportFrom(self, nodo: ast.ImportFrom) -> None:
        if nodo.level == 0 and nodo.module:
            self._modulo(nodo, nodo.module)
        else:  # relativo: es un módulo del equipo; solo importa si es herramientas/
            nombres = [nodo.module] if nodo.module else [a.name for a in nodo.names]
            for modulo in nombres:
                if modulo.split(".")[0] == reglas.CARPETA_HERRAMIENTAS:
                    self._modulo(nodo, modulo)
        if nodo.level == 0 and nodo.module in ("importlib", "builtins"):
            for alias in nodo.names:
                local = alias.asname or alias.name
                if alias.name in reglas.LLAMADAS_IMPORTAR:
                    self.importadoras.add(local)
                elif alias.name in reglas.LLAMADAS_EJECUTAR:
                    self.ejecutoras.add(local)
        self.generic_visit(nodo)

    # --- Llamadas -----------------------------------------------------------------------
    def visit_Call(self, nodo: ast.Call) -> None:
        funcion = nodo.func
        self.llamados.add(id(funcion))
        nombre = funcion.id if isinstance(funcion, ast.Name) else None
        atributo = funcion.attr if isinstance(funcion, ast.Attribute) else None
        if nombre in self.importadoras or atributo in reglas.LLAMADAS_IMPORTAR:
            modulo = _texto_literal(_argumento(nodo, 0, "name"))
            if modulo is None:
                self._aviso(nodo, "importa un módulo con un nombre calculado")
            else:
                self._modulo(nodo, modulo)
        elif nombre in self.ejecutoras or (
            atributo in reglas.LLAMADAS_EJECUTAR and _es_builtins(funcion)
        ):
            argumento = _argumento(nodo, 0, "source")
            fuente = _texto_literal(argumento)
            if isinstance(argumento, ast.Constant) and isinstance(argumento.value, bytes):
                self._aviso(nodo, f"ejecuta bytes ({nombre or atributo})")
                fuente = argumento.value.decode("utf-8", errors="replace")
                self._revisar_literal(nodo, fuente)
            elif fuente is None:
                self._aviso(
                    nodo, f"ejecuta código armado en tiempo de ejecución ({nombre or atributo})"
                )
            else:
                self._revisar_literal(nodo, fuente)
        elif nombre in reglas.LLAMADAS_CARGAR or atributo in reglas.LLAMADAS_CARGAR:
            self._aviso(nodo, f"carga o ejecuta código de otra forma ({nombre or atributo})")
        elif nombre == "getattr" and nodo.args:
            base = nodo.args[0]
            base_nombre = base.id if isinstance(base, ast.Name) else None
            if base_nombre in ("builtins", "__builtins__", "importlib"):
                self._aviso(nodo, f"usa getattr sobre {base_nombre}")
        self.generic_visit(nodo)

    def _revisar_literal(self, nodo: ast.AST, fuente: str) -> None:
        if self.profundidad >= _PROFUNDIDAD_MAXIMA:
            self._aviso(nodo, "anida demasiados exec")
            return
        try:
            arbol = ast.parse(fuente)
        except (SyntaxError, ValueError):
            self._aviso(nodo, "ejecuta un texto que no es Python válido")
            return
        _analizar(arbol, self.rel, self.en_herramientas, self.h, self.profundidad + 1)

    # --- Acceso por diccionario: __builtins__["exec"], globals()["x"] ------------------
    def visit_Subscript(self, nodo: ast.Subscript) -> None:
        base = nodo.value
        if isinstance(base, ast.Name) and base.id in reglas.NOMBRES_DICCIONARIO_GLOBAL:
            self._aviso(nodo, f"usa {base.id}[...]")
        elif isinstance(base, ast.Attribute) and base.attr == "__dict__":
            self._aviso(nodo, "usa .__dict__[...]")
        elif (
            isinstance(base, ast.Call)
            and isinstance(base.func, ast.Name)
            and base.func.id in reglas.LLAMADAS_DICCIONARIO_GLOBAL
            and base.func.id not in self.propios
        ):
            self._aviso(nodo, f"usa {base.func.id}()[...]")
        self.generic_visit(nodo)

    # --- Referencias sin llamar (alias: f = eval; f(x)) ---------------------------------
    def visit_Name(self, nodo: ast.Name) -> None:
        if (
            isinstance(nodo.ctx, ast.Load)
            and id(nodo) not in self.llamados
            and nodo.id in (reglas.LLAMADAS_IMPORTAR | reglas.LLAMADAS_EJECUTAR)
            and nodo.id not in self.propios
        ):
            self._aviso(nodo, f"usa {nodo.id} sin llamarlo directamente")

    def visit_Attribute(self, nodo: ast.Attribute) -> None:
        if id(nodo) not in self.llamados and (
            nodo.attr in (reglas.LLAMADAS_IMPORTAR | reglas.LLAMADAS_CARGAR)
            or (nodo.attr in reglas.LLAMADAS_EJECUTAR and _es_builtins(nodo))
        ):
            self._aviso(nodo, f"usa {nodo.attr} sin llamarlo directamente")
        self.generic_visit(nodo)

    def visit_Expr(self, nodo: ast.Expr) -> None:
        if _texto_literal(nodo.value) is None:  # los docstrings no cuentan
            self.generic_visit(nodo)

    def visit_Constant(self, nodo: ast.Constant) -> None:
        texto = nodo.value
        if (
            not self.en_herramientas
            and isinstance(texto, str)
            and reglas.CARPETA_HERRAMIENTAS in texto
        ):
            self._aviso(nodo, "menciona herramientas/ (no se ejecuta en la liga)")


def _analizar(
    arbol: ast.AST, rel: str, en_herramientas: bool, h: Hallazgos, profundidad: int
) -> None:
    analizador = _Analizador(rel, en_herramientas, h, profundidad)
    # Primero: qué nombres se llaman directamente y cuáles define el propio archivo.
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call):
            analizador.llamados.add(id(nodo.func))
        elif isinstance(nodo, ast.Name) and isinstance(nodo.ctx, ast.Store):
            analizador.propios.add(nodo.id)
        elif isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            analizador.propios.add(nodo.name)
        elif isinstance(nodo, ast.arg):
            analizador.propios.add(nodo.arg)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module not in ("importlib", "builtins"):
            analizador.propios |= {a.asname or a.name for a in nodo.names}
        elif isinstance(nodo, ast.Import):
            analizador.propios |= {a.asname or a.name.split(".")[0] for a in nodo.names}
    sombreados = analizador.propios & (reglas.LLAMADAS_IMPORTAR | reglas.LLAMADAS_EJECUTAR)
    analizador.importadoras -= sombreados
    analizador.ejecutoras -= sombreados
    analizador.visit(arbol)


def revisar_python(rel: str, fuente: bytes, en_herramientas: bool) -> Hallazgos:
    """Errores y avisos de un archivo .py (`rel`: su ruta dentro de la carpeta)."""
    h = Hallazgos()
    try:
        arbol = ast.parse(fuente, filename=rel)
    except SyntaxError as e:
        h.errores.append(
            f"{rel}, línea {e.lineno or '?'}: Python no lo puede leer, hay un error de "
            f"sintaxis (detalle: {e.msg}). Corrígelo."
        )
        return h
    except ValueError as e:  # bytes nulos, codificación inválida
        h.errores.append(f"{rel}: Python no lo puede leer (detalle: {e}). Corrígelo.")
        return h
    except (RecursionError, MemoryError):
        h.errores.append(f"{rel}: el código está demasiado anidado para revisarlo. Simplifícalo.")
        return h
    try:
        _analizar(arbol, rel, en_herramientas, h, 0)
    except RecursionError:
        h.errores.append(f"{rel}: el código está demasiado anidado para revisarlo. Simplifícalo.")
    return h


def nombres_definidos(fuente: bytes) -> set[str] | None:
    """Nombres que el módulo define arriba (def, asignación, import); None si no compila."""
    try:
        arbol = ast.parse(fuente)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    nombres: set[str] = set()
    for nodo in arbol.body:
        if isinstance(nodo, ast.FunctionDef):
            nombres.add(nodo.name)
        elif isinstance(nodo, ast.Assign):
            nombres |= {t.id for t in nodo.targets if isinstance(t, ast.Name)}
        elif isinstance(nodo, ast.ImportFrom):
            nombres |= {a.asname or a.name for a in nodo.names}
    return nombres
