"""BotDocker: argumentos de `docker run` y partidas reales en contenedores aislados.

Los tests marcados `docker` construyen antes `torneo-bot-base:local` desde este
repo (el código de sistema/ va horneado en la imagen).
"""

import os
import subprocess
import uuid
from dataclasses import replace
from pathlib import Path

import pytest

from arbitro import procesos
from arbitro.azar import Dados, semilla_bots
from arbitro.partida import jugar_partida
from arbitro.procesos import BotDocker, BotLocal, BotNoSeCongela, FallaInfraestructura, arquitectura
from config import RAIZ, limites_prueba

BOTS = Path(__file__).parent / "bots"
LIMITES = limites_prueba()
IMAGEN = "torneo-bot-base:local"


def bot_docker(nombre: str, **kw) -> BotDocker:
    # TORNEO_NUCLEO_PRUEBA=<n> fija los bots de prueba a un núcleo (máquina compartida).
    nucleo = os.environ.get("TORNEO_NUCLEO_PRUEBA")
    nucleo = kw.pop("nucleo", int(nucleo) if nucleo else None)
    return BotDocker(BOTS / nombre, IMAGEN, nucleo, LIMITES, **kw)


# --- Argumentos (no necesitan Docker) -------------------------------------------------


def test_args_docker(monkeypatch):
    monkeypatch.delenv("TORNEO_SIN_CPUSET", raising=False)
    monkeypatch.delenv("TORNEO_RAIZ_HOST", raising=False)
    a = bot_docker("fiel", nucleo=2).argumentos()
    assert {
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--log-driver=none",
        "--pids-limit=64",
    } <= set(a) and "--rm" not in a
    assert a[:3] == ["docker", "run", "-i"]
    assert {"--cpus=1", "--cpuset-cpus=2", "--memory=1024m", "--memory-swap=1024m"} <= set(a)
    pares = list(zip(a, a[1:], strict=False))
    assert ("--tmpfs", "/tmp/numba:size=64m,noexec") in pares
    assert ("--user", "65534:65534") in pares
    assert ("--security-opt", "no-new-privileges") in pares
    assert ("-v", f"{BOTS / 'fiel'}:/bot:ro") in pares
    assert ("-v", f"torneo_numba_{arquitectura()}:/opt/numba_listo:ro") in pares
    variables = {b for x, b in pares if x == "-e"}
    assert variables == {
        "PYTHONDONTWRITEBYTECODE=1",
        "OMP_NUM_THREADS=1",
        "OPENBLAS_NUM_THREADS=1",
        "MKL_NUM_THREADS=1",
        "NUMBA_NUM_THREADS=1",
        "NUMBA_CACHE_DIR=/tmp/numba",
        "PYTHONPYCACHEPREFIX=/opt/pyc",
    }
    assert a[-5:] == [IMAGEN, "python", "-m", "arbitro.runner", "/bot"]


def test_args_docker_memoria_escalada():
    limites = replace(LIMITES, escala_limites=2.0)
    a = BotDocker(BOTS / "fiel", IMAGEN, None, limites).argumentos()
    assert "--memory=2048m" in a and "--memory-swap=2048m" in a


def test_ruta_traducida_al_host(monkeypatch):
    monkeypatch.delenv("TORNEO_RAIZ_HOST", raising=False)
    b = BotDocker(
        RAIZ / "estudiantes" / "eq", IMAGEN, None, LIMITES, raiz_host=Path("/home/x/repo")
    )
    assert "/home/x/repo/estudiantes/eq:/bot:ro" in b.argumentos()
    # También desde la variable de ambiente que exporta ./torneo.
    monkeypatch.setenv("TORNEO_RAIZ_HOST", "/home/y/repo")
    b = BotDocker(RAIZ / "estudiantes" / "eq", IMAGEN, None, LIMITES)
    assert "/home/y/repo/estudiantes/eq:/bot:ro" in b.argumentos()


def test_ruta_fuera_del_repo_se_rechaza(tmp_path):
    b = BotDocker(tmp_path, IMAGEN, None, LIMITES, raiz_host=Path("/home/x/repo"))
    with pytest.raises(ValueError, match="estudiantes"):
        b.argumentos()


def test_args_docker_sin_cpuset(monkeypatch):
    monkeypatch.setenv("TORNEO_SIN_CPUSET", "1")
    a = bot_docker("fiel", nucleo=2).argumentos()
    assert not any(x.startswith("--cpuset-cpus") for x in a)
    assert "--cpus=1" in a
    monkeypatch.delenv("TORNEO_SIN_CPUSET")
    assert not any(
        x.startswith("--cpuset-cpus") for x in bot_docker("fiel", nucleo=None).argumentos()
    )


