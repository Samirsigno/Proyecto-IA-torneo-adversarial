"""Docker para el CLI: imágenes de los equipos, caché de numba y limpieza de contenedores.

- La imagen base de los bots (`torneo-bot-base:local`) la deja lista el script `./torneo`
  (la construye en tu máquina; nunca se descarga de un registro).
- `torneo-bot:<equipo>`: si el equipo no instala nada (sin requirements.txt o solo con
  comentarios) es la misma imagen base con otro nombre; si instala algo, se construye con
  `sistema/Dockerfile.equipo` y se reconstruye solo cuando cambian su requirements.txt,
  el Dockerfile o la imagen base (etiqueta `torneo.hash`).
- Caché de numba de la máquina (volumen `torneo_numba_<arquitectura>`): se llena SOLO con
  nuestro código (el motor, en una partida random contra montecarlo hecha con el motor),
  nunca con código de alumnos.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import tarfile
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import config
from arbitro.procesos import ETIQUETA_DUENO, arquitectura, dueno
from cli import ErrorCLI, ErrorEquipo
from validador.requirements import auditar_archivo

IMAGEN_BOTS = "torneo-bot-base:local"
DOCKERFILE_EQUIPO = config.SISTEMA / "Dockerfile.equipo"
CONSTRAINTS = config.SISTEMA / "constraints.txt"
EDAD_HUERFANO = timedelta(minutes=10)  # sin dueño identificable: ninguna partida dura tanto
EDAD_CREADO = timedelta(seconds=60)  # un contenedor recién creado arranca en segundos
PREFIJOS = ("torneo-bot-", "torneo-calentar-")
_PASO_DOCKER = re.compile(r"\s*(Step \d+/\d+ :|--->)")  # ruido del builder
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")  # colores de pip en el log del build

# Partida random (blancas) contra montecarlo (negras) usando solo el motor: compila
# todos los kernels de numba que usan el árbitro, el runner y los bots de ejemplo.
CALENTAR = """
import random
from motor import Estado, simular_al_azar
rng = random.Random(0)
e = Estado.desde_dict(Estado.inicial().a_dict())
while e.ganador() is None:
    js = e.jugadas()
    if e.turno == "blancas":
        j = rng.choice(js)
    else:
        j = max(js, key=lambda j: sum(p * simular_al_azar(h, 2, rng.randrange(99), para="negras")
                                      for p, h in e.siguiente(j)))
    e.piezas(e.turno); e.clave; e.dibujar()
    if e.es_ataque(j):
        e = e.aplicar(j, gana_ataque=rng.random() < e.prob_ataque(j))
    else:
        e = e.aplicar(j)
