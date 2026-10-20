"""Publicación de la liga.

Escribe en `salida/`:
- `tabla.csv`: la tabla completa (público).
- `calificaciones.csv.age`: calificaciones con nombres y claves únicas, CIFRADO con la llave
  pública `age` del profesor. Nunca se escribe en claro: si falta la llave o el programa
  `age`, `publicar` se niega antes de escribir nada.
- `resumen.md`: para `$GITHUB_STEP_SUMMARY` (sin nombres ni claves únicas).
- `incidentes.md`: fallas de infraestructura por pareja.
- `sitio/`: `index.html`, una página por equipo (partidas y motivo de cada derrota),
  `partidas/` con el registro JSON y el visor de cada partida, SIN `info` ni `salidas`
  de ningún bot (eso solo queda en `parejas/`, que no es público). Se regenera completo
  en cada publicación (no quedan archivos viejos).

Todos los archivos se escriben de forma atómica (temporal + fsync + renombrar).

Los registros se leen de `salida/parejas/` (ya juntados los shards).
"""

from __future__ import annotations

import csv
import html
import io
import json
import os
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

import config
from config import es_reservado
from liga.ejecutar import leer_parejas
from liga.tabla import FilaTabla

LLAVE_PROFESOR = config.SISTEMA / "llave_profesor.age.pub"
COLORES = ("blancas", "negras")

# Motivo del resultado, visto desde quien perdió.
DERROTAS = {
    "puntos": "El rival llegó a 3 puntos",
    "sin_jugadas": "Se quedó sin jugadas",
    "reloj": "Se quedó sin reloj",
    "preparar": "preparar tardó demasiado",
    "memoria": "Se pasó de memoria",
    "ilegal": "Jugada ilegal",
    "error": "Error del bot (excepción o se cerró)",
}

Integrante = dict[str, str]


def leer_integrantes(carpeta: Path) -> list[Integrante]:
    """Integrantes (`nombre`, `clave_unica`) del `equipo.toml` de un equipo."""
    with (Path(carpeta) / "equipo.toml").open("rb") as archivo:
        datos = tomllib.load(archivo)
    return [
        {"nombre": str(i.get("nombre", "")), "clave_unica": str(i.get("clave_unica", ""))}
        for i in datos.get("integrantes", [])
    ]


# --- Calificaciones cifradas ---------------------------------------------------------------
def _revisar_cifrado(llave: Path) -> str:
    """Ruta del programa `age`. Error claro si falta la llave o el programa."""
    if not llave.is_file():
        raise FileNotFoundError(
            f"No existe la llave pública del profesor ({llave}). Sin ella no se escriben "
            "calificaciones (nunca se guardan en claro). Genérala con `age-keygen` y "
            "guarda la línea `age1...` en ese archivo."
        )
    programa = shutil.which("age")
    if programa is None:
        raise RuntimeError(
            "No encontré el programa `age` para cifrar las calificaciones. Instálalo "
            "(https://github.com/FiloSottile/age) y vuelve a publicar."
        )
    return programa


def _revisar_claves(calificaciones: dict[str, float], claves: dict[str, list[Integrante]]) -> None:
    """Cada equipo calificado necesita integrantes con clave única (si no, no se escribe)."""
    faltan = sorted(
        e
        for e in calificaciones
        if not claves.get(e) or any(not str(i.get("clave_unica", "")).strip() for i in claves[e])
    )
    if faltan:
        raise ValueError(
            "Faltan integrantes con clave única para: "
            f"{', '.join(faltan)}. Revisa su equipo.toml (o pásalos como no calificables); "
            "no se escriben calificaciones incompletas."
        )