class _ApiFalsa:
    """API de Docker que nunca logra pausar; `inspect_container` dice lo que se le pida."""

    def __init__(self, corriendo: bool):
        self.corriendo = corriendo
        self.intentos = 0

    def pause(self, nombre):
        import docker

        self.intentos += 1
        raise docker.errors.APIError("no se pudo congelar")

    def inspect_container(self, nombre):
        return {"State": {"Running": self.corriendo, "Paused": False}}


def _bot_con_api(api) -> BotDocker:
    bot = BotDocker(BOTS / "fiel", IMAGEN, None, LIMITES)
    bot._api = lambda: api
    return bot


def test_pausa_fallida_en_contenedor_vivo_es_del_bot(monkeypatch):
    monkeypatch.setattr(procesos, "_ASENTAR_S", 0.05)
    api = _ApiFalsa(corriendo=True)
    with pytest.raises(BotNoSeCongela):
        _bot_con_api(api).pausar()
    assert api.intentos >= 2  # reintentó durante la espera
    assert not issubclass(BotNoSeCongela, FallaInfraestructura)


def test_pausa_fallida_en_contenedor_muerto_no_lanza(monkeypatch):
    monkeypatch.setattr(procesos, "_ASENTAR_S", 0.05)
    _bot_con_api(_ApiFalsa(corriendo=False)).pausar()  # lo verán recibir/causa_muerte


# --- Partidas en Docker ------------------------------------------------------------------


@pytest.fixture(scope="session")
def _imagen_construida():
    """Construye la imagen de bots con el código actual de sistema/."""
    subprocess.run(
        [
            "docker",
            "build",
            "-q",
            "-f",
            str(RAIZ / "sistema" / "Dockerfile"),
            "--target",
            "bot",
            "-t",
            IMAGEN,
            str(RAIZ),
        ],
        check=True,
        capture_output=True,
    )
    return IMAGEN


def _llenar_cache(volumen: str, imagen: str) -> None:
    """Llena un volumen de caché de numba como lo hará `./torneo calentar`."""
    codigo = (
        "from motor import Estado, simular_al_azar\n"
        "e = Estado.inicial(); j = e.jugadas()[0]\n"
        "e.clave; e.prob_ataque(j); e.aplicar(j); simular_al_azar(e, 2, 1, 'blancas')"
    )
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network=none",
            "-v",
            f"{volumen}:/opt/numba_listo",
            "-e",
            "NUMBA_CACHE_DIR=/opt/numba_listo",
            "--user",
            "0",
            imagen,
            "python",
            "-c",
            codigo,
        ],
        check=True,
        capture_output=True,
    )


@pytest.fixture(scope="session")
def _cache_de_prueba(_imagen_construida):
    """Volumen de caché lleno, propio de los tests (no toca torneo_numba_<arch>)."""
    volumen = f"torneo_numba_pruebas{uuid.uuid4().hex[:8]}"
    _llenar_cache(volumen, _imagen_construida)
    yield volumen
    subprocess.run(["docker", "volume", "rm", "-f", volumen], capture_output=True)


@pytest.fixture
def imagen_bots(_imagen_construida, _cache_de_prueba, monkeypatch):
    """Imagen lista + caché de numba caliente: `preparar` no compila en frío.

    Así los tests no dependen de la carga de la máquina. La compilación en frío
    la prueba `test_docker_sin_cache_compila_antes_de_preparar`.
    """
    from arbitro import procesos

    sufijo = _cache_de_prueba.removeprefix("torneo_numba_")
    monkeypatch.setattr(procesos, "arquitectura", lambda: sufijo)
    return _imagen_construida


def partida(blancas, negras, semilla=1, limites=LIMITES):
    return jugar_partida(
        blancas,
        negras,
        Dados(semilla, 0, 0),
        limites,
        limites.efectivos(),
        semilla_bots(semilla, 0, 0),
    )


