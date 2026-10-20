#!/usr/bin/env bash
# Se corre una vez al crear el Codespace: deja listo ./torneo.
# Codespaces: Python 3.12 + Docker dentro del contenedor (feature docker-in-docker).
# Después, en la terminal: ./torneo jugar mi_equipo montecarlo
set -euo pipefail
cd "$(dirname "$0")/.."

echo "Instalando numpy, scipy y numba para el editor y para --sin-docker..."
# -e sistema: el editor encuentra `from motor import ...` en tu strategy.py.
if ! python -m pip install --quiet --user -r sistema/requirements.txt -c sistema/constraints.txt ||
    ! python -m pip install --quiet --user -e sistema; then
    echo "⚠ No se pudieron instalar; ./torneo con Docker funciona igual."
fi

echo "Esperando a Docker..."
for _ in $(seq 60); do
    docker info >/dev/null 2>&1 && break
    sleep 2
done

# Construye las imágenes del torneo en el Codespace (unos minutos) y llena la caché de numba.
./torneo calentar

echo
echo "✓ Listo. Prueba en la terminal:  ./torneo jugar random montecarlo"
