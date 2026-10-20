"""Publicación: tabla.csv, calificaciones cifradas, resumen.md y sitio."""

import json
import shutil
import subprocess

import pytest

from liga.calificacion import calificar
from liga.publicar import publicar
from liga.tabla import construir_tabla

hay_age = pytest.mark.skipif(
    shutil.which("age") is None or shutil.which("age-keygen") is None,
    reason="Falta el programa `age` (instálalo para probar el cifrado de verdad)",
)

CLAVE = "000123456"
SECRETO_INFO = "pesos-del-tier-xyz"
SECRETO_SALIDA = "imprimi-mi-estrategia-abc"
CLAVES = {
    "ana": [
        {"nombre": "Ana Pérez", "clave_unica": CLAVE},
        {"nombre": "Luis Gómez", "clave_unica": "000654321"},
    ]
}
INCIDENTES = [
    {"pareja": 9, "equipos": ["beto", "tier_1"], "fallas": ["juego 0: Docker"], "excluida": True}
]


def reg(pareja: int, juego: int, blancas: str, negras: str, ganador: str, motivo: str) -> dict:
    return {
        "version": 1,
        "meta": {
            "blancas": blancas,
            "negras": negras,
            "pareja": pareja,
            "juego": juego,
            "semilla_maestra": 5,
        },
        "jugadas": [
            {
                "n": 1,
                "color": "blancas",
                "jugada": "a2-a3",
                "combate": None,
                "tiempo": 0.1,
                "reloj": 0.1,
                "info": {"eval": 0.5, "secreto": SECRETO_INFO},
            }
        ],
        "ganador": ganador,
        "motivo": motivo,
        "puntos": {
            "blancas": 3 if ganador == "blancas" else 1,
            "negras": 3 if ganador == "negras" else 0,
        },
        "reloj_usado": {"blancas": 0.1, "negras": 0.0},
        "salidas": {"blancas": SECRETO_SALIDA, "negras": SECRETO_SALIDA},
    }


@pytest.fixture
def liga(tmp_path):
    """Una liga ya jugada en `tmp_path/liga` (ana, montecarlo, random)."""
    salida = tmp_path / "liga"
    (salida / "parejas").mkdir(parents=True)
    parejas = {
        0: [
            reg(0, 0, "ana", "montecarlo", "blancas", "puntos"),
            reg(0, 0, "montecarlo", "ana", "negras", "reloj"),
            reg(0, 1, "ana", "montecarlo", "negras", "ilegal"),
            reg(0, 1, "montecarlo", "ana", "blancas", "puntos"),
        ],
        1: [
            reg(1, 0, "ana", "random", "blancas", "puntos"),
            reg(1, 0, "random", "ana", "negras", "puntos"),
            reg(1, 1, "ana", "random", "blancas", "puntos"),
            reg(1, 1, "random", "ana", "blancas", "sin_jugadas"),
        ],
        2: [
            reg(2, 0, "montecarlo", "random", "blancas", "puntos"),
            reg(2, 0, "random", "montecarlo", "negras", "puntos"),
            reg(2, 1, "montecarlo", "random", "blancas", "puntos"),
            reg(2, 1, "random", "montecarlo", "negras", "puntos"),
        ],
    }
    registros = []
    for p, regs in parejas.items():
        (salida / "parejas" / f"{p}.json").write_text(
            json.dumps({"version": 1, "pareja": p, "registros": regs})
        )
        registros += regs
    tabla = construir_tabla(registros, semilla_maestra=5)
    notas = calificar(tabla, {"random": 1, "montecarlo": 3}, {"ana"})
    return salida, tabla, notas


@pytest.fixture
def llaves(tmp_path):
    privada = tmp_path / "llave.txt"
    subprocess.run(["age-keygen", "-o", str(privada)], check=True, capture_output=True)
    publica = tmp_path / "llave.age.pub"
    salida = subprocess.run(
        ["age-keygen", "-y", str(privada)], check=True, capture_output=True, text=True
    )
    publica.write_text(salida.stdout)
    return privada, publica


