"""Calibración del juego y de los tiempos de la liga. Solo para el profesor.

Juega en este mismo proceso (sin Docker, sin árbitro), con el motor, los dados del árbitro
y los `strategy.py` de `estudiantes/`. Opcionalmente mide partidas reales con `./torneo`.

    taskset -c 0 python sistema/herramientas/calibrar.py --azar 2000 --mc 30 --reloj-mc 3 \\
        --mc-random 30 --frio --docker 2

Mediciones:
- `--azar N`: random vs random. Duración (jugadas totales), % de Blancas, ataques por partida.
- `--mc N` (reloj `--reloj-mc`): montecarlo vs montecarlo. % de Blancas, duración.
- `--mc-random N`: montecarlo vs random (con el mismo reloj reducido). % de montecarlo.
- `--frio`: segundos de compilación de numba en frío (Python nuevo, caché vacía).
- `--docker N`: N partidas montecarlo vs montecarlo con `./torneo jugar` (reloj real);
  tiempo de pared por partida, con arranque de contenedores y `preparar`.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

SISTEMA = Path(__file__).resolve().parents[1]
RAIZ = SISTEMA.parent
sys.path.insert(0, str(SISTEMA))

from arbitro.azar import Dados, semilla_bots, semilla_de_color  # noqa: E402
from arbitro.runner import Config  # noqa: E402
from motor import Estado, Jugada  # noqa: E402

COLORES = ("blancas", "negras")


@dataclass
class Resultado:
    ganador: str  # color
    jugadas: int
    ataques: int
    motivo: str  # "juego" o "reloj"
    reloj: dict[str, float]


def cargar_bot(equipo: str, instancia: int) -> ModuleType:
    """Carga `estudiantes/<equipo>/strategy.py` como un módulo nuevo (globals propias)."""
    ruta = RAIZ / "estudiantes" / equipo / "strategy.py"
    spec = importlib.util.spec_from_file_location(f"bot_{equipo}_{instancia}", ruta)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def partida(equipos: tuple[str, str], reloj_s: float, semilla: int, n: int) -> Resultado:
    """Una partida en proceso: `equipos` = (blancas, negras). Pierde quien agota su reloj."""
    bots = {c: cargar_bot(e, i) for i, (c, e) in enumerate(zip(COLORES, equipos, strict=True))}
    base = semilla_bots(semilla, 0, n)
    for color, bot in bots.items():
        carpeta = RAIZ / "estudiantes" / equipos[COLORES.index(color)] / "data"
        if hasattr(bot, "preparar"):
            bot.preparar(Config(color, semilla_de_color(base, color), carpeta, reloj_s))
    dados = Dados(semilla, 0, n)
    usado = dict.fromkeys(COLORES, 0.0)
    estado, jugadas, ataques = Estado.inicial(), 0, 0
    while (ganador := estado.ganador()) is None:
        color = estado.turno
        inicio = time.perf_counter()
        jugada = bots[color].jugar(estado, max(0.0, reloj_s - usado[color]))
        usado[color] += time.perf_counter() - inicio
        if usado[color] > reloj_s:
            otro = COLORES[1 - COLORES.index(color)]
            return Resultado(otro, jugadas, ataques, "reloj", usado)
        jugada = Jugada.desde_texto(str(jugada))
        if estado.es_ataque(jugada):
            ataques += 1
            gana = dados.tirar(color) < estado.prob_ataque(jugada)
            estado = estado.aplicar(jugada, gana_ataque=gana)
        else:
            estado = estado.aplicar(jugada)
        jugadas += 1
    return Resultado(ganador, jugadas, ataques, "juego", usado)


def serie(equipos: tuple[str, str], n: int, reloj_s: float, semilla: int) -> list[Resultado]:
    """n partidas alternando colores: en las impares `equipos` va invertido."""
    resultados = []
    for i in range(n):
        orden = equipos if i % 2 == 0 else equipos[::-1]
        resultados.append(partida(orden, reloj_s, semilla, i))
    return resultados


def resumen(titulo: str, rs: list[Resultado], equipos: tuple[str, str] | None = None) -> None:
    largos = [r.jugadas for r in rs]
    p = statistics.quantiles(largos, n=20) if len(largos) > 1 else largos * 19
    blancas = sum(r.ganador == "blancas" for r in rs) / len(rs)
    print(f"\n## {titulo} ({len(rs)} partidas)\n")
    print(
        f"- Jugadas totales: media {statistics.mean(largos):.1f}, mediana "
        f"{statistics.median(largos):g}, p5 {p[0]:g}, p95 {p[18]:g}, "
        f"mín {min(largos)}, máx {max(largos)}"
    )
    print(f"- Gana Blancas: {100 * blancas:.1f} %")
    print(
        f"- Ataques por partida: media {statistics.mean(r.ataques for r in rs):.1f} "
        f"({100 * sum(r.ataques for r in rs) / sum(largos):.1f} % de las jugadas)"
    )
    reloj = [r for r in rs if r.motivo == "reloj"]
    print(f"- Derrotas por reloj: {len(reloj)}")
    usado = [max(r.reloj.values()) for r in rs]
    print(f"- Reloj máximo usado por partida: media {statistics.mean(usado):.2f} s")
    if equipos:
        # En la partida i, equipos[0] juega con Blancas si i es par.
        gana_a = sum((r.ganador == "blancas") == (i % 2 == 0) for i, r in enumerate(rs))
        print(f"- Gana {equipos[0]}: {gana_a}/{len(rs)} ({100 * gana_a / len(rs):.1f} %)")


def compilacion_en_frio() -> float:
    """Segundos de un Python nuevo, con caché de numba vacía, hasta la primera simulación."""
    codigo = (
        "import time; t = time.perf_counter()\n"
        "from motor import Estado, simular_al_azar\n"
        "e = Estado.inicial(); e.jugadas(); simular_al_azar(e, 1, 0, para='blancas')\n"
        "print(time.perf_counter() - t)"
    )
    with tempfile.TemporaryDirectory() as cache:
        env = {**os.environ, "NUMBA_CACHE_DIR": cache, "PYTHONPATH": str(SISTEMA)}
        salida = subprocess.run(
            [sys.executable, "-c", codigo], env=env, check=True, capture_output=True, text=True
        ).stdout
    return float(salida.strip().splitlines()[-1])


def docker(n: int, a: str, b: str) -> None:
    """n partidas reales con `./torneo jugar a b`: tiempo de pared total y por partida."""
    inicio = time.perf_counter()
    proc = subprocess.run(
        [str(RAIZ / "torneo"), "jugar", a, b, "--partidas", str(n)],
        cwd=RAIZ,
        capture_output=True,
        text=True,
    )
    pared = time.perf_counter() - inicio
    print(f"\n## Docker: {a} vs {b}, reloj real ({n} partidas)\n")
    print("```text\n" + proc.stdout.strip() + "\n```")
    por_partida = pared / n
    print(f"- Pared total: {pared:.1f} s · por partida: {por_partida:.1f} s (rc {proc.returncode})")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--azar", type=int, default=0, help="partidas random vs random")
    p.add_argument("--mc", type=int, default=0, help="partidas montecarlo vs montecarlo")
    p.add_argument("--mc-random", type=int, default=0, help="partidas montecarlo vs random")
    p.add_argument("--reloj-mc", type=float, default=3.0, help="reloj por partida (s) en proceso")
    p.add_argument("--frio", action="store_true", help="medir compilación de numba en frío")
    p.add_argument("--docker", type=int, default=0, help="partidas reales con ./torneo")
    p.add_argument("--rival-docker", default="montecarlo", help="rival de montecarlo en Docker")
    p.add_argument("--semilla", type=int, default=2026)
    a = p.parse_args()

    print(f"# Calibración · semilla {a.semilla} · núcleos visibles {len(os.sched_getaffinity(0))}")
    if a.frio:
        print(f"\n## numba en frío\n\n- Primera simulación: {compilacion_en_frio():.1f} s")
    for n, equipos, reloj in (
        (a.azar, ("random", "random"), 30.0),
        (a.mc, ("montecarlo", "montecarlo"), a.reloj_mc),
        (a.mc_random, ("montecarlo", "random"), a.reloj_mc),
    ):
        if n:
            t = time.perf_counter()
            rs = serie(equipos, n, reloj, a.semilla)
            titulo = f"{equipos[0]} vs {equipos[1]}, reloj {reloj:g} s"
            resumen(titulo, rs, equipos if equipos[0] != equipos[1] else None)
            print(f"- Tiempo de cómputo: {time.perf_counter() - t:.1f} s")
    if a.docker:
        docker(a.docker, "montecarlo", a.rival_docker)
    return 0


if __name__ == "__main__":
    sys.exit(main())