def _csv_calificaciones(
    tabla: list[FilaTabla], calificaciones: dict[str, float], claves: dict[str, list[Integrante]]
) -> bytes:
    filas = {f.equipo: f for f in tabla}
    texto = io.StringIO()
    escritor = csv.writer(texto, lineterminator="\n")
    escritor.writerow(["equipo", "posicion", "puntos", "calificacion", "nombre", "clave_unica"])
    for equipo in sorted(calificaciones, key=lambda e: filas[e].posicion):
        f = filas[equipo]
        for i in claves[equipo]:
            escritor.writerow(
                [
                    equipo,
                    f.posicion,
                    f.puntos,
                    f"{calificaciones[equipo]:g}",
                    i["nombre"],
                    i["clave_unica"],
                ]
            )
    return texto.getvalue().encode()


def _escribir_cifrado(programa: str, llave: Path, claro: bytes, destino: Path) -> None:
    """Cifra en memoria (el texto claro nunca toca el disco) y escribe de forma atómica."""
    r = subprocess.run(
        [programa, "--encrypt", "-R", str(llave)], input=claro, capture_output=True, timeout=60
    )
    if r.returncode != 0 or not r.stdout.startswith(b"age-encryption.org/v1"):
        raise RuntimeError(
            f"`age` no pudo cifrar las calificaciones: {r.stderr.decode(errors='replace')}"
        )
    _escribir(destino, r.stdout)


