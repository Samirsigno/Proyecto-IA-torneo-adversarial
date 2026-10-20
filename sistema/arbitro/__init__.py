"""Árbitro del torneo: corre los bots, lleva el reloj, tira los dados y decide.

Módulos:
- `protocolo`: mensajes JSON por línea entre árbitro y bot.
- `azar`: dados por color y semillas derivadas.
- `runner`: corre DENTRO del contenedor/proceso del bot (`python -m arbitro.runner <carpeta>`).
- `procesos`: `BotLocal` (subproceso) y `BotDocker` (contenedor aislado).
- `partida`: `jugar_partida`, la única fuente de verdad del resultado.
- `registro`: formato v1 del log de una partida.

Este archivo no importa nada a propósito: el runner corre en la imagen de bots,
que no tiene el SDK de Docker.
"""
