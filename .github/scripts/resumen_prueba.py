"""Resumen (Markdown) de la prueba de un equipo, para el resumen del job de GitHub Actions.

Uso (desde la raíz del repo, con el Python del runner; solo biblioteca estándar):
    python3 .github/scripts/resumen_prueba.py --equipo mi_equipo --validacion ok \\
        --resultados resultados --memoria memoria.log >> "$GITHUB_STEP_SUMMARY"

Lee los registros `*.json` de las partidas en `resultados/` y el muestreo de memoria
(`memoria.sh`: líneas «imagen uso / límite» de `docker stats`).
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

BIEN, AVISO = "✅", "⚠️"
UMBRAL = 0.9  # avisar al pasar el 90 % de un límite

DERROTAS = {
    "puntos": "el rival llegó a 3 puntos",
    "sin_jugadas": "se quedó sin jugadas",
    "reloj": "se quedó sin reloj",
    "preparar": "preparar tardó demasiado (incluye importar strategy.py)",
    "memoria": "se pasó de memoria",
    "ilegal": "jugada ilegal",
    "error": "error del bot (excepción o se cerró)",
}
UNIDADES = {
    "b": 1 / 2**20,
    "kib": 1 / 1024,
    "mib": 1,
    "gib": 1024,
    "kb": 1e3 / 2**20,
    "mb": 1e6 / 2**20,
    "gb": 1e9 / 2**20,
}


def partidas_de(resultados: Path, equipo: str) -> list[dict]:
    """Registros de las partidas de `equipo` (ignora carpetas ocultas como `.cache`)."""
    regs = []
    if not resultados.is_dir():
        return regs
    for ruta in sorted(resultados.rglob("*.json")):
        if any(p.startswith(".") for p in ruta.relative_to(resultados).parts):
            continue
        try:
            reg = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        meta = reg.get("meta") if isinstance(reg, dict) else None
        if isinstance(meta, dict) and equipo in (meta.get("blancas"), meta.get("negras")):
            regs.append(reg)
    return regs


def contar_partidas(resultados: Path, equipo: str) -> int:
    """Partidas de `equipo` jugadas de verdad (con ganador; sin falla de infraestructura)."""
    return sum(r.get("ganador") in ("blancas", "negras") for r in partidas_de(resultados, equipo))


def memoria_pico_mb(log: Path, equipo: str) -> float | None:
    """Máximo uso de memoria (MB) visto en contenedores de la imagen del equipo."""
    pico = None
    try:
        lineas = log.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for linea in lineas:
        partes = linea.split()
        if len(partes) < 2 or partes[0] != f"torneo-bot:{equipo}":
            continue
        m = re.fullmatch(r"([\d.]+)([a-zA-Z]+)", partes[1])
        if not m or m.group(2).lower() not in UNIDADES:
            continue
        mb = float(m.group(1)) * UNIDADES[m.group(2).lower()]
        pico = mb if pico is None else max(pico, mb)
    return pico


def _fila(nombre: str, ok: bool, detalle: str) -> str:
    return f"| {nombre} | {BIEN if ok else AVISO} | {detalle} |"


def resumen(
    equipo: str,
    validacion_ok: bool,
    resultados: Path,
    memoria: Path,
    reloj_s: float,
    memoria_mb: float,
) -> str:
    regs = partidas_de(resultados, equipo)
    filas = [
        _fila(
            "Validación",
            validacion_ok,
            f"pasa `./torneo validar {equipo}`"
            if validacion_ok
            else "NO pasa: abre el paso «Validar» del log para ver qué arreglar",
        )
    ]
    derrotas = []
    rivales: dict[str, list[bool]] = {}
    reloj_max = 0.0
    no_carga = 0
    for reg in regs:
        meta = reg["meta"]
        color = "blancas" if meta.get("blancas") == equipo else "negras"
        rival = meta.get("negras") if color == "blancas" else meta.get("blancas")
        gano = reg.get("ganador") == color
        rivales.setdefault(str(rival), []).append(gano)
        reloj_max = max(reloj_max, float((reg.get("reloj_usado") or {}).get(color, 0.0)))
        if not gano:
            motivo = str(reg.get("motivo", ""))
            mias = [j for j in reg.get("jugadas", []) if j.get("color") == color]
            if motivo == "preparar" or (motivo == "error" and not mias):
                no_carga += 1
            derrotas.append(
                f"- Contra {rival} con {color}: {DERROTAS.get(motivo, motivo or 'sin dato')}"
            )

    if not regs:
        filas.append(_fila("Partidas", False, "No se jugaron partidas: revisa el log"))
    else:
        filas.append(
            _fila(
                "Carga",
                no_carga == 0,
                "carga bien (preparar a tiempo)"
                if no_carga == 0
                else f"no cargó en {no_carga} partidas: revisa `preparar` e imports",
            )
        )
        for rival, juegos in sorted(rivales.items()):
            ganadas = sum(juegos)
            # A random hay que ganarle siempre; a los demás, más de la mitad.
            ok = ganadas == len(juegos) if rival == "random" else ganadas * 2 > len(juegos)
            filas.append(_fila(f"Contra {rival}", ok, f"{ganadas}/{len(juegos)} ganadas"))
        filas.append(
            _fila(
                "Reloj máx",
                reloj_max <= UMBRAL * reloj_s,
                f"{reloj_max:.1f} s de {reloj_s:g} s por partida",
            )
        )
    pico = memoria_pico_mb(memoria, equipo)
    if pico is None:
        filas.append("| Memoria pico (informativa) | — | sin datos |")
    else:
        filas.append(
            _fila(
                "Memoria pico (informativa)",
                pico <= UMBRAL * memoria_mb,
                f"{pico:.0f} MB de {memoria_mb:g} MB",
            )
        )

    partes = [
        f"## Prueba de `{equipo}`",
        "",
        "| Revisión | | Detalle |",
        "|---|---|---|",
        *filas,
        "",
    ]
    if derrotas:
        partes += ["**Partidas perdidas:**", *derrotas, ""]
    partes.append(
        "Repeticiones: descarga el artifact **repeticiones** (abajo, en *Artifacts*), "
        "descomprímelo y abre `index.html` en tu navegador."
    )
    return "\n".join(partes) + "\n"


def leer_limites(ruta: Path) -> dict[str, float]:
    """Números de `limites.toml` («clave = número»; sin tomllib, por si el Python es viejo)."""
    texto = ruta.read_text(encoding="utf-8")
    return {
        m.group(1): float(m.group(2))
        for m in re.finditer(r"^\s*(\w+)\s*=\s*([\d.]+)", texto, re.MULTILINE)
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--equipo", required=True)
    p.add_argument("--validacion", choices=["ok", "falla"])
    p.add_argument("--contar", action="store_true", help="solo imprime cuántas partidas jugó")
    p.add_argument("--resultados", default="resultados")
    p.add_argument("--memoria", default="memoria.log")
    p.add_argument("--limites", default="sistema/limites.toml")
    args = p.parse_args()
    if args.contar:
        print(contar_partidas(Path(args.resultados), args.equipo))
        return
    if args.validacion is None:
        p.error("falta --validacion")
    limites = leer_limites(Path(args.limites))
    print(
        resumen(
            args.equipo,
            args.validacion == "ok",
            Path(args.resultados),
            Path(args.memoria),
            float(limites["reloj_s"]),
            float(limites["memoria_mb"]),
        )
    )


if __name__ == "__main__":
    main()
