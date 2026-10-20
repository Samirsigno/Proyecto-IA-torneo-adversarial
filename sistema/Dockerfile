# syntax=docker/dockerfile:1
# Imágenes del torneo. Funcionan en linux/amd64 y linux/arm64 (Mac con Apple
# Silicon). Construir desde la raíz del repo:
#   docker build -f sistema/Dockerfile --target bot -t torneo-bot-base:local .
#   docker build -f sistema/Dockerfile --target cli -t torneo-base:local .
#
# - bot (`torneo-bot-base`): donde corren los bots. Python + numpy/scipy/numba
#   fijados + el código de sistema/. Sin cliente Docker, sin compilador de C,
#   usuario sin privilegios (65534 = nobody).
# - cli (`torneo-base`): el CLI del torneo = bot + cliente Docker (docker-ce-cli
#   y el paquete `docker` de Python). Corre como root para usar el socket.

# ---------------------------------------------------------------- bot
FROM python:3.12-slim-bookworm AS bot

# PYTHONPATH en vez de instalar sistema/: cualquier paquete nuevo bajo
# sistema/ (motor, cli, ...) se importa sin reconstruir cuando el repo se
# monta en /torneo.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/torneo/sistema \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    NUMBA_CACHE_DIR=/tmp/numba \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMBA_NUM_THREADS=1

WORKDIR /torneo

# Bytecode (.pyc) en un árbol aparte, de solo lectura al jugar: Python ignora los
# __pycache__ de la carpeta del bot (/bot no tiene entradas aquí) y no escribe nada.
ENV PYTHONPYCACHEPREFIX=/opt/pyc

# constraints.txt solo tiene versiones exactas: sirve como lista a instalar.
COPY sistema/constraints.txt sistema/
RUN pip install --only-binary=:all: -r sistema/constraints.txt \
    && python -m compileall -q /usr/local/lib/python3.12

COPY sistema/ sistema/
RUN python -m compileall -q /torneo/sistema

USER 65534:65534
CMD ["python"]

# ---------------------------------------------------------------- cli
FROM bot AS cli

USER root

# Cliente Docker (sin el daemon): el CLI usa el socket del anfitrión.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl; \
    install -m 0755 -d /etc/apt/keyrings; \
    curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc; \
    . /etc/os-release; \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian ${VERSION_CODENAME} stable" \
        > /etc/apt/sources.list.d/docker.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends docker-ce-cli; \
    apt-get purge -y curl; \
    apt-get autoremove -y; \
    rm -rf /var/lib/apt/lists/*

# requirements.txt = mismas versiones fijadas + el paquete `docker` de Python.
RUN pip install --only-binary=:all: -r sistema/requirements.txt -c sistema/constraints.txt

CMD ["python", "-m", "cli"]