def _escribir(ruta: Path, contenido: str | bytes) -> None:
    """Escritura atómica (temporal + fsync + renombrar): nunca queda un archivo a medias."""
    datos = contenido.encode() if isinstance(contenido, str) else contenido
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, temporal = tempfile.mkstemp(dir=ruta.parent, prefix=f".{ruta.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as archivo:
            archivo.write(datos)
            archivo.flush()
            os.fsync(archivo.fileno())
        os.chmod(temporal, 0o644)  # mkstemp lo crea solo para el dueño
        os.replace(temporal, ruta)
    except BaseException:
        Path(temporal).unlink(missing_ok=True)
        raise


def _fsync_arbol(carpeta: Path) -> None:
    for ruta in carpeta.rglob("*"):
        if ruta.is_file():
            with ruta.open("rb") as archivo:
                os.fsync(archivo.fileno())


# --- Tabla y resumen -----------------------------------------------------------------------
def _porcentaje(f: FilaTabla) -> str:
    return f"{100 * f.puntos / f.partidas:.1f} %" if f.partidas else "—"


def _nota(equipo: str, calificaciones: dict[str, float]) -> str:
    return f"{calificaciones[equipo]:g}" if equipo in calificaciones else "—"


def _tabla_csv(tabla: list[FilaTabla]) -> str:
    texto = io.StringIO()
    escritor = csv.writer(texto, lineterminator="\n")
    escritor.writerow(
        ["posicion", "equipo", "puntos", "partidas", "victorias", "sb", "anotados", "referencia"]
    )
    for f in tabla:
        escritor.writerow(
            [
                f.posicion,
                f.equipo,
                f.puntos,
                f.partidas,
                f.victorias,
                f"{f.sb:g}",
                f.anotados,
                int(es_reservado(f.equipo)),
            ]
        )
    return texto.getvalue()


def _linea_incidentes(incidentes: list[dict]) -> str:
    if not incidentes:
        return "**Incidentes:** ninguno."
    partes = []
    for i in incidentes:
        estado = "excluida de la tabla" if i["excluida"] else "repetida y completa"
        partes.append(
            f"pareja {i['pareja']} ({' vs '.join(i['equipos'])}): {len(i['fallas'])} "
            f"falla(s) de infraestructura, {estado}"
        )
    return "**Incidentes:** " + "; ".join(partes) + "."


def _resumen_md(
    tabla: list[FilaTabla], calificaciones: dict[str, float], incidentes: list[dict]
) -> str:
    lineas = [
        "## Liga: tabla final",
        "",
        "| Posición | Equipo | Puntos | % | Calificación |",
        "|---:|---|---:|---:|---:|",
    ]
    for f in tabla:
        nombre = f"*{f.equipo}*" if es_reservado(f.equipo) else f.equipo
        lineas.append(
            f"| {f.posicion} | {nombre} | {f.puntos} | {_porcentaje(f)} | "
            f"{_nota(f.equipo, calificaciones)} |"
        )
    lineas += [
        "",
        "En cursiva: participantes de referencia (no se califican).",
        "",
        _linea_incidentes(incidentes),
        "",
    ]
    return "\n".join(lineas)


def _incidentes_md(incidentes: list[dict]) -> str:
    lineas = ["# Incidentes de infraestructura", ""]
    if not incidentes:
        lineas.append("Ninguno.")
    for i in incidentes:
        estado = "**excluida de la tabla**" if i["excluida"] else "repetida y completa"
        lineas.append(f"- Pareja {i['pareja']} ({' vs '.join(i['equipos'])}): {estado}")
        lineas += [f"  - {falla}" for falla in i["fallas"]]
    return "\n".join(lineas) + "\n"


# --- Sitio ---------------------------------------------------------------------------------
_CSS = """
:root { color-scheme: light dark; --fondo: #fff; --texto: #1d1d1f; --suave: #6b6b70;
  --linea: #ddd; --gano: #1a7f37; --perdio: #c62828; }
@media (prefers-color-scheme: dark) { :root { --fondo: #141416; --texto: #eee;
  --suave: #a0a0a8; --linea: #333; --gano: #4cc36b; --perdio: #ff6b6b; } }
body { background: var(--fondo); color: var(--texto); margin: 0 auto; max-width: 960px;
  padding: 16px; font: 15px/1.5 system-ui, sans-serif; }
table { border-collapse: collapse; width: 100%; }
th, td { border-bottom: 1px solid var(--linea); padding: 4px 8px; text-align: left; }
td.n, th.n { text-align: right; font-variant-numeric: tabular-nums; }
.ref { font-style: italic; color: var(--suave); }
.gano { color: var(--gano); } .perdio { color: var(--perdio); }
a { color: inherit; }
"""


def _pagina(titulo: str, cuerpo: str) -> str:
    return (
        '<!doctype html>\n<html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{html.escape(titulo)}</title><style>{_CSS}</style></head>"
        f"<body>{cuerpo}</body></html>\n"
    )


def registro_publico(registro: dict) -> dict:
    """Copia del registro sin `info` ni `salidas` de NINGÚN participante.

    Lo que imprimen o reportan los bots (incluidas nuestras referencias) no va al sitio
    público; el registro completo queda solo en `parejas/` (artifact no público).
    """
    publico = {k: v for k, v in registro.items() if k != "salidas"}
    publico["jugadas"] = [
        {k: v for k, v in j.items() if k != "info"} for j in registro.get("jugadas", [])
    ]
    return publico


def _visor_o_enlace(registro: dict, partidas: Path, ident: str) -> str:
    """Escribe el registro PÚBLICO en JSON y, si está el visor (`visor.generar`), su visor.

    Regresa la ruta (relativa a `partidas/`) a enlazar: el visor si existe, si no el JSON.
    """
    registro = registro_publico(registro)
    _escribir(partidas / f"{ident}.json", json.dumps(registro, ensure_ascii=False))
    try:
        from visor.generar import visor_partida
    except ImportError:
        return f"{ident}.json"
    return visor_partida(registro, partidas / f"{ident}.html").name


def _partidas_por_equipo(registros: list[dict], partidas: Path) -> dict[str, list[dict]]:
    """Genera las partidas del sitio y agrupa por equipo las filas de sus páginas."""
    por_equipo: dict[str, list[dict]] = {}
    vistos: dict[int, int] = {}
    for r in registros:
        m = r["meta"]
        k = vistos[m["pareja"]] = vistos.get(m["pareja"], -1) + 1
        ident = f"{m['pareja']}-{k}"
        enlace = _visor_o_enlace(r, partidas, ident)
        for color in COLORES:
            rival = COLORES[1 - COLORES.index(color)]
            gano = r["ganador"] == color
            motivo = DERROTAS.get(r["motivo"], r["motivo"])
            por_equipo.setdefault(m[color], []).append(
                {
                    "ident": ident,
                    "rival": m[rival],
                    "color": color,
                    "juego": m["juego"],
                    "gano": gano,
                    "marcador": f"{r['puntos'][color]}–{r['puntos'][rival]}",
                    "motivo": f"Rival: {motivo}"
                    if gano and r["motivo"] != "puntos"
                    else ("" if gano else motivo),
                    "enlace": enlace,
                    "json": f"{ident}.json",
                }
            )
    return por_equipo


def _index_html(
    tabla: list[FilaTabla], calificaciones: dict[str, float], incidentes: list[dict]
) -> str:
    filas = []
    for f in tabla:
        clase = ' class="ref"' if es_reservado(f.equipo) else ""
        e = html.escape(f.equipo)
        filas.append(
            f'<tr{clase}><td class="n">{f.posicion}</td>'
            f'<td><a href="equipos/{e}.html">{e}</a></td>'
            f'<td class="n">{f.puntos}</td><td class="n">{f.partidas}</td>'
            f'<td class="n">{_porcentaje(f)}</td><td class="n">{f.sb:g}</td>'
            f'<td class="n">{f.anotados}</td>'
            f'<td class="n">{_nota(f.equipo, calificaciones)}</td></tr>'
        )
    lista = (
        "".join(
            f"<li>Pareja {i['pareja']} ({html.escape(' vs '.join(i['equipos']))}): "
            f"{len(i['fallas'])} falla(s) de infraestructura, "
            f"{'excluida de la tabla' if i['excluida'] else 'repetida y completa'}.</li>"
            for i in incidentes
        )
        or "<li>Ninguno.</li>"
    )
    cuerpo = (
        "<h1>Liga: tabla final</h1>"
        '<table><thead><tr><th class="n">Posición</th><th>Equipo</th>'
        '<th class="n">Puntos</th><th class="n">Partidas</th><th class="n">%</th>'
        '<th class="n">SB</th><th class="n">Anotados</th>'
        '<th class="n">Calificación</th></tr></thead>'
        f"<tbody>{''.join(filas)}</tbody></table>"
        '<p class="ref">En cursiva: participantes de referencia (no se califican). '
        "Desempates: puntos entre empatados, Sonneborn-Berger (SB), peones anotados, "
        "sorteo con la semilla maestra.</p>"
        f"<h2>Incidentes</h2><ul>{lista}</ul>"
    )
    return _pagina("Liga: tabla final", cuerpo)


def _equipo_html(fila: FilaTabla, partidas: list[dict], nota: str) -> str:
    e = html.escape(fila.equipo)
    filas = []
    for p in partidas:
        clase, texto = ("gano", "Ganó") if p["gano"] else ("perdio", "Perdió")
        filas.append(
            f'<tr><td><a href="../partidas/{html.escape(p["enlace"])}">{p["ident"]}</a></td>'
            f'<td><a href="{html.escape(p["rival"])}.html">{html.escape(p["rival"])}</a></td>'
            f'<td>{p["color"]}</td><td class="n">{p["juego"]}</td>'
            f'<td class="{clase}">{texto}</td><td class="n">{p["marcador"]}</td>'
            f"<td>{html.escape(p['motivo'])}</td>"
            f'<td><a href="../partidas/{html.escape(p["json"])}">JSON</a></td></tr>'
        )
    cuerpo = (
        f'<p><a href="../index.html">← Tabla</a></p><h1>{e}</h1>'
        f"<p>Posición {fila.posicion} · {fila.puntos} puntos de {fila.partidas} partidas · "
        f"calificación {html.escape(nota)}</p>"
        "<table><thead><tr><th>Partida</th><th>Rival</th><th>Color</th>"
        '<th class="n">Dados</th><th>Resultado</th><th class="n">Peones</th>'
        "<th>Motivo</th><th>Registro</th></tr></thead>"
        f"<tbody>{''.join(filas)}</tbody></table>"
    )
    return _pagina(f"Liga: {fila.equipo}", cuerpo)


def _sitio(
    salida: Path,
    tabla: list[FilaTabla],
    calificaciones: dict[str, float],
    incidentes: list[dict],
) -> None:
    # Se arma en una carpeta temporal y se cambia al final: no quedan archivos viejos.
    sitio = Path(tempfile.mkdtemp(dir=salida, prefix=".sitio."))
    try:
        _armar_sitio(sitio, salida, tabla, calificaciones, incidentes)
    except BaseException:
        shutil.rmtree(sitio, ignore_errors=True)
        raise
    sitio.chmod(0o755)
    final = salida / "sitio"
    if final.exists():
        viejo = Path(tempfile.mkdtemp(dir=salida, prefix=".sitio.viejo."))
        os.replace(final, viejo / "sitio")
        os.replace(sitio, final)
        shutil.rmtree(viejo)
    else:
        os.replace(sitio, final)


def _armar_sitio(
    sitio: Path,
    salida: Path,
    tabla: list[FilaTabla],
    calificaciones: dict[str, float],
    incidentes: list[dict],
) -> None:
    partidas = sitio / "partidas"
    equipos = sitio / "equipos"
    partidas.mkdir(parents=True, exist_ok=True)
    equipos.mkdir(parents=True, exist_ok=True)
    por_equipo = _partidas_por_equipo(leer_parejas(salida), partidas)
    for f in tabla:
        _escribir(
            equipos / f"{f.equipo}.html",
            _equipo_html(f, por_equipo.get(f.equipo, []), _nota(f.equipo, calificaciones)),
        )
    _escribir(sitio / "index.html", _index_html(tabla, calificaciones, incidentes))
    _fsync_arbol(sitio)


# --- Entrada -------------------------------------------------------------------------------
def publicar(
    salida: Path,
    tabla: list[FilaTabla],
    calificaciones: dict[str, float],
    incidentes: list[dict],
    *,
    claves: dict[str, list[Integrante]] | None = None,
    llave: Path | None = None,
    aceptar_incidentes: bool = False,
) -> None:
    """Publica la liga en `salida/` (ver el inicio de este archivo).

    `claves`: integrantes de cada equipo calificado (ver `leer_integrantes`); solo van al
    archivo cifrado y son obligatorios. `llave`: llave pública `age` (por defecto
    `sistema/llave_profesor.age.pub`). Si alguna pareja quedó excluida por fallas de
    infraestructura, no se publica (los equipos tendrían distinto número de partidas)
    salvo con `aceptar_incidentes=True`: primero hay que volver a jugar esas parejas.

    Todas las revisiones van antes de escribir nada.
    """
    salida = Path(salida)
    excluidas = [str(i["pareja"]) for i in incidentes if i.get("excluida")]
    if excluidas and not aceptar_incidentes:
        raise ValueError(
            f"Hay parejas excluidas por fallas de infraestructura ({', '.join(excluidas)}). "
            "Vuelve a correr la liga en la misma carpeta para jugarlas (reanuda solo esas) "
            "o publica con aceptar_incidentes=True si el profesor así lo decide."
        )
    _revisar_claves(calificaciones, claves or {})
    llave = Path(llave or LLAVE_PROFESOR)
    programa = _revisar_cifrado(llave)
    salida.mkdir(parents=True, exist_ok=True)
    _escribir_cifrado(
        programa,
        llave,
        _csv_calificaciones(tabla, calificaciones, claves or {}),
        salida / "calificaciones.csv.age",
    )
    _escribir(salida / "tabla.csv", _tabla_csv(tabla))
    _escribir(salida / "resumen.md", _resumen_md(tabla, calificaciones, incidentes))
    _escribir(salida / "incidentes.md", _incidentes_md(incidentes))
    _sitio(salida, tabla, calificaciones, incidentes)
