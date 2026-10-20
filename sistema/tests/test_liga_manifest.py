"""manifest.json: hashes de las entregas, versión del motor, imagen y semilla."""

import json

import motor
from liga.manifest import escribir_manifest, hash_carpeta


def equipo(carpeta, texto="def jugar(e, t): ..."):
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "strategy.py").write_text(texto)
    (carpeta / "data").mkdir(exist_ok=True)
    (carpeta / "data" / "tabla.bin").write_bytes(b"\x00\x01")
    return carpeta


def test_hash_carpeta_cambia_con_el_contenido_y_el_nombre(tmp_path):
    a = equipo(tmp_path / "a")
    h = hash_carpeta(a)
    assert h == hash_carpeta(equipo(tmp_path / "b"))  # mismo contenido, otra carpeta
    (a / "data" / "tabla.bin").write_bytes(b"\x00\x02")
    assert hash_carpeta(a) != h
    (a / "data" / "tabla.bin").write_bytes(b"\x00\x01")
    (a / "data" / "tabla.bin").rename(a / "data" / "otra.bin")
    assert hash_carpeta(a) != h


def test_hash_carpeta_ignora_pycache(tmp_path):
    a = equipo(tmp_path / "a")
    h = hash_carpeta(a)
    (a / "__pycache__").mkdir()
    (a / "__pycache__" / "strategy.cpython-312.pyc").write_bytes(b"x")
    assert hash_carpeta(a) == h


def test_escribir_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("TORNEO_IMAGEN_DIGEST", "sha256:abc")
    a, b = equipo(tmp_path / "eq" / "a"), equipo(tmp_path / "eq" / "b", "otro")
    ruta = escribir_manifest(tmp_path / "salida", {"b": b, "a": a}, semilla_maestra=42)
    datos = json.loads(ruta.read_text())
    assert ruta == tmp_path / "salida" / "manifest.json"
    assert datos["semilla_maestra"] == 42
    assert datos["motor"] == motor.__version__
    assert datos["imagen"]["digest"] == "sha256:abc"
    assert list(datos["participantes"]) == ["a", "b"]
    assert datos["participantes"]["a"]["sha256"] == hash_carpeta(a)
    assert datos["participantes"]["a"]["sha256"] != datos["participantes"]["b"]["sha256"]
