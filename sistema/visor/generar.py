"""Genera visores HTML autocontenidos de partidas (registro v1) y un índice.

Las reglas se calculan aquí con el motor y se incrustan como JSON: el JavaScript
del visor solo dibuja, nunca reimplementa reglas.
"""

from __future__ import annotations

import html
import json
import math
import re
from pathlib import Path
from urllib.parse import quote

from motor import Estado, Jugada, nucleo
from motor.jugada import casilla_de_texto

PLANTILLA = Path(__file__).parent / "plantilla.html"
LIMITE_RELOJ_S = 30.0


def _json_seguro(datos: object) -> str:
    """JSON apto para incrustar en <script>: sin `</script`, `<!--` ni U+2028/2029."""
    return json.dumps(datos, ensure_ascii=True, allow_nan=False).replace("<", "\\u003c")


def _sin_no_finitos(x: object) -> object:
    """Cambia NaN e infinitos (que no existen en JSON) por None, en todo el registro."""
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, dict):
        return {k: _sin_no_finitos(v) for k, v in x.items()}
    if isinstance(x, list | tuple):
        return [_sin_no_finitos(v) for v in x]
    return x


def _rellenar(plantilla: str, valores: dict[str, str]) -> str:
    """Sustituye {{CLAVE}} en una sola pasada: lo que se inserta no se vuelve a interpretar."""
    return re.sub(r"\{\{(\w+)\}\}", lambda m: valores.get(m.group(1), m.group(0)), plantilla)


def _foto(estado: Estado) -> dict:
    """Lo que el visor necesita de una posición, ya calculado con el motor."""
    b = [casilla_de_texto(c) for c in estado.piezas("blancas")]
    n = [casilla_de_texto(c) for c in estado.piezas("negras")]
    # El apoyo lo calcula el propio motor (nucleo.apoyo), así nunca se desvía de las reglas.
    apoyo = {c: int(nucleo.apoyo(estado._tablero, c, 0)) for c in b}
    apoyo.update({c: int(nucleo.apoyo(estado._tablero, c, 1)) for c in n})
    legales = []
    for j in estado.jugadas():
        ataque = estado.es_ataque(j)
        legales.append([j.origen, j.destino, round(estado.prob_ataque(j), 4), 1 if ataque else 0])
    pts = estado.puntos
    return {
        "b": b,
        "n": n,
        "pts": [pts["blancas"], pts["negras"]],
        "turno": estado.turno,
        "apoyo": {str(c): v for c, v in apoyo.items()},
        "legales": legales,
    }


def _fotos(registro: dict) -> list[dict]:
    """Posición antes de cada jugada y la final: len(jugadas) + 1 fotos."""
    estado = Estado.inicial()
    fotos = [_foto(estado)]
    for j in registro["jugadas"]:
        combate = j["combate"]
        estado = estado.aplicar(
            Jugada.desde_texto(j["jugada"]), None if combate is None else combate["gano"]
        )
        fotos.append(_foto(estado))
    return fotos


def _nombre_archivo(registro: dict, numero: int | None = None) -> str:
    """Nombre de archivo seguro: los nombres de participantes no son de fiar.

    `numero` (orden de la partida en la corrida) lo hace único aunque dos partidas
    tengan la misma meta (p. ej. `jugar x x`: x contra x en los dos colores).
    """
    m = registro["meta"]
    crudo = f"{m['pareja']}_{m['juego']}_{m['blancas']}_vs_{m['negras']}"
    if numero is not None:
        crudo = f"{numero:03d}_{crudo}"
    return re.sub(r"[^A-Za-z0-9_.-]", "_", crudo).lstrip(".") + ".html"


def visor_partida(registro: dict, destino: Path, numero: int | None = None) -> Path:
    """Escribe el visor HTML de una partida en `destino` y regresa su ruta.

    Si `destino` es una carpeta (o no tiene sufijo .html), el archivo se llama
    `[<numero>_]<pareja>_<juego>_<blancas>_vs_<negras>.html` (saneado) en esa carpeta.
    """
    destino = Path(destino)
    if destino.suffix != ".html":
        destino.mkdir(parents=True, exist_ok=True)
        destino = destino / _nombre_archivo(registro, numero)
        if destino.resolve().parent != destino.parent.resolve():
            raise ValueError("El nombre de la partida sale de la carpeta de destino.")
    else:
        destino.parent.mkdir(parents=True, exist_ok=True)
    m = registro["meta"]
    registro = _sin_no_finitos(registro)
    datos = {"registro": registro, "fotos": _fotos(registro), "limite_reloj": LIMITE_RELOJ_S}
    titulo = f"{m['blancas']} vs {m['negras']}"
    pagina = _rellenar(
        PLANTILLA.read_text(encoding="utf-8"),
        {"TITULO": html.escape(titulo), "DATOS": _json_seguro(datos)},
    )
    destino.write_text(pagina, encoding="utf-8")
    return destino