def sin_claves(carpeta) -> None:
    for archivo in carpeta.rglob("*"):
        if archivo.is_file() and archivo.suffix != ".age":
            texto = archivo.read_text(errors="replace")
            assert CLAVE not in texto, archivo
            assert "Ana Pérez" not in texto, archivo


def no_hay_calificaciones_en_claro(carpeta) -> None:
    assert not (carpeta / "calificaciones.csv").exists()
    assert not [
        a for a in carpeta.rglob("*") if a.name.startswith("calificaciones") and a.suffix != ".age"
    ]


@hay_age
def test_calificaciones_nunca_en_claro(liga, llaves, tmp_path):
    salida, tabla, notas = liga
    privada, publica = llaves
    publicar(
        salida, tabla, notas, INCIDENTES, claves=CLAVES, llave=publica, aceptar_incidentes=True
    )
    no_hay_calificaciones_en_claro(tmp_path)
    cifrado = salida / "calificaciones.csv.age"
    assert cifrado.read_bytes().startswith(b"age-encryption.org/v1")
    assert CLAVE.encode() not in cifrado.read_bytes()
    claro = subprocess.run(
        ["age", "-d", "-i", str(privada), str(cifrado)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    lineas = claro.splitlines()
    assert lineas[0] == "equipo,posicion,puntos,calificacion,nombre,clave_unica"
    filas = [linea.split(",") for linea in lineas[1:]]
    assert {f[5] for f in filas} == {CLAVE, "000654321"}
    assert all(f[0] == "ana" and float(f[3]) == notas["ana"] for f in filas)


def test_sin_llave_se_niega_y_no_escribe_en_claro(liga, tmp_path):
    salida, tabla, notas = liga
    with pytest.raises(FileNotFoundError, match="llave pública"):
        publicar(salida, tabla, notas, [], claves=CLAVES, llave=tmp_path / "no_existe.pub")
    no_hay_calificaciones_en_claro(tmp_path)
    assert not (salida / "calificaciones.csv.age").exists()


def test_sin_programa_age_se_niega(liga, tmp_path, monkeypatch):
    salida, tabla, notas = liga
    publica = tmp_path / "llave.age.pub"
    publica.write_text("age1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq\n")
    monkeypatch.setattr("liga.publicar.shutil.which", lambda _: None)
    with pytest.raises(RuntimeError, match="age"):
        publicar(salida, tabla, notas, [], claves=CLAVES, llave=publica)
    no_hay_calificaciones_en_claro(tmp_path)
    assert not (salida / "calificaciones.csv.age").exists()


@hay_age
def test_resumen_md_sin_claves_unicas(liga, llaves):
    salida, tabla, notas = liga
    publicar(
        salida, tabla, notas, INCIDENTES, claves=CLAVES, llave=llaves[1], aceptar_incidentes=True
    )
    resumen = (salida / "resumen.md").read_text()
    sin_claves(salida)
    lineas = resumen.splitlines()
    assert any("Posición" in linea and "Calificación" in linea and "%" in linea for linea in lineas)
    fila_ana = next(linea for linea in lineas if "| ana |" in linea)
    assert f"{notas['ana']:g}" in fila_ana
    assert any("*random*" in linea for linea in lineas)  # referencias en cursiva
    assert any("*montecarlo*" in linea for linea in lineas)
    incidentes = [linea for linea in lineas if "ncidente" in linea]
    assert len(incidentes) == 1 and "9" in incidentes[0]


@hay_age
def test_tabla_csv(liga, llaves):
    salida, tabla, notas = liga
    publicar(salida, tabla, notas, [], claves=CLAVES, llave=llaves[1])
    filas = (salida / "tabla.csv").read_text().splitlines()
    assert filas[0].startswith("posicion,equipo,puntos")
    assert len(filas) == 1 + len(tabla)
    assert filas[1].split(",")[1] == tabla[0].equipo


@hay_age
def test_sitio_con_paginas_por_equipo_y_motivos(liga, llaves):
    salida, tabla, notas = liga
    publicar(
        salida, tabla, notas, INCIDENTES, claves=CLAVES, llave=llaves[1], aceptar_incidentes=True
    )
    sitio = salida / "sitio"
    index = (sitio / "index.html").read_text()
    for fila in tabla:
        assert f"equipos/{fila.equipo}.html" in index
        assert (sitio / "equipos" / f"{fila.equipo}.html").exists()
    ana = (sitio / "equipos" / "ana.html").read_text()
    # ana perdió por jugada ilegal (pareja 0, juego 1) y por sin_jugadas (pareja 1, juego 1).
    assert "Jugada ilegal" in ana
    assert "sin jugadas" in ana
    # Cada partida tiene su registro publicado y la página de ana enlaza sus 8.
    assert len(list((sitio / "partidas").glob("*.json"))) == 12
    assert ana.count('href="../partidas/') >= 8


@hay_age
def test_sitio_sin_info_ni_salidas_de_ningun_bot(liga, llaves):
    salida, tabla, notas = liga
    publicar(salida, tabla, notas, [], claves=CLAVES, llave=llaves[1])
    archivos = [a for a in (salida / "sitio").rglob("*") if a.is_file()]
    assert any(a.suffix == ".html" and a.parent.name == "partidas" for a in archivos)
    for archivo in archivos:
        texto = archivo.read_text(errors="replace")
        assert SECRETO_INFO not in texto and SECRETO_SALIDA not in texto, archivo
    for archivo in (salida / "sitio" / "partidas").glob("*.json"):
        datos = json.loads(archivo.read_text())
        assert "salidas" not in datos
        assert all("info" not in j for j in datos["jugadas"])
    # El registro completo sigue en parejas/ (artifact no público).
    assert SECRETO_SALIDA in (salida / "parejas" / "0.json").read_text()


def test_equipo_calificado_sin_claves_es_error(liga, tmp_path):
    salida, tabla, notas = liga
    publica = tmp_path / "llave.age.pub"
    publica.write_text("age1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq\n")
    for claves in (None, {}, {"ana": []}, {"ana": [{"nombre": "Ana", "clave_unica": ""}]}):
        with pytest.raises(ValueError, match="clave única.*ana"):
            publicar(salida, tabla, notas, [], claves=claves, llave=publica)
    assert not (salida / "calificaciones.csv.age").exists()
    assert not (salida / "tabla.csv").exists()


def test_parejas_excluidas_impiden_publicar(liga, tmp_path):
    salida, tabla, notas = liga
    with pytest.raises(ValueError, match="excluidas.*9.*aceptar_incidentes"):
        publicar(salida, tabla, notas, INCIDENTES, claves=CLAVES, llave=tmp_path / "x.pub")
    assert not (salida / "calificaciones.csv.age").exists()
    assert not (salida / "sitio").exists()
    # Una pareja repetida y completa (no excluida) no impide publicar: llega a la llave.
    repetida = [dict(INCIDENTES[0], excluida=False)]
    with pytest.raises(FileNotFoundError, match="llave pública"):
        publicar(salida, tabla, notas, repetida, claves=CLAVES, llave=tmp_path / "x.pub")


@hay_age
def test_republicar_borra_archivos_viejos_del_sitio(liga, llaves):
    salida, tabla, notas = liga
    publicar(salida, tabla, notas, [], claves=CLAVES, llave=llaves[1])
    viejo = salida / "sitio" / "equipos" / "equipo_que_ya_no_esta.html"
    viejo.write_text("viejo")
    publicar(salida, tabla, notas, [], claves=CLAVES, llave=llaves[1])
    assert not viejo.exists()
    assert (salida / "sitio" / "index.html").exists()
    assert not [p for p in salida.iterdir() if p.name.startswith(".")]  # sin temporales
    assert oct((salida / "tabla.csv").stat().st_mode & 0o777) == "0o644"
