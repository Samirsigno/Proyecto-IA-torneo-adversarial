"""Configuración común de los tests."""

import os
import py_compile
import shutil
import subprocess
from pathlib import Path

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "docker: necesita Docker (corre con `pytest -m docker`)")


def _docker_disponible() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


def pytest_collection_modifyitems(config, items):
    docker = [item for item in items if "docker" in item.keywords]
    if docker and not _docker_disponible():
        saltar = pytest.mark.skip(reason="Docker no está disponible")
        for item in docker:
            item.add_marker(saltar)


@pytest.fixture
def bot_con_pyc_viejo(tmp_path: Path) -> Path:
    """Bot cuyo __pycache__ trae un .pyc que no corresponde al .py (misma fecha y tamaño).

    Python normal usaría el .pyc ('pyc'); el runner debe correr el .py ('src') y el
    bot lo reporta en `info["valor"]`. Carpeta legible para el usuario del contenedor.
    """
    bot = tmp_path / "bot"
    bot.mkdir()
    (bot / "strategy.py").write_text(
        "from ayuda import VALOR\n"
        "from motor import Estado, reportar\n\n\n"
        "def preparar(config):\n    Estado.inicial().jugadas()\n\n\n"
        "def jugar(estado, tiempo_restante):\n"
        "    reportar(valor=VALOR)\n    return estado.jugadas()[0]\n"
    )
    ayuda = bot / "ayuda.py"
    ayuda.write_text("VALOR = 'pyc'\n")
    py_compile.compile(str(ayuda), doraise=True)
    fecha = ayuda.stat().st_mtime_ns
    ayuda.write_text("VALOR = 'src'\n")
    os.utime(ayuda, ns=(fecha, fecha))
    for ruta in [bot, *bot.rglob("*")]:
        ruta.chmod(0o755 if ruta.is_dir() else 0o644)
    return bot
