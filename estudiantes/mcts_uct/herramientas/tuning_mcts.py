"""Búsqueda de K_EXPLORACION (c = √(2k)) de mcts_uct contra el montecarlo original.

    python3 estudiantes/mcts_uct/herramientas/tuning_mcts.py              # todo (≈ 75 min)
    python3 estudiantes/mcts_uct/herramientas/tuning_mcts.py --partidas 10

Para cada k de 1.0 a 6.0 (cada 0.5) juega `--partidas` partidas contra `montecarlo`, mitad con
cada color, con los límites reales de la liga (Docker, 1 núcleo fijo por bot, 1024 MB, reloj de
30 s). Corre `--simultaneas` partidas a la vez, como `./torneo liga`.

- Justo entre valores de k: todos juegan con los mismos dados (juego j con blancas y negras) y
  las partidas se intercalan por k (si se corta, todos los k llevan casi lo mismo).
- El bot de cada k es una copia de esta carpeta en la carpeta de salida con solo la línea
  `K_EXPLORACION = ...` cambiada: el contenedor del bot es de solo lectura y no recibe
  variables de entorno, así que no hay otra forma de pasarle k. El original no se toca.
- Salida (en resultados/, que git ignora): `partidas.csv` (una fila por partida, se escribe al
  terminar cada una), `resumen.csv` (win rate por k) y las repeticiones `.json`.
- Si se interrumpe (Ctrl+C), vuelve a correrlo con la misma `--salida`: se salta lo ya jugado.

Desde WSL se relanza solo dentro del contenedor del torneo (el mismo que usa ./torneo).
"""

import argparse
import csv
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from queue import Queue
from typing import NamedTuple

EQUIPO = Path(__file__).resolve().parent.parent
RAIZ = EQUIPO.parent.parent
RIVAL = "montecarlo"
SEMILLA = 2026
INTENTOS_MAX = 3  # una partida con falla de infraestructura (Docker) se repite

CAMPOS = (
    "k", "c", "juego", "color_uct", "ganador", "gano_uct", "motivo", "puntos_uct",
    "puntos_rival", "jugadas", "jugadas_uct", "reloj_uct_s", "reloj_rival_s",
    "t_turno_prom_uct_s", "t_turno_prom_rival_s", "nodos_prom_uct", "prof_prom_uct",
    "duracion_s", "intentos", "repeticion",
)  # fmt: skip


class Tarea(NamedTuple):
    k: float
    juego: int  # juego de dados (cada uno se juega una vez con cada color)
    color_uct: str


# --- Partes puras ------------------------------------------------------------------------------
def valores_k(inicio: float, fin: float, paso: float) -> list[float]:
    n = round((fin - inicio) / paso)
    return [round(inicio + i * paso, 6) for i in range(n + 1)]


def constante_c(k: float) -> float:
    return math.sqrt(2 * k)


def copiar_bot(origen: Path, destino: Path, k: float) -> Path:
    """Copia el bot (sin herramientas/) a `destino` con K_EXPLORACION = k."""
    codigo = (origen / "strategy.py").read_text(encoding="utf-8")
    nuevo, cambios = re.subn(
        r"^K_EXPLORACION = [^#\n]*", f"K_EXPLORACION = {k!r}  ", codigo, flags=re.M
    )
    if cambios != 1:
        raise ValueError(f"{origen / 'strategy.py'}: se esperaba 1 línea K_EXPLORACION = ...")
    if destino.exists():
        shutil.rmtree(destino)
    shutil.copytree(
        origen, destino, ignore=shutil.ignore_patterns("herramientas", "__pycache__")
    )
    (destino / "strategy.py").write_text(nuevo, encoding="utf-8")
    return destino


