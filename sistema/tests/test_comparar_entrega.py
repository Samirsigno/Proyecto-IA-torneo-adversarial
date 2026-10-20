"""`herramientas/comparar_entrega.py`: huella de una carpeta según git y comparación."""

from __future__ import annotations

import shutil
import subprocess

import pytest

from herramientas import comparar_entrega as ce

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="falta git")


def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / "estudiantes" / "eq").mkdir(parents=True)
    (r / "estudiantes" / "eq" / "strategy.py").write_text("x = 1\n")
    (r / "estudiantes" / "eq" / "data").mkdir()
    (r / "estudiantes" / "eq" / "data" / "t.json").write_text("{}\n")
    (r / "otro.txt").write_text("no cuenta\n")
    _git(r, "init", "-q")
    _git(r, "-c", "user.email=a@b", "-c", "user.name=a", "add", ".")
    _git(r, "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "uno")
    return r


def _commit(repo, mensaje):
    _git(repo, "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qam", mensaje)
    return _git(repo, "rev-parse", "HEAD")


def test_arbol_local_solo_la_carpeta(repo):
    arbol = ce.arbol_local(repo, "HEAD", "estudiantes/eq")
    assert set(arbol) == {"strategy.py", "data/t.json"}


def test_arbol_remoto_igual_al_local(repo):
    """El árbol de la API de GitHub (con rutas desde la raíz) da la misma huella."""
    sha = _git(repo, "rev-parse", "HEAD")
    entradas = []
    for linea in _git(repo, "ls-tree", "-r", "-t", sha).splitlines():
        modo, tipo, objeto, ruta = linea.split(None, 3)
        entradas.append({"path": ruta, "mode": modo, "type": tipo, "sha": objeto})

    def falso_gh(ruta_api):
        assert ruta_api == f"repos/alumno/su_repo/git/trees/{sha}?recursive=1"
        return {"tree": entradas, "truncated": False}

    remoto = ce.arbol_remoto("alumno/su_repo", sha, "estudiantes/eq", gh=falso_gh)
    local = ce.arbol_local(repo, "HEAD", "estudiantes/eq")
    assert remoto == local
    assert ce.huella(remoto) == ce.huella(local)


def test_comparar_reporta_diferencias(repo):
    antes = ce.arbol_local(repo, "HEAD", "estudiantes/eq")
    (repo / "estudiantes" / "eq" / "strategy.py").write_text("x = 2\n")
    (repo / "otro.txt").write_text("cambia fuera\n")
    _commit(repo, "dos")
    despues = ce.arbol_local(repo, "HEAD", "estudiantes/eq")
    dif = ce.comparar(antes, despues)
    assert dif.cambiados == ["strategy.py"] and not dif.agregados and not dif.quitados
    assert not ce.comparar(antes, antes).hay
    assert ce.huella(antes) != ce.huella(despues)


def test_main_coincide_y_codigo_de_salida(repo, capsys, monkeypatch):
    sha = _git(repo, "rev-parse", "HEAD")
    arbol = ce.arbol_local(repo, sha, "estudiantes/eq")
    monkeypatch.setattr(ce, "arbol_remoto", lambda *a, **k: arbol)
    codigo = ce.main(
        [
            "--repo",
            "alumno/su_repo",
            "--sha",
            sha,
            "--carpeta",
            "estudiantes/eq",
            "--local",
            str(repo),
        ]
    )
    assert codigo == 0 and "Coinciden" in capsys.readouterr().out
    monkeypatch.setattr(ce, "arbol_remoto", lambda *a, **k: {})
    codigo = ce.main(
        [
            "--repo",
            "alumno/su_repo",
            "--sha",
            sha,
            "--carpeta",
            "estudiantes/eq",
            "--local",
            str(repo),
        ]
    )
    assert codigo == 1 and "strategy.py" in capsys.readouterr().out


def test_solo_huella(repo, capsys):
    assert ce.main(["--huella", "estudiantes/eq", "--local", str(repo)]) == 0
    salida = capsys.readouterr().out
    assert ce.huella(ce.arbol_local(repo, "HEAD", "estudiantes/eq")) in salida


def test_submodulo_cuenta_igual_en_los_dos_arboles():
    """Un gitlink (tipo commit) aparece en ambos árboles: no puede «desaparecer» de uno."""
    datos = {
        "tree": [
            {"path": "estudiantes/eq/lib", "mode": "160000", "type": "commit", "sha": "a" * 40},
            {"path": "estudiantes/eq/data", "mode": "040000", "type": "tree", "sha": "b" * 40},
        ]
    }
    remoto = ce.arbol_remoto("x/y", "s", "estudiantes/eq", gh=lambda _ruta: datos)
    assert remoto == {"lib": ("160000", "a" * 40)}
