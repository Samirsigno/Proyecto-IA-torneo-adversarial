"""Liga oficial: `./torneo liga --oficial [--shard i/n] [--estado dir] [--publicar]`.

- Participantes: todas las carpetas de `estudiantes/` con nombre válido y `strategy.py`.
- `--shard i/n` (i de 1 a n) juega solo su parte del calendario en `--estado`; todos los
  shards necesitan la misma semilla (`--semilla`, `$TORNEO_SEMILLA` o la de `--estado`).
- Sin `--shard`: juega todo y publica. `--publicar`: solo publica (shards ya juntados).
- Nunca imprime lo que imprimieron los bots: los logs de Actions son públicos.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import tomllib
from pathlib import Path

from cli import ErrorCLI
from cli.comun import (
    ESTUDIANTES,
    Entorno,
    carpeta_resultados,
    disponibles,
    imprimir,
    imprimir_tabla,
    jugar_liga,
    limites,
    nombre_de_participante,
    tabla_partidas,
)
from config import Limites, cargar_calificacion, es_reservado
from liga.calendario import generar_calendario, repartir
from liga.calificacion import calificar
from liga.ejecutar import hash_calendario, leer_incidentes, leer_parejas, revisar_resultados
from liga.manifest import escribir_manifest
from liga.tabla import construir_tabla


def leer_shard(texto: str) -> tuple[int, int]:
    """«i/n» con i de 1 a n (para humanos) → (i − 1, n) para `repartir` (base 0)."""
    m = re.fullmatch(r"(\d+)/(\d+)", texto.strip())
    if not m or not 1 <= int(m.group(1)) <= int(m.group(2)):
        raise ValueError(f"--shard {texto!r} no es válido: usa i/n con 1 ≤ i ≤ n (p. ej. 2/20).")
    return int(m.group(1)) - 1, int(m.group(2))


def participantes_oficiales() -> dict[str, Path]:
    """Carpetas de estudiantes/ con nombre válido (reglas del validador) y strategy.py."""
    participantes = {}
    for nombre in disponibles():
        carpeta = ESTUDIANTES / nombre
        if nombre_de_participante(nombre) and (carpeta / "strategy.py").is_file():
            participantes[nombre] = carpeta.resolve()
        else:
            imprimir(f"⚠ Se ignora estudiantes/{nombre}/ (nombre inválido o sin strategy.py).")
    if len(participantes) < 2:
        raise ErrorCLI("La liga necesita al menos 2 participantes en estudiantes/.")
    return participantes


def _semilla_guardada(estado: Path) -> int | None:
    try:
        return int(json.loads((estado / "estado_liga.json").read_text())["semilla_maestra"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _semilla(args, estado: Path) -> int:
    semilla = args.semilla
    if semilla is None and os.environ.get("TORNEO_SEMILLA"):
        semilla = int(os.environ["TORNEO_SEMILLA"])
    if semilla is None:
        semilla = _semilla_guardada(estado)
    if semilla is None and args.shard:
        raise ErrorCLI("Con --shard todos los shards necesitan la misma semilla: pasa --semilla N.")
    return secrets.randbits(63) if semilla is None else semilla


def cmd_liga_oficial(args, entorno: Entorno) -> int:
    if args.equipos:
        raise ErrorCLI(
            "La liga --oficial usa todas las carpetas de estudiantes/; no pases equipos."
        )
    estado = Path(args.estado) if args.estado else carpeta_resultados() / "oficial"
    participantes = participantes_oficiales()
    publicos = limites()
    if args.publicar:
        return publicar_oficial(args, estado, participantes, publicos)

    semilla = _semilla(args, estado)
    calendario = generar_calendario(sorted(participantes), args.juegos_dados)
    parte = None
    if args.shard:
        try:
            shard, total = leer_shard(args.shard)
        except ValueError as e:
            raise ErrorCLI(str(e)) from None
        calendario = repartir(calendario, shard, total)
        parte = (shard + 1, total)
        imprimir(f"Shard {args.shard}: {len(calendario)} partidas.")
    en_juego = {
        e: participantes[e] for e in sorted({x for p in calendario for x in (p.blancas, p.negras)})
    }
    entorno.preparar(en_juego)  # sin imagen de algún equipo: error antes de jugar nada
    registros: list[dict] = []
    if calendario:
        try:
            registros = jugar_liga(
                participantes,
                args.juegos_dados,
                semilla,
                estado,
                entorno,
                publicos,
                calendario,
                shard=parte,
            )
        except ValueError as e:  # otra liga en --estado
            raise ErrorCLI(str(e)) from None
    estado.mkdir(parents=True, exist_ok=True)
    escribir_manifest(estado, participantes, semilla)
    tabla_partidas(registros, publicos, con_salida=False)
    if args.shard:
        imprimir(f"Shard {args.shard} listo: {len(registros)} partidas en {estado}.")
        return 0
    return publicar_oficial(args, estado, participantes, publicos)


def publicar_oficial(args, estado: Path, participantes: dict[str, Path], publicos: Limites) -> int:
    from liga.publicar import leer_integrantes, publicar
    from validador import validar_equipo

    semilla = _semilla_guardada(estado)
    if semilla is None:
        raise ErrorCLI(f"No encontré {estado}/estado_liga.json: juega la liga antes de publicar.")
    try:
        registros = leer_parejas(estado)
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise ErrorCLI(f"No pude leer las partidas de {estado}: {e}") from None
    incidentes = leer_incidentes(estado)
    calendario = generar_calendario(sorted(participantes), args.juegos_dados)
    guardado = json.loads((estado / "estado_liga.json").read_text(encoding="utf-8"))
    if guardado.get("calendario") != hash_calendario(calendario):
        raise ErrorCLI(
            f"{estado}/estado_liga.json es de otro calendario (otros participantes o "
            "--juegos-dados): no se publica."
        )
    problemas = revisar_resultados(calendario, registros, incidentes, semilla)
    if problemas:
        raise ErrorCLI(
            "Los resultados no coinciden con el calendario de la liga; no se publica:\n"
            + "\n".join(f"  - {p}" for p in problemas[:20])
            + "\nJunta las carpetas de todos los shards (de la misma corrida) y reanuda."
        )
    tabla = construir_tabla(registros, semilla, list(participantes))
    alumnos = {e for e in participantes if not es_reservado(e)}
    no_calificables = {  # mismas reglas que el PR de entrega
        e
        for e in alumnos
        if not validar_equipo(participantes[e], publicos, jugar_humo=False, entrega=True).ok
    }
    notas = calificar(tabla, cargar_calificacion(), alumnos, no_calificables)
    try:
        claves = {e: leer_integrantes(participantes[e]) for e in notas}
        publicar(
            estado,
            tabla,
            notas,
            incidentes,
            claves=claves,
            aceptar_incidentes=args.aceptar_incidentes,
        )
    except (OSError, RuntimeError, ValueError, tomllib.TOMLDecodeError) as e:
        raise ErrorCLI(f"No se publicó la liga: {e}") from None
    imprimir_tabla("Tabla oficial", tabla)
    if no_calificables:
        imprimir(f"⚠ {len(no_calificables)} equipos juegan pero no reciben calificación.")
    imprimir(f"Publicado en {estado}: tabla.csv, calificaciones.csv.age, resumen.md, sitio/.")
    return 0