def tareas(valores: list[float], partidas_por_k: int) -> list[Tarea]:
    """Juego j con blancas y con negras para cada k, intercalando los k."""
    if partidas_por_k % 2:
        raise ValueError("partidas_por_k debe ser par (mitad con cada color)")
    return [
        Tarea(k, juego, color)
        for juego in range(partidas_por_k // 2)
        for color in ("blancas", "negras")
        for k in valores
    ]


def _promedio(valores: list[float]) -> float:
    return sum(valores) / len(valores) if valores else 0.0


def fila(tarea: Tarea, reg: dict, duracion_s: float, intentos: int, repeticion: str = "") -> dict:
    """Una fila del CSV a partir del registro de la partida (`registro.a_json`)."""
    uct, rival = tarea.color_uct, ("negras" if tarea.color_uct == "blancas" else "blancas")
    propias = [j for j in reg["jugadas"] if j["color"] == uct]
    ajenas = [j for j in reg["jugadas"] if j["color"] == rival]
    infos = [j["info"] for j in propias if j.get("info")]
    return {
        "k": tarea.k,
        "c": constante_c(tarea.k),
        "juego": tarea.juego,
        "color_uct": uct,
        "ganador": reg["ganador"],
        "gano_uct": int(reg["ganador"] == uct),
        "motivo": reg["motivo"],
        "puntos_uct": reg["puntos"][uct],
        "puntos_rival": reg["puntos"][rival],
        "jugadas": len(reg["jugadas"]),
        "jugadas_uct": len(propias),
        "reloj_uct_s": reg["reloj_usado"].get(uct, 0.0),
        "reloj_rival_s": reg["reloj_usado"].get(rival, 0.0),
        "t_turno_prom_uct_s": _promedio([j["tiempo"] for j in propias]),
        "t_turno_prom_rival_s": _promedio([j["tiempo"] for j in ajenas]),
        "nodos_prom_uct": _promedio([i["nodos"] for i in infos if "nodos" in i]),
        "prof_prom_uct": _promedio([i["prof"] for i in infos if "prof" in i]),
        "duracion_s": round(duracion_s, 2),
        "intentos": intentos,
        "repeticion": repeticion,
    }


def hechas(ruta: Path) -> set[Tarea]:
    """Partidas ya jugadas (válidas) en un `partidas.csv` anterior."""
    if not ruta.exists():
        return set()
    with ruta.open(newline="", encoding="utf-8") as archivo:
        return {
            Tarea(float(f["k"]), int(f["juego"]), f["color_uct"])
            for f in csv.DictReader(archivo)
            if f["gano_uct"] != ""
        }


def barra(hechas_n: int, total: int, transcurrido_s: float, ancho: int = 30) -> str:
    llenas = ancho * hechas_n // total if total else ancho
    if hechas_n:
        eta = str(timedelta(seconds=int(transcurrido_s / hechas_n * (total - hechas_n))))
    else:
        eta = "--:--:--"
    porcentaje = 100 * hechas_n / total if total else 100
    return (
        f"[{'#' * llenas}{'.' * (ancho - llenas)}] {hechas_n}/{total} {porcentaje:.0f}% · "
        f"{timedelta(seconds=int(transcurrido_s))} · ETA {eta}"
    )


def resumen(filas: list[dict]) -> list[dict]:
    """Win rate de UCT por k, con su error estándar √(p(1−p)/n)."""
    por_k: dict[float, list[int]] = {}
    for f in filas:
        if f["gano_uct"] != "":
            por_k.setdefault(float(f["k"]), []).append(int(f["gano_uct"]))
    salida = []
    for k in sorted(por_k):
        n, g = len(por_k[k]), sum(por_k[k])
        p = g / n
        salida.append(
            {"k": k, "c": constante_c(k), "partidas": n, "ganadas": g, "win_rate": p,
             "error_estandar": math.sqrt(p * (1 - p) / n)}
        )  # fmt: skip
    return salida


# --- Partidas de verdad (dentro del contenedor del torneo) ------------------------------------
def _jugar(tarea: Tarea, bots: dict[float, Path], rival: Path, ranura, salida: Path) -> dict:
    from arbitro import registro
    from arbitro.azar import Dados, semilla_bots
    from arbitro.partida import jugar_partida
    from arbitro.procesos import BotDocker
    from cli.imagenes import imagen_equipo
    from config import cargar_limites

    publicos = cargar_limites()
    nombre_uct = f"mcts_uct_k{tarea.k}"
    if tarea.color_uct == "blancas":
        nombres = (nombre_uct, RIVAL)
        carpetas = ((bots[tarea.k], "mcts_uct"), (rival, RIVAL))
    else:
        nombres = (RIVAL, nombre_uct)
        carpetas = ((rival, RIVAL), (bots[tarea.k], "mcts_uct"))
    inicio = time.monotonic()
    for intento in range(1, INTENTOS_MAX + 1):
        blancas, negras = (
            BotDocker(carpeta, imagen_equipo(equipo), nucleo, publicos)
            for (carpeta, equipo), nucleo in zip(carpetas, ranura, strict=True)
        )
        r = jugar_partida(
            blancas, negras, Dados(SEMILLA, 0, tarea.juego), publicos, publicos.efectivos(),
            semilla_bots(SEMILLA, 0, tarea.juego),
        )  # fmt: skip
        if not r.falla_infraestructura:
            break
    meta = {"blancas": nombres[0], "negras": nombres[1], "pareja": 0, "juego": tarea.juego,
            "semilla_maestra": SEMILLA}  # fmt: skip
    reg = registro.a_json(r, meta)
    if r.falla_infraestructura:
        f = dict.fromkeys(CAMPOS, "")
        f.update(k=tarea.k, c=constante_c(tarea.k), juego=tarea.juego, color_uct=tarea.color_uct,
                 motivo="infraestructura", intentos=INTENTOS_MAX)  # fmt: skip
        return f
    nombre = f"k{tarea.k}_j{tarea.juego:02d}_{tarea.color_uct}.json"
    (salida / "partidas").mkdir(exist_ok=True)
    (salida / "partidas" / nombre).write_text(json.dumps(reg, ensure_ascii=False))
    return fila(tarea, reg, time.monotonic() - inicio, intento, f"partidas/{nombre}")


def experimento(salida: Path, valores: list[float], partidas_por_k: int, simultaneas: int) -> None:
    from cli.comun import Entorno
    from liga.ejecutar import nucleos_disponibles, ranuras

    salida.mkdir(parents=True, exist_ok=True)
    rival = RAIZ / "estudiantes" / RIVAL
    Entorno(sin_docker=False).preparar({"mcts_uct": EQUIPO, RIVAL: rival})  # imágenes y numba
    bots = {k: copiar_bot(EQUIPO, salida / "bots" / f"mcts_uct_k{k}", k) for k in valores}

    ruta_csv = salida / "partidas.csv"
    ya = hechas(ruta_csv)
    faltan = [t for t in tareas(valores, partidas_por_k) if t not in ya]
    total = len(faltan)
    libres: Queue = Queue()
    for r in ranuras(nucleos_disponibles(), simultaneas):
        libres.put(r)
    print(f"k = {valores[0]}…{valores[-1]} · {partidas_por_k} partidas por k contra {RIVAL} · "
          f"{libres.qsize()} a la vez · reloj real de la liga")  # fmt: skip
    print(f"Salida: {salida}  ({len(ya)} partidas ya hechas, faltan {total})")
    if not faltan:
        return

    candado = threading.Lock()
    nuevo = not ruta_csv.exists()
    archivo = ruta_csv.open("a", newline="", encoding="utf-8")
    escritor = csv.DictWriter(archivo, CAMPOS)
    if nuevo:
        escritor.writeheader()
    ganadas = jugadas = 0
    inicio = time.monotonic()

    def una(tarea: Tarea) -> dict:
        ranura = libres.get()
        try:
            return _jugar(tarea, bots, rival, ranura, salida)
        finally:
            libres.put(ranura)

    pool = ThreadPoolExecutor(max_workers=libres.qsize())
    try:
        futuros = [pool.submit(una, t) for t in faltan]
        print(barra(0, total, 0.0), end="", flush=True)
        for n, futuro in enumerate(as_completed(futuros), 1):
            f = futuro.result()
            with candado:
                escritor.writerow(f)
                archivo.flush()
            if f["gano_uct"] != "":
                jugadas += 1
                ganadas += f["gano_uct"]
            parcial = f" · UCT ganó {ganadas}/{jugadas}" if jugadas else ""
            print(f"\r{barra(n, total, time.monotonic() - inicio)}{parcial}  ", end="", flush=True)
        print()
    except KeyboardInterrupt:
        print("\nDetenido: se terminan las partidas en curso (lo jugado ya está en el CSV)...")
        pool.shutdown(wait=True, cancel_futures=True)
        raise
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
        archivo.close()
        _escribir_resumen(salida)


def _escribir_resumen(salida: Path) -> None:
    with (salida / "partidas.csv").open(newline="", encoding="utf-8") as archivo:
        filas = list(csv.DictReader(archivo))
    tabla = resumen(filas)
    with (salida / "resumen.csv").open("w", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(
            archivo, ["k", "c", "partidas", "ganadas", "win_rate", "error_estandar"]
        )
        escritor.writeheader()
        escritor.writerows(tabla)
    print("\n   k      c   partidas  win rate (± error estándar)")
    for x in tabla:
        print(f"{x['k']:4.1f}  {x['c']:5.3f}  {x['partidas']:5d}     "
              f"{x['win_rate']:6.1%} ± {x['error_estandar']:.1%}")  # fmt: skip
    print(f"Resumen: {salida / 'resumen.csv'}")


# --- Lanzador ---------------------------------------------------------------------------------
def _relanzar_en_docker() -> None:
    """Fuera del contenedor del torneo: corre este mismo script con `docker compose run`."""
    try:
        gid_docker = os.stat("/var/run/docker.sock").st_gid
    except OSError:
        gid_docker = 0
    env = {**os.environ, "TORNEO_RAIZ_HOST": str(RAIZ), "TORNEO_UID": str(os.getuid()),
           "TORNEO_GID": str(os.getgid()), "TORNEO_DOCKER_GID": str(gid_docker)}  # fmt: skip
    script = Path(__file__).resolve().relative_to(RAIZ)
    tty = [] if sys.stdin.isatty() and sys.stdout.isatty() else ["-T"]
    comando = ["docker", "compose", "--project-directory", str(RAIZ), "-f",
               str(RAIZ / "docker-compose.yml"), "run", "--rm", *tty, "torneo",
               "python", "-u", str(script), *sys.argv[1:]]  # fmt: skip
    sys.exit(subprocess.call(comando, env=env))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--partidas", type=int, default=30, help="partidas por k (par)")
    parser.add_argument("--simultaneas", type=int, default=5, help="partidas a la vez")
    parser.add_argument("--k-min", type=float, default=1.0)
    parser.add_argument("--k-max", type=float, default=6.0)
    parser.add_argument("--k-paso", type=float, default=0.5)
    parser.add_argument("--salida", type=Path, help="carpeta (por omisión, una nueva con fecha)")
    args = parser.parse_args()
    if args.partidas < 2 or args.partidas % 2:
        parser.error("--partidas debe ser par y ≥ 2")
    salida = args.salida or (
        RAIZ / "resultados" / "tuning_mcts" / datetime.now().strftime("%Y-%m-%d_%H-%M")
    )
    experimento(salida.resolve(), valores_k(args.k_min, args.k_max, args.k_paso),
                args.partidas, args.simultaneas)  # fmt: skip


if __name__ == "__main__":
    try:
        import arbitro  # noqa: F401  (solo existe dentro del contenedor del torneo)
    except ImportError:
        _relanzar_en_docker()
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
