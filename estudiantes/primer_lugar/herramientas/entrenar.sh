#!/usr/bin/env bash
# Entrena la tabla V(ŝ) dentro del Docker del torneo, con todos los núcleos que tenga Docker.
#
#   estudiantes/primer_lugar/herramientas/entrenar.sh                # hasta Ctrl+C
#   estudiantes/primer_lugar/herramientas/entrenar.sh --horas 8      # se detiene solo
#   estudiantes/primer_lugar/herramientas/entrenar.sh --workers 6    # menos núcleos
#
# Guarda cada 5 min en herramientas/tablas/<tu usuario>.npy (y .json) y, si lo vuelves a correr,
# continúa desde ahí. Ctrl+C (o `docker stop`) detiene y guarda. Más opciones: --help.
set -euo pipefail

IMAGEN="torneo-base:local"
EQUIPO="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAIZ="$(cd -P "$EQUIPO/../.." && pwd)"

docker image inspect "$IMAGEN" >/dev/null 2>&1 || {
    echo "✗ Falta la imagen $IMAGEN. Desde la raíz del repo corre primero: ./torneo construir" >&2
    exit 2
}

# Linux: corre con tu usuario (las tablas quedan tuyas). En Mac, Docker Desktop ya lo hace.
usuario=()
[[ "$(uname -s)" == Darwin ]] || usuario=(--user "$(id -u):$(id -g)")
terminal=()
[[ -t 0 && -t 1 ]] && terminal=(-it)

# El repo se monta en /torneo: la imagen encuentra `motor` en /torneo/sistema. La caché de numba
# va a resultados/ (ignorada por git) para no recompilar en cada corrida.
exec docker run --rm --init ${terminal[@]+"${terminal[@]}"} ${usuario[@]+"${usuario[@]}"} \
    -e HOME=/tmp \
    -e NUMBA_CACHE_DIR=/torneo/resultados/.cache/numba_entrenamiento \
    -e ENTRENAMIENTO_ETIQUETA="$(whoami)" \
    -v "$RAIZ:/torneo" -w "/torneo/${EQUIPO#"$RAIZ"/}" \
    "$IMAGEN" python herramientas/entrenamiento.py "$@"