def indice(registros: list[dict], destino: Path, tabla: list | None = None) -> Path:
    """Escribe `index.html` con una tabla de partidas y enlaces a cada visor.

    `destino` es la carpeta donde viven los visores (se crea si no existe).
    Genera también los visores que falten (numerados en el orden de `registros`). Si pasas
    `tabla` (FilaTabla de la liga), va arriba.
    """
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    filas = []
    for numero, r in enumerate(registros, 1):
        try:
            m = r["meta"]
            archivo = visor_partida(r, destino, numero).name
            pts = r["puntos"]
            filas.append(
                "<tr>"
                f"<td>{html.escape(str(m['pareja']))}</td><td>{html.escape(str(m['juego']))}</td>"
                f"<td>{html.escape(str(m['blancas']))}</td><td>{html.escape(str(m['negras']))}</td>"
                f"<td>{html.escape(str(r['ganador'] or '—'))}</td>"
                f"<td>{html.escape(str(r['motivo']))}</td>"
                f"<td>{pts.get('blancas', 0)} – {pts.get('negras', 0)}</td>"
                f"<td>{len(r['jugadas'])}</td>"
                f'<td><a href="{html.escape(quote(archivo), quote=True)}">Ver partida</a></td>'
                "</tr>"
            )
        except Exception as error:  # una partida mala no debe tumbar el índice
            filas.append(
                f'<tr><td colspan="9">No se pudo generar una partida: '
                f"{html.escape(type(error).__name__)}: {html.escape(str(error))}</td></tr>"
            )
    pagina = _rellenar(
        _INDICE,
        {"FILAS": "\n".join(filas), "N": str(len(registros)), "TABLA": _tabla_posiciones(tabla)},
    )
    ruta = destino / "index.html"
    ruta.write_text(pagina, encoding="utf-8")
    return ruta


def _tabla_posiciones(tabla: list | None) -> str:
    """Tabla de posiciones en HTML (vacía si no hay), con todo escapado."""
    if not tabla:
        return ""
    filas = "\n".join(
        "<tr>"
        f"<td>{f.posicion}</td><td>{html.escape(str(f.equipo))}</td><td>{f.puntos}</td>"
        f"<td>{f.partidas}</td><td>{f.sb:g}</td><td>{f.anotados}</td>"
        "</tr>"
        for f in tabla
    )
    return (
        '<h1>Tabla</h1>\n<div class="t"><table>\n<thead><tr><th>Lugar</th><th>Equipo</th>'
        "<th>Puntos</th><th>Partidas</th><th>SB</th><th>Anotados</th></tr></thead>\n"
        f"<tbody>\n{filas}\n</tbody></table></div>\n<br>"
    )


_INDICE = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Partidas</title>
<style>
:root{--bg:#f6f7f9;--fg:#1c2330;--mut:#667085;--card:#fff;--line:#dfe3ea;--acc:#2457d6}
@media (prefers-color-scheme:dark){:root{--bg:#12161d;--fg:#e6e9ef;--mut:#98a2b3;--card:#1b212b;
--line:#2d3542;--acc:#7aa2ff}}
body{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:15px/1.4 system-ui,sans-serif}
h1{font-size:1.3rem;margin:0 0 12px}
.t{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:10px}
table{border-collapse:collapse;width:100%}
th,td{padding:8px 12px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--mut);font-weight:600;font-size:.85rem}
tr:last-child td{border-bottom:0}a{color:var(--acc)}
</style></head><body>
{{TABLA}}
<h1>Partidas ({{N}})</h1>
<div class="t"><table>
<thead><tr><th>Pareja</th><th>Juego</th><th>Blancas</th><th>Negras</th><th>Ganó</th><th>Motivo</th><th>Puntos</th><th>Jugadas</th><th></th></tr></thead>
<tbody>
{{FILAS}}
</tbody></table></div>
</body></html>
"""
