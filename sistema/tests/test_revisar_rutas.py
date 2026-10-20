"""`.github/scripts/revisar_rutas.py`: el PR solo puede tocar UNA carpeta de equipo."""

from __future__ import annotations

import importlib.util
import io

import pytest

from config import RAIZ, RESERVADOS, es_reservado
from validador import reglas


def _revisor():
    ruta = RAIZ / ".github" / "scripts" / "revisar_rutas.py"
    spec = importlib.util.spec_from_file_location("revisar_rutas", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


SHA = "0" * 40


def _diff(*cambios: str) -> str:
    """«A\\truta» (o «A\\truta\\t160000») … → salida de `git diff --raw --no-renames -z`."""
    texto = ""
    for cambio in cambios:
        estado, ruta, *modo = cambio.split("\t")
        nuevo = modo[0] if modo else "100644"
        antes = "000000" if estado == "A" else nuevo
        despues = "000000" if estado == "D" else nuevo
        texto += f":{antes} {despues} {SHA} {SHA} {estado}\0{ruta}\0"
    return texto


def test_acepta_una_carpeta_de_equipo():
    r = _revisor()
    cambios = r.leer_cambios(
        _diff(
            "A\testudiantes/los_alfa/strategy.py",
            "M\testudiantes/los_alfa/data/t.json",
            "D\testudiantes/los_alfa/viejo.py",
        )
    )
    assert r.revisar(cambios) == ("los_alfa", [])


@pytest.mark.parametrize(
    "cambios, texto",
    [
        (["M\tsistema/motor/reglas.py", "A\testudiantes/los_alfa/strategy.py"], "sistema/motor"),
        (["M\t.github/workflows/revisar-pr.yml"], ".github/workflows"),
        (["M\tREADME.md"], "README.md"),
        (["D\ttorneo"], "torneo (borrado)"),
        (["A\testudiantes/los_alfa/s.py", "A\testudiantes/los_beta/s.py"], "varias carpetas"),
        (["M\testudiantes/random/strategy.py"], "reservada"),
        (["A\testudiantes/tier_9/strategy.py"], "reservada"),
        (["A\testudiantes/Mi Equipo/strategy.py"], "no es válido"),
        (["A\testudiantes/archivo_suelto.py"], "estudiantes/archivo_suelto.py"),
        (["A\testudiantes/los_alfa/lib\t160000"], "submódulos"),
        ([], "no cambia"),
    ],
)
def test_rechaza(cambios, texto):
    r = _revisor()
    equipo, errores = r.revisar(r.leer_cambios(_diff(*cambios)))
    assert equipo is None
    assert texto in "\n".join(errores)


def test_renombre_revisa_las_dos_rutas():
    r = _revisor()
    texto = f":100644 100644 {SHA} {SHA} R100\0sistema/x.py\0estudiantes/los_alfa/x.py\0"
    equipo, errores = r.revisar(r.leer_cambios(texto))
    assert equipo is None and "sistema/x.py" in "\n".join(errores)


def test_nombres_iguales_que_el_validador():
    r = _revisor()
    assert r.NOMBRE.pattern == reglas.PATRON_NOMBRE.pattern
    assert set(r.RESERVADOS) == set(RESERVADOS)
    for nombre in ("random", "montecarlo", "humano", "tier_1", "tier_x", "_x", "los_alfa", "abc"):
        assert r.es_reservado(nombre) == es_reservado(nombre), nombre


def test_rechaza_carpeta_que_ya_existe_en_la_base():
    r = _revisor()
    cambios = r.leer_cambios(_diff("M\testudiantes/los_alfa/strategy.py"))
    equipo, errores = r.revisar(cambios, frozenset({"los_alfa", "random"}))
    assert equipo is None and "ya existe" in "\n".join(errores)
    assert r.revisar(cambios, frozenset({"los_beta"})) == ("los_alfa", [])


def test_equipos_en_lee_la_base_de_git(monkeypatch):
    r = _revisor()
    monkeypatch.chdir(RAIZ)
    assert {"random", "montecarlo"} <= r.equipos_en("HEAD")


def test_main_con_base_rechaza_carpeta_existente(monkeypatch, capsys):
    r = _revisor()
    monkeypatch.setattr(r, "equipos_en", lambda base: frozenset({"los_alfa"}))
    monkeypatch.setattr("sys.stdin", io.StringIO(_diff("A\testudiantes/los_alfa/x.py")))
    assert r.main(["--base", SHA]) == 1
    assert "ya existe" in capsys.readouterr().err