def _contenedores(nombre: str) -> str:
    return subprocess.run(
        ["docker", "ps", "-a", "-q", "--filter", f"name={nombre}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


@pytest.mark.docker
def test_docker_import_motor_con_flags_reales(imagen_bots):
    b, n = bot_docker("fiel"), bot_docker("fiel")
    r = partida(b, n)
    assert not r.falla_infraestructura, r.salidas
    assert r.motivo in {"puntos", "sin_jugadas"}, r.salidas
    assert b.memoria_pico_mb() and 10 < b.memoria_pico_mb() < LIMITES.memoria_mb
    # Sin --rm, pero el árbitro borra los contenedores al terminar.
    assert _contenedores(b.nombre) == "" and _contenedores(n.nombre) == ""


@pytest.mark.docker
def test_docker_memoria_pierde_por_memoria(imagen_bots):
    r = partida(bot_docker("memoria"), BotLocal(BOTS / "fiel"))
    assert (r.ganador, r.motivo) == ("negras", "memoria"), r.salidas
    assert not r.falla_infraestructura
    assert "memoria" in r.salidas["blancas"]


@pytest.mark.docker
def test_docker_maliciosos_motivos_exactos(imagen_bots):
    archivos_antes = sorted(p.name for p in (BOTS / "escribe").rglob("*"))

    r = partida(bot_docker("escribe"), bot_docker("fiel"))
    assert not r.falla_infraestructura, r.salidas
    if r.motivo != "error":
        assert r.motivo in {"puntos", "sin_jugadas"}, r.salidas
        escritos = [j["info"]["escritos"] for j in r.jugadas if j["color"] == "blancas"][0]
        assert escritos == [], escritos
    assert sorted(p.name for p in (BOTS / "escribe").rglob("*")) == archivos_antes

    r = partida(bot_docker("fiel"), bot_docker("red"))
    assert (r.ganador, r.motivo) == ("blancas", "error"), r.salidas
    assert "OSError" in r.salidas["negras"] or "unreachable" in r.salidas["negras"]

    r = partida(bot_docker("procesos"), bot_docker("fiel"))
    assert not r.falla_infraestructura, r.salidas
    assert r.ganador == "negras" and r.motivo in {"reloj", "error"}, r.salidas


@pytest.mark.docker
def test_docker_spam_y_basura(imagen_bots):
    r = partida(bot_docker("escribe_fd1"), bot_docker("spam"))
    assert (r.ganador, r.motivo) == ("blancas", "reloj"), r.salidas
    s = r.salidas["negras"]
    assert len(s.encode()) <= 64 * 1024 and not s.startswith("::") and "\n::" not in s
    assert "basura sin salto" in r.salidas["blancas"]
    assert "[runner]" not in r.salidas["blancas"]  # sin avisos de la caché de numba


@pytest.mark.docker
def test_docker_usa_cache_numba_de_la_maquina(imagen_bots, monkeypatch):
    # Volumen propio del test (en vez de torneo_numba_<arch>), llenado como lo hará
    # `./torneo calentar`: un contenedor con la caché escribible compila el motor.
    from arbitro import procesos

    volumen = f"torneo_numba_prueba{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(procesos, "arquitectura", lambda: volumen.removeprefix("torneo_numba_"))
    try:
        _llenar_cache(volumen, imagen_bots)
        r = partida(bot_docker("cache"), bot_docker("cache"))
        assert r.motivo in {"puntos", "sin_jugadas"}, r.salidas
        info = r.jugadas[0]["info"]
        assert (info["aciertos"], info["fallos"]) == (1, 0), info
    finally:
        subprocess.run(["docker", "volume", "rm", "-f", volumen], capture_output=True)


@pytest.mark.docker
def test_docker_sin_cache_compila_antes_de_preparar(imagen_bots, monkeypatch):
    from arbitro import procesos

    volumen = f"torneo_numba_vacio{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(procesos, "arquitectura", lambda: volumen.removeprefix("torneo_numba_"))
    try:
        # Sin caché, el runner compila el motor en frío al arrancar (antes de `hola`,
        # fuera de todo reloj). `preparar` amplio: aquí importa que no haya caché.
        r = partida(
            bot_docker("cache"), bot_docker("fiel"), limites=replace(LIMITES, preparar_s=60.0)
        )
        assert r.motivo in {"puntos", "sin_jugadas"}, r.salidas
        info = r.jugadas[0]["info"]
        assert info["aciertos"] == 0 and info["fallos"] >= 1, info
    finally:
        subprocess.run(["docker", "volume", "rm", "-f", volumen], capture_output=True)


class BotDockerQueMuere(BotDocker):
    """El contenedor arranca, pero el proceso termina antes de mandar `hola`."""

    IMAGEN_COMANDO = ("python", "-c", "import sys; print('sitecustomize roto'); sys.exit(3)")


@pytest.mark.docker
def test_docker_muere_antes_de_hola_es_error(imagen_bots):
    r = partida(BotDockerQueMuere(BOTS / "fiel", IMAGEN, None, LIMITES), bot_docker("fiel"))
    assert not r.falla_infraestructura, r.salidas
    assert (r.ganador, r.motivo) == ("negras", "error")


@pytest.mark.docker
def test_docker_imagen_inexistente_es_infraestructura(imagen_bots):
    malo = BotDocker(BOTS / "fiel", "torneo-no-existe:nunca", None, LIMITES)
    r = partida(malo, bot_docker("fiel"))
    assert r.falla_infraestructura and r.ganador == ""
    assert _contenedores(malo.nombre) == ""


@pytest.mark.docker
def test_docker_reloj_incluye_la_pausa(imagen_bots):
    # Reloj amplio: con 1 CPU, el hilo ocupado frena al bot (50 ms por jugada + pausas).
    r = partida(
        bot_docker("sigue_pensando"),
        bot_docker("tranquilo"),
        limites=replace(LIMITES, reloj_s=20.0),
    )
    assert r.motivo in {"puntos", "sin_jugadas"}, r.salidas
    mias = [j for j in r.jugadas if j["color"] == "blancas"][1:]
    velocidad = sum(j["info"]["dentro"] for j in mias) / sum(j["info"]["duracion"] for j in mias)
    trabajo_fuera = sum(j["info"]["fuera"] for j in mias) / velocidad
    cobrado_fuera = sum(j["tiempo"] - j["info"]["duracion"] for j in mias)
    # Lo que el hilo trabajó tras responder (hasta que terminó la pausa) se cobró.
    gratis = trabajo_fuera - cobrado_fuera
    assert gratis < 0.004 * len(mias), (gratis, trabajo_fuera, cobrado_fuera, len(mias))
    rival = [j["tiempo"] for j in r.jugadas if j["color"] == "negras"][1:]
    assert sum(rival) / len(rival) < 0.03 + 0.05  # 30 ms de pensar + la pausa


@pytest.mark.docker
def test_docker_muere_durante_la_pausa_nunca_es_infraestructura(imagen_bots):
    # Un hilo hace os._exit entre 5 y 12 ms después de responder: cae durante
    # `docker pause`. Siempre es culpa del bot, nunca falla de infraestructura.
    resultados = []
    for semilla in range(30):
        r = partida(bot_docker("muere_tras_responder"), bot_docker("fiel"), semilla=semilla)
        assert not r.falla_infraestructura, (semilla, r.salidas)
        resultados.append((r.ganador, r.motivo))
    # Lo normal es («negras», «error»). En un núcleo compartido muy cargado (medido:
    # otro proceso al 82 % en el mismo núcleo) un bot puede pasarse de los 5 s de
    # `preparar` aun con la caché caliente: es tiempo, no infraestructura, y se tolera.
    assert set(resultados) <= {("negras", "error"), ("negras", "preparar"), ("blancas", "preparar")}
    assert resultados.count(("negras", "error")) >= 20, resultados


class BotDockerAtorado(BotDocker):
    """`docker run` que nunca llega a crear el contenedor (cliente atorado)."""

    def _comando(self):
        return ["sleep", "30"]


@pytest.mark.docker
def test_docker_contenedor_nunca_creado_es_infraestructura(imagen_bots, monkeypatch):
    from arbitro import partida as modulo_partida

    monkeypatch.setattr(modulo_partida, "ARRANQUE_S", 1.0)
    r = partida(BotDockerAtorado(BOTS / "fiel", IMAGEN, None, LIMITES), bot_docker("fiel"))
    assert r.falla_infraestructura and r.ganador == ""


@pytest.mark.docker
def test_docker_usa_pyc_de_la_imagen_e_ignora_los_del_bot(imagen_bots, bot_con_pyc_viejo):
    r = partida(BotDocker(bot_con_pyc_viejo, IMAGEN, None, LIMITES), bot_docker("fiel"))
    assert r.jugadas[0]["info"] == {"valor": "src"}, r.salidas
    # Dentro del contenedor, los .pyc de la imagen vienen del árbol horneado /opt/pyc.
    salida = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--read-only",
            "--user",
            "65534:65534",
            "-e",
            "PYTHONPYCACHEPREFIX=/opt/pyc",
            IMAGEN,
            "python",
            "-c",
            "import sys, numpy, os; "
            "print(sys.pycache_prefix, os.path.exists(numpy.__spec__.cached))",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert salida == ["/opt/pyc", "True"]


@pytest.mark.docker
def test_docker_motor_caliente_antes_del_primer_turno(imagen_bots):
    # El runner calienta NUESTRO motor antes del reloj de `preparar`: un bot que usa
    # el motor por primera vez en su turno no paga la carga de los kernels de numba.
    r = partida(bot_docker("sin_preparar"), bot_docker("sin_preparar"))
    assert r.motivo in {"puntos", "sin_jugadas"}, r.salidas
    primeras = [j["tiempo"] for j in r.jugadas[:2]]
    assert max(primeras) < 0.3, primeras
