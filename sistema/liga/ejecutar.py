"""Ejecuta la liga: juega las parejas, las guarda de forma atómica y permite reanudar.

Carpeta de salida:
- `estado_liga.json`: semilla maestra, participantes, hash del calendario COMPLETO,
  hashes de las entregas y límites (públicos y efectivos). Reanudar con otro estado es
  error (nunca se mezclan dos ligas). Todos los shards escriben el mismo, así que juntar
  sus carpetas no lo cambia y la liga completa se puede reanudar en la carpeta juntada.
- `estados_shard/<i>_de_<n>.json`: hash de la parte del calendario de cada shard.
- `parejas/<pareja>.json`: las partidas de una pareja, escritas JUNTAS (temporal +
  renombrar) y solo si ninguna tuvo falla de infraestructura. Reanudar salta estas.
- `incidentes/<pareja>.json`: fallas de infraestructura de la pareja. Si hubo falla, se
  descartan todas sus partidas y la pareja se repite completa con las mismas semillas,
  hasta 2 veces; si vuelve a fallar queda `excluida` (no entra a la tabla; decide el
  profesor). Al reanudar, una pareja excluida se vuelve a intentar.

Un archivo por pareja: las carpetas de varios shards se juntan sin choques.
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import tempfile
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from itertools import count
from pathlib import Path

from arbitro import registro
from arbitro.azar import Dados, semilla_bots
from arbitro.partida import jugar_partida
from arbitro.procesos import ProcesoBot
from config import Limites
from liga.calendario import PartidaProgramada

REPETICIONES_MAX = 2  # además del primer intento
NUCLEOS_LIBRES = 2
NUCLEOS_MINIMOS = 6  # con menos: sin núcleos fijos y una partida a la vez
VERSION_PAREJA = 1

CrearBot = Callable[[str, int | None], ProcesoBot]
Ranura = tuple[int | None, int | None]


# --- Núcleos -------------------------------------------------------------------------------
def nucleos_disponibles() -> list[int]:
    """Núcleos que puede usar este proceso."""
    try:
        return sorted(os.sched_getaffinity(0))
    except AttributeError:  # macOS
        return list(range(os.cpu_count() or 1))


def ranuras(nucleos: list[int], simultaneas: int) -> list[Ranura]:
    """Núcleos (blancas, negras) de cada partida simultánea.

    Con ≥ 6 núcleos: 2 fijos por partida, dejando libres los 2 primeros (sistema y
    árbitro). Con menos: una sola partida a la vez y sin núcleos fijos.
    """
    if len(nucleos) < NUCLEOS_MINIMOS:
        return [(None, None)]
    usables = nucleos[NUCLEOS_LIBRES:]
    n = max(1, min(simultaneas, len(usables) // 2))
    return [(usables[2 * i], usables[2 * i + 1]) for i in range(n)]


# --- Archivos ------------------------------------------------------------------------------
def _escribir_atomico(ruta: Path, datos: object) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, temporal = tempfile.mkstemp(dir=ruta.parent, prefix=f".{ruta.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as archivo:
            json.dump(datos, archivo, ensure_ascii=False)
            archivo.flush()
            os.fsync(archivo.fileno())
        os.chmod(temporal, 0o644)  # mkstemp lo crea solo para el dueño
        os.replace(temporal, ruta)
    except BaseException:
        Path(temporal).unlink(missing_ok=True)
        raise


def hash_calendario(calendario: list[PartidaProgramada]) -> str:
    texto = json.dumps([asdict(p) for p in calendario], sort_keys=True)
    return hashlib.sha256(texto.encode()).hexdigest()


def _revisar_estado(salida: Path, estado: dict, nombre: str = "estado_liga.json") -> None:
    ruta = salida / nombre
    if ruta.exists():
        previo = json.loads(ruta.read_text(encoding="utf-8"))
        if previo != estado:
            distinto = [c for c in estado if previo.get(c) != estado[c]]
            raise ValueError(
                f"{salida} ya tiene otra liga (cambió: {', '.join(distinto) or 'formato'}). "
                "Para reanudar usa la misma semilla, participantes y entregas; para una "
                "liga nueva usa otra carpeta."
            )
        return
    _escribir_atomico(ruta, estado)


def _leer_pareja(ruta: Path) -> list[dict]:
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    registros = datos["registros"]
    if datos.get("version") != VERSION_PAREJA or any(
        r["meta"]["pareja"] != datos["pareja"] or not r["ganador"] for r in registros
    ):
        raise ValueError(f"{ruta} está dañado o no es de esta versión; bórralo y reanuda.")
    return registros


def leer_parejas(salida: Path) -> list[dict]:
    """Todos los registros guardados en `salida/parejas/` (p. ej. tras juntar shards)."""
    rutas = sorted((salida / "parejas").glob("*.json"), key=lambda r: int(r.stem))
    return [r for ruta in rutas for r in _leer_pareja(ruta)]


def leer_incidentes(salida: Path) -> list[dict]:
    """Incidentes de `salida/incidentes/`, ordenados por pareja."""
    rutas = sorted((salida / "incidentes").glob("*.json"), key=lambda r: int(r.stem))
    return [json.loads(r.read_text(encoding="utf-8")) for r in rutas]


def revisar_resultados(
    calendario: list[PartidaProgramada],
    registros: list[dict],
    incidentes: list[dict],
    semilla_maestra: int,
) -> list[str]:
    """Problemas al contrastar lo guardado con el calendario completo (vacío = coherente).

    Cada partida del calendario debe estar exactamente una vez (mismos equipos, colores y
    semilla), salvo las de parejas excluidas, que no deben tener partidas. Nada ajeno.
    """
    programadas = {(p.pareja, p.juego, p.blancas): p for p in calendario}
    excluidas = {i["pareja"] for i in incidentes if i.get("excluida")}
    problemas: list[str] = []
    vistas: set[tuple] = set()
    for r in registros:
        m = r["meta"]
        clave = (m["pareja"], m["juego"], m["blancas"])
        p = programadas.get(clave)
        if p is None or p.negras != m["negras"] or m["semilla_maestra"] != semilla_maestra:
            problemas.append(
                f"partida ajena al calendario: pareja {m['pareja']}, juego {m['juego']}, "
                f"{m['blancas']} vs {m['negras']} (semilla {m['semilla_maestra']})"
            )
        elif clave in vistas:
            problemas.append(f"partida repetida: pareja {p.pareja}, juego {p.juego}, {p.blancas}")
        elif p.pareja in excluidas:
            problemas.append(f"la pareja {p.pareja} está excluida pero tiene partidas")
        vistas.add(clave)
    faltan = sorted(
        {p.pareja for c, p in programadas.items() if c not in vistas and p.pareja not in excluidas}
    )
    if faltan:
        problemas.append(
            f"faltan partidas de {len(faltan)} parejas ({', '.join(map(str, faltan[:20]))}"
            f"{'...' if len(faltan) > 20 else ''})"
        )
    return problemas


# --- Partidas ------------------------------------------------------------------------------
def _jugar_una(
    p: PartidaProgramada,
    crear_bot: CrearBot,
    ranura: Ranura,
    publicos: Limites,
    efectivos: Limites,
    semilla_maestra: int,
) -> tuple[dict | None, str]:
    """Registro v1 de la partida, o (None, detalle) si hubo falla de infraestructura."""
    blancas = None
    try:
        blancas = crear_bot(p.blancas, ranura[0])
        negras = crear_bot(p.negras, ranura[1])
    except Exception as e:  # p. ej. Docker no responde al crear el contenedor
        if blancas is not None:
            try:
                blancas.terminar()
            except Exception:  # ya hay falla; solo limpiamos
                pass
        return None, f"juego {p.juego}, {p.blancas} vs {p.negras}: {type(e).__name__}: {e}"
    r = jugar_partida(
        blancas,
        negras,
        Dados(semilla_maestra, p.pareja, p.juego),
        publicos,
        efectivos,
        semilla_bots(semilla_maestra, p.pareja, p.juego),
    )
    if r.falla_infraestructura or not r.ganador:
        nota = next(
            (
                linea
                for t in r.salidas.values()
                for linea in t.splitlines()
                if "Falla de infraestructura" in linea
            ),
            "falla de infraestructura",
        )
        return None, f"juego {p.juego}, {p.blancas} vs {p.negras}: {nota}"
    meta = {
        "blancas": p.blancas,
        "negras": p.negras,
        "pareja": p.pareja,
        "juego": p.juego,
        "semilla_maestra": semilla_maestra,
    }
    return registro.a_json(r, meta), ""


def _jugar_pareja(
    partidas: list[PartidaProgramada],
    crear_bot: CrearBot,
    ranura: Ranura,
    publicos: Limites,
    efectivos: Limites,
    semilla_maestra: int,
    salida: Path,
) -> list[dict]:
    pareja = partidas[0].pareja
    # Si una corrida anterior la excluyó, se conserva su historial de fallas.
    previo = salida / "incidentes" / f"{pareja}.json"
    fallas: list[str] = (
        json.loads(previo.read_text(encoding="utf-8"))["fallas"] if previo.exists() else []
    )
    for _ in range(1 + REPETICIONES_MAX):
        registros: list[dict] = []
        for p in partidas:  # en serie, en el orden del calendario
            reg, detalle = _jugar_una(p, crear_bot, ranura, publicos, efectivos, semilla_maestra)
            if reg is None:
                fallas.append(detalle)
                break
            registros.append(reg)
        else:
            if fallas:
                _anotar_incidente(salida, partidas, fallas, excluida=False)
            _escribir_atomico(
                salida / "parejas" / f"{pareja}.json",
                {"version": VERSION_PAREJA, "pareja": pareja, "registros": registros},
            )
            return registros
    _anotar_incidente(salida, partidas, fallas, excluida=True)
    return []


def _anotar_incidente(
    salida: Path, partidas: list[PartidaProgramada], fallas: list[str], excluida: bool
) -> None:
    p = partidas[0]
    _escribir_atomico(
        salida / "incidentes" / f"{p.pareja}.json",
        {
            "pareja": p.pareja,
            "equipos": sorted({p.blancas, p.negras}),
            "fallas": fallas,
            "excluida": excluida,
        },
    )


def ejecutar_liga(
    calendario: list[PartidaProgramada],
    crear_bot: CrearBot,
    publicos: Limites,
    efectivos: Limites,
    semilla_maestra: int,
    simultaneas: int,
    salida: Path,
    *,
    nucleos: int | None = None,
    hashes: dict[str, str] | None = None,
    avisar: Callable[[str], None] | None = None,
    completo: list[PartidaProgramada] | None = None,
    shard: tuple[int, int] | None = None,
) -> list[dict]:
    """Juega las parejas de `calendario` que falten en `salida` y regresa TODOS sus registros.

    `crear_bot(equipo, nucleo)` crea el ProcesoBot del equipo (BotDocker o BotLocal).
    `nucleos`: cuántos núcleos usar (por defecto, los de la máquina); `hashes`: sha256 de
    cada entrega, para que reanudar con otras entregas sea error. `avisar(texto)` recibe
    una línea de avance por pareja. Con shards: `completo` es el calendario de toda la
    liga y `shard` = (i, n) con i de 1 a n; `calendario` es solo la parte del shard.
    """
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    liga = completo if completo is not None else calendario
    _revisar_estado(
        salida,
        {
            "semilla_maestra": semilla_maestra,
            "participantes": sorted({e for p in liga for e in (p.blancas, p.negras)}),
            "calendario": hash_calendario(liga),
            "hashes": dict(sorted((hashes or {}).items())),
            "limites": {"publicos": asdict(publicos), "efectivos": asdict(efectivos)},
        },
    )
    if shard is not None:
        _revisar_estado(
            salida,
            {"shard": list(shard), "calendario": hash_calendario(calendario)},
            f"estados_shard/{shard[0]}_de_{shard[1]}.json",
        )

    por_pareja: dict[int, list[PartidaProgramada]] = {}
    for p in calendario:
        por_pareja.setdefault(p.pareja, []).append(p)
    hechas = {
        pareja: _leer_pareja(ruta)
        for pareja in por_pareja
        if (ruta := salida / "parejas" / f"{pareja}.json").exists()
    }
    for pareja, regs in hechas.items():
        if len(regs) != len(por_pareja[pareja]):
            raise ValueError(f"parejas/{pareja}.json no coincide con el calendario.")
    faltan = [pareja for pareja in sorted(por_pareja) if pareja not in hechas]

    lista = nucleos_disponibles() if nucleos is None else list(range(nucleos))
    libres: queue.Queue[Ranura] = queue.Queue()
    for ranura in ranuras(lista, simultaneas):
        libres.put(ranura)
    total = len(por_pareja)
    listas = count(len(hechas) + 1)  # parejas terminadas (las ya guardadas cuentan)
    avance = threading.Lock()

    detener = threading.Event()  # tras un error inesperado no se empiezan más parejas

    def jugar(pareja: int) -> list[dict] | None:
        ranura = libres.get()
        try:
            if detener.is_set():
                return None
            regs = _jugar_pareja(
                por_pareja[pareja],
                crear_bot,
                ranura,
                publicos,
                efectivos,
                semilla_maestra,
                salida,
            )
        except BaseException:
            detener.set()
            raise
        finally:
            libres.put(ranura)
        with avance:  # un hilo a la vez: el contador y su línea salen en orden
            n = next(listas)
            if avisar is not None:
                avisar(f"pareja {pareja} lista ({len(regs)} partidas válidas) · {n}/{total}")
        return regs

    with ThreadPoolExecutor(max_workers=libres.qsize()) as pool:
        futuros = {pareja: pool.submit(jugar, pareja) for pareja in faltan}
        try:
            for pareja, futuro in futuros.items():
                hechas[pareja] = futuro.result()
        except BaseException:
            detener.set()
            raise
    return [r for pareja in sorted(hechas) for r in hechas[pareja]]
