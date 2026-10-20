#!/usr/bin/env bash
# Muestrea cada ~2 s la memoria de los contenedores de bots (solo informativo).
# Escribe líneas «imagen uso» en el archivo $1, p. ej. «torneo-bot:mi_equipo 120.5MiB».
# Uso: .github/scripts/memoria.sh memoria.log &   (se detiene al terminar el job)
set -u
log="${1:-memoria.log}"
: >"$log"
while true; do
    # nombre → imagen de los contenedores de bots que corren ahora.
    declare -A imagen=()
    while read -r nombre img; do
        [[ -n "${nombre:-}" ]] && imagen["$nombre"]="$img"
    done < <(docker ps --filter name=torneo-bot- --format '{{.Names}} {{.Image}}' 2>/dev/null)
    if ((${#imagen[@]})); then
        while read -r nombre uso; do
            [[ -n "${imagen[$nombre]:-}" ]] && echo "${imagen[$nombre]} $uso" >>"$log"
        done < <(docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' "${!imagen[@]}" 2>/dev/null)
    fi
    unset imagen
    sleep 2
done