print("caché de numba lista")
"""


def imagen_equipo(nombre: str) -> str:
    return f"torneo-bot:{nombre}"


def cliente():
    """Cliente del SDK de Docker, o un error claro si Docker no responde."""
    try:
        import docker

        c = docker.from_env()
        c.ping()
    except Exception as e:
        if isinstance(e, PermissionError) or "ermission denied" in str(e):
            raise ErrorCLI(
                "No tengo permiso para usar el socket de Docker. En Linux agrega tu usuario al "
                "grupo docker (sudo usermod -aG docker $USER), cierra sesión y vuelve a entrar. "
                "En Mac, revisa que Docker Desktop (o colima) esté corriendo."
            ) from None
        raise ErrorCLI(
            "No pude hablar con Docker. Revisa que Docker esté abierto y corriendo "
            f"(«docker info» debe funcionar). Detalle: {e}"
        ) from None
    return c


def imagen_base(c):
    import docker

    try:
        return c.images.get(IMAGEN_BOTS)
    except docker.errors.ImageNotFound:
        raise ErrorCLI(
            f"Falta la imagen {IMAGEN_BOTS}. Usa el script ./torneo (la construye solo en "
            "tu máquina) o corre ./torneo construir."
        ) from None


# --- Limpieza ------------------------------------------------------------------------------
def _fecha(texto: str) -> datetime:
    return datetime.strptime(texto[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC)


def _proceso_vivo(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # existe, pero es de otro usuario
        return True
    return True


def _huerfano(c, etiqueta: str | None, edad: timedelta) -> bool:
    """True si el proceso que lanzó el contenedor (etiqueta `torneo.dueno`) ya no existe.

    Así una partida larga de otra terminal (p. ej. contra `humano`) nunca se borra.
    """
    import docker

    try:
        host, pid, lugar = (etiqueta or "").rsplit(":", 2)
        pid_n = int(pid)
    except ValueError:
        return edad > EDAD_HUERFANO  # sin etiqueta (versión vieja del sistema)
    yo_host, _, _ = dueno().rsplit(":", 2)
    if host == yo_host:
        return not _proceso_vivo(pid_n)
    if lugar == "c":  # lo lanzó otro contenedor del CLI: ¿sigue corriendo?
        try:
            return c.containers.get(host).status != "running"
        except docker.errors.NotFound:
            return True
        except docker.errors.APIError:
            return False
    return edad > EDAD_HUERFANO  # proceso de otra máquina/espacio: no se puede revisar


def limpiar_contenedores(c) -> int:
    """Borra contenedores del torneo que quedaron de corridas interrumpidas (p. ej. Ctrl+C).

    Bots (`torneo-bot-*`) y calentadores (`torneo-calentar-*`). Borra los que ya terminaron,
    los recién creados que nunca arrancaron (más de 1 minuto) y los huérfanos reales: los
    que siguen vivos o en pausa pero cuyo proceso dueño ya no existe. Nunca toca los de otra
    terminal que siga jugando, por larga que sea la partida.
    """
    ahora = datetime.now(UTC)
    borrados = 0
    for contenedor in c.containers.list(all=True, filters={"name": "torneo-"}):
        if not contenedor.name.startswith(PREFIJOS):
            continue
        estado = contenedor.attrs.get("State", {}).get("Status")
        edad = ahora - _fecha(contenedor.attrs.get("Created", ""))
        etiqueta = (contenedor.attrs.get("Config", {}).get("Labels") or {}).get(ETIQUETA_DUENO)
        if (
            estado in ("exited", "dead")
            or (estado == "created" and edad > EDAD_CREADO)
            or (estado in ("running", "paused", "restarting") and _huerfano(c, etiqueta, edad))
        ):
            try:
                contenedor.remove(force=True)
                borrados += 1
            except Exception:  # otro proceso lo borró primero
                pass
    return borrados


# --- Imágenes de equipos ---------------------------------------------------------------------
def _paquetes(carpeta: Path) -> bytes | None:
    """Bytes de requirements.txt si instala algo; None si no hay nada que instalar."""
    archivo = carpeta / "requirements.txt"
    if not archivo.is_file():
        return None
    datos = archivo.read_bytes()
    errores, limpias = auditar_archivo(datos)
    if errores:
        raise ErrorEquipo(
            f"El requirements.txt de {carpeta.name} tiene problemas:\n"
            + "\n".join(f"  - {e}" for e in errores)
        )
    return datos if limpias else None


def _contexto(nombre: str, requirements: bytes) -> io.BytesIO:
    """Contexto mínimo del build: solo lo que copia Dockerfile.equipo (rápido)."""
    archivos = {
        "sistema/Dockerfile.equipo": DOCKERFILE_EQUIPO.read_bytes(),
        "sistema/constraints.txt": CONSTRAINTS.read_bytes(),
        f"estudiantes/{nombre}/requirements.txt": requirements,
    }
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for ruta, datos in archivos.items():
            info = tarfile.TarInfo(ruta)
            info.size = len(datos)
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(datos))
    buffer.seek(0)
    return buffer


def asegurar_imagen_equipo(
    c, nombre: str, carpeta: Path, avisar: Callable[[str], None] = print
) -> str:
    """Deja lista `torneo-bot:<nombre>` y regresa su nombre."""
    import docker

    base = imagen_base(c)
    etiqueta = imagen_equipo(nombre)
    try:
        actual = c.images.get(etiqueta)
    except docker.errors.ImageNotFound:
        actual = None
    requirements = _paquetes(carpeta)
    if requirements is None:
        if actual is None or actual.id != base.id:
            base.tag("torneo-bot", nombre)
        return etiqueta

    huella = hashlib.sha256()
    for parte in (DOCKERFILE_EQUIPO.read_bytes(), CONSTRAINTS.read_bytes(), requirements):
        huella.update(hashlib.sha256(parte).digest())
    huella.update(base.id.encode())
    if actual is not None and actual.labels.get("torneo.hash") == huella.hexdigest():
        return etiqueta
    if os.environ.get("TORNEO_IMAGEN_DIGEST"):
        raise ErrorCLI(
            f"Falta la imagen {etiqueta} (o no corresponde a su requirements.txt). En la liga "
            "oficial no se construye nada: debió construirse en el job «imagenes». "
            "Ningún equipo pierde en silencio: vuelve a lanzar la liga."
        )

    avisar(
        f"Construyendo la imagen de {nombre} (instala su requirements.txt; puede tardar "
        "unos minutos y solo se repite si cambia ese archivo)..."
    )
    log: list[str] = []
    for trozo in c.api.build(
        fileobj=_contexto(nombre, requirements),
        custom_context=True,
        dockerfile="sistema/Dockerfile.equipo",
        tag=etiqueta,
        buildargs={"EQUIPO": nombre, "BASE": IMAGEN_BOTS},
        labels={"torneo.hash": huella.hexdigest()},
        rm=True,
        forcerm=True,
        decode=True,
    ):
        if "stream" in trozo:
            log += _ANSI.sub("", trozo["stream"]).splitlines()
        if "error" in trozo:
            utiles = [x for x in log if x.strip() and not _PASO_DOCKER.match(x)]
            cola = "\n".join(f"  | {linea}" for linea in utiles[-15:])
            motivo = trozo["error"].strip()
            if motivo.startswith("The command"):  # el comando completo no le dice nada
                motivo = "falló la instalación de su requirements.txt"
            raise ErrorEquipo(
                f"No se pudo construir la imagen de {nombre}: {motivo}.\n{cola}\n"
                "Revisa su requirements.txt (solo «paquete==versión» que exista para Linux, "
                "sin librerías prohibidas)."
            )
    instalado = next((linea for linea in log if linea.startswith("requirements.txt de")), "")
    avisar(f"Imagen de {nombre} lista. {instalado.strip()}".rstrip())
    return etiqueta


# --- Caché de numba --------------------------------------------------------------------------
def _volumen(c, nombre: str):
    import docker

    try:
        return c.volumes.get(nombre)
    except docker.errors.NotFound:
        return c.volumes.create(nombre)


def _marca(carpeta_cache: Path) -> Path:
    return carpeta_cache / f"numba_{arquitectura()}.json"


def cache_al_dia(c, carpeta_cache: Path) -> bool:
    """True si el volumen de caché se llenó con la imagen base actual."""
    import docker

    try:
        datos = json.loads(_marca(carpeta_cache).read_text(encoding="utf-8"))
        volumen = c.volumes.get(f"torneo_numba_{arquitectura()}")
    except (OSError, ValueError, docker.errors.NotFound):
        return False
    return datos == {"imagen": imagen_base(c).id, "volumen": volumen.attrs.get("CreatedAt")}


def calentar(c, carpeta_cache: Path, avisar: Callable[[str], None] = print) -> None:
    """Llena la caché de numba de esta máquina con una partida hecha solo con el motor."""
    nombre = f"torneo_numba_{arquitectura()}"
    base = imagen_base(c)
    volumen = _volumen(c, nombre)
    avisar(
        "Preparando la caché de numba de esta máquina (solo la primera vez; tarda "
        "alrededor de un minuto)..."
    )
    try:
        c.containers.run(
            IMAGEN_BOTS,
            ["python", "-c", CALENTAR],
            name=f"torneo-calentar-{uuid.uuid4().hex[:12]}",
            labels={ETIQUETA_DUENO: dueno()},
            remove=True,
            network_mode="none",
            user="0",
            volumes={nombre: {"bind": "/opt/numba_listo", "mode": "rw"}},
            environment={"NUMBA_CACHE_DIR": "/opt/numba_listo"},
        )
    except Exception as e:
        raise ErrorCLI(f"No se pudo preparar la caché de numba: {e}") from None
    carpeta_cache.mkdir(parents=True, exist_ok=True)
    _marca(carpeta_cache).write_text(
        json.dumps({"imagen": base.id, "volumen": volumen.attrs.get("CreatedAt")}),
        encoding="utf-8",
    )
    avisar("Caché de numba lista.")
