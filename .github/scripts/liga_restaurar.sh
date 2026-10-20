#!/usr/bin/env bash
# Deja el checkout listo para jugar/publicar la liga (lo usa _liga.yml).
#   liga_restaurar.sh <oficial|mini> <carpeta con preparado.tar.gz[.age]>
# - oficial: descifra con $LIGA_LLAVE (llave age), copia los tiers a estudiantes/ y los
#   límites oficiales a .liga/limites.toml (TORNEO_LIMITES).
# - mini: deja en estudiantes/ solo random y montecarlo.
#   También exporta LIGA_DESTINATARIO (la parte pública de la llave) para cifrar después.
# En ambos exporta TORNEO_SEMILLA (vía $GITHUB_ENV) para que todos los shards usen la misma.
set -euo pipefail
modo="$1"
origen="$2"
destino="$RUNNER_TEMP/preparado"
rm -rf "$destino"
mkdir -p "$destino"

if [[ "$modo" == oficial ]]; then
    : "${LIGA_LLAVE:?Falta el secreto LIGA_LLAVE en el Environment}"
    llave="$(mktemp)"
    trap 'rm -f "$llave"' EXIT
    printf '%s\n' "$LIGA_LLAVE" >"$llave"
    age --decrypt -i "$llave" "$origen/preparado.tar.gz.age" | tar -xz -C "$destino"
    # Destinatario PÚBLICO de la llave: los pasos que corren después de código de alumnos
    # cifran solo con él (nunca ven LIGA_LLAVE).
    echo "LIGA_DESTINATARIO=$(age-keygen -y "$llave")" >>"$GITHUB_ENV"
    rm -f "$llave"
    shopt -s nullglob
    tiers=("$destino"/tiers/tier_*/)
    ((${#tiers[@]})) || { echo "::error::El paquete no trae tiers."; exit 1; }
    for t in "${tiers[@]}"; do
        nombre="$(basename "$t")"
        rm -rf "estudiantes/$nombre"
        cp -a "$t" "estudiantes/$nombre"
    done
    mkdir -p .liga
    cp "$destino/limites.toml" .liga/limites.toml
    echo "TORNEO_LIMITES=$PWD/.liga/limites.toml" >>"$GITHUB_ENV"
    echo "Tiers: ${#tiers[@]} · límites oficiales en .liga/limites.toml"
else
    tar -xzf "$origen/preparado.tar.gz" -C "$destino"
    for d in estudiantes/*/; do
        case "$(basename "$d")" in
        random | montecarlo) ;;
        *) rm -rf "$d" ;;
        esac
    done
    echo "Ensayo: solo random y montecarlo."
fi

semilla="$(cat "$destino/semilla")"
[[ "$semilla" =~ ^[0-9]+$ ]] || { echo "::error::Semilla inválida."; exit 1; }
echo "TORNEO_SEMILLA=$semilla" >>"$GITHUB_ENV"
ls estudiantes
