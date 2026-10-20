"""Jugar tú contra un bot desde la terminal (`./torneo jugar humano montecarlo`) y el
tablero en vivo (`--ver`).

Todo aquí cumple la interfaz `ProcesoBot` del árbitro (o envuelve a un bot que la
cumple), así que la partida la decide el mismo árbitro de siempre.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable

from arbitro import protocolo
from arbitro.procesos import ProcesoBot
from cli.salida import limpio
from motor import Estado, Jugada

# Contra un humano nadie pierde por reloj: el árbitro usa este reloj enorme y el bot
# sigue viendo su reloj normal (ver `RelojNormal`).
RELOJ_HUMANO_S = 24 * 3600.0
SALIR = ("salir", "rendirse", "q")
AYUDA = ("jugadas", "ayuda", "?")


class Vista:
    """Lo que comparten los dos lados de una partida para mostrarla: la última jugada."""

    def __init__(self) -> None:
        self.ultima: str | None = None


class BotHumano:
    """Tú, como `ProcesoBot`: muestra el tablero y lee tu jugada del teclado."""

    def __init__(
        self,
        vista: Vista,
        entrada: Callable[[str], str] | None = None,
        imprimir: Callable[..., None] = print,
    ) -> None:
        self._vista = vista
        self._entrada = entrada or (lambda texto: input(texto))
        self._imprimir = imprimir
        self._mensajes: deque[dict] = deque()
        self._rendido = False
        self.color = ""

    # --- ProcesoBot ------------------------------------------------------------------------
    def iniciar(self) -> None:
        self._mensajes.append(protocolo.hola())

    def enviar(self, msg: dict) -> None:
        tipo = msg.get("tipo")
        if tipo == "preparar":
            self.color = msg["config"]["color"]
            self._imprimir(f"\nJuegas con {self.color} ({self.color[0].upper()}).")
            self._mensajes.append(protocolo.listo())
        elif tipo == "jugar":
            texto = self._pedir_jugada(Estado.desde_dict(msg["estado"]))
            if texto is None:
                self._rendido = True
            else:
                self._vista.ultima = f"Tú jugaste {texto}"
                self._mensajes.append(protocolo.jugada(texto, None))
        elif tipo == "fin":
            self._mensajes.append(protocolo.adios(None))

    def recibir(self, timeout_s: float) -> dict | None:
        return self._mensajes.popleft() if self._mensajes else None

    def pausar(self) -> None: ...

    def reanudar(self) -> None: ...

    def terminar(self) -> None: ...

    def salida(self) -> str:
        return "Te rendiste." if self._rendido else ""

    def causa_muerte(self) -> str | None:
        return "error" if self._rendido else None

    def memoria_pico_mb(self) -> float | None:
        return None

    # --- Teclado ---------------------------------------------------------------------------
    def _pedir_jugada(self, estado: Estado) -> str | None:
        legales = estado.jugadas()
        self._imprimir("")
        if self._vista.ultima:
            self._imprimir(self._vista.ultima)
        self._imprimir(estado.dibujar())
        self._imprimir(
            "Escribe tu jugada como e2-e3 · «jugadas» muestra las legales · «salir» te rinde."
        )
        while True:
            try:
                texto = self._entrada("Tu jugada: ").strip().lower()
            except EOFError:
                texto = "salir"
            if texto in SALIR:
                self._imprimir("Te rendiste.")
                return None
            if texto in AYUDA:
                self._imprimir(self._lista(estado, legales))
                continue
            try:
                jugada = Jugada.desde_texto(texto)
            except ValueError as e:
                self._imprimir(str(e))
                continue
            if jugada not in legales:
                self._imprimir(
                    f"{texto} no es legal ahora. Escribe «jugadas» para ver las legales."
                )
                continue
            if estado.es_ataque(jugada):
                self._imprimir(
                    f"Atacas: ganas el combate con probabilidad {estado.prob_ataque(jugada):.2f}."
                )
            return str(jugada)

    @staticmethod
    def _lista(estado: Estado, legales: list[Jugada]) -> str:
        textos = [
            f"{j} (ataque, p={estado.prob_ataque(j):.2f})" if estado.es_ataque(j) else str(j)
            for j in legales
        ]
        return "Jugadas legales: " + ", ".join(textos)


def _texto_jugada(mensaje: dict) -> str:
    """La jugada que mandó el bot, sin caracteres de control y corta (el bot la controla)."""
    return limpio(str(mensaje.get("jugada")))[:20]


class _Envoltura:
    """Delega todo al bot envuelto salvo lo que la subclase cambie."""

    def __init__(self, bot: ProcesoBot) -> None:
        self._bot = bot

    def __getattr__(self, nombre: str):
        return getattr(self._bot, nombre)


class RelojNormal(_Envoltura):
    """El bot que juega contra un humano ve su reloj normal (p. ej. 30 s).

    El árbitro corre con `RELOJ_HUMANO_S` para no apurar al humano; aquí se reescribe
    lo que ve el bot y se lleva su propio reloj, así piensa como en una partida normal.
    """

    def __init__(self, bot: ProcesoBot, reloj_s: float, nombre: str, vista: Vista) -> None:
        super().__init__(bot)
        self._reloj_s = reloj_s
        self._nombre = nombre
        self._vista = vista
        self._usado = 0.0
        self._inicio: float | None = None

    def enviar(self, msg: dict) -> None:
        if msg.get("tipo") == "preparar":
            msg = {**msg, "config": {**msg["config"], "reloj_s": self._reloj_s}}
        elif msg.get("tipo") == "jugar":
            msg = {**msg, "tiempo_restante": max(0.0, self._reloj_s - self._usado)}
            self._inicio = time.monotonic()
        self._bot.enviar(msg)

    def recibir(self, timeout_s: float) -> dict | None:
        mensaje = self._bot.recibir(timeout_s)
        if mensaje is not None and self._inicio is not None:
            self._usado += time.monotonic() - self._inicio
            self._inicio = None
            if mensaje.get("tipo") == "jugada":
                self._vista.ultima = f"{self._nombre} jugó {_texto_jugada(mensaje)}"
        return mensaje


class Mirador:
    """`--ver`: observador de `jugar_partida` que dibuja el tablero tras cada jugada.

    El árbitro lo llama con los dos bots en pausa, así que dibujar (por lento que sea
    la terminal) no le cuesta reloj a nadie. El tablero final lo imprime `jugar`.
    """

    def __init__(
        self,
        nombres: dict[str, str],
        reloj_s: float,
        imprimir: Callable[..., None] = print,
        limpiar: bool = False,
    ) -> None:
        self._nombres = nombres
        self._reloj_s = reloj_s
        self._imprimir = imprimir
        self._limpiar = limpiar
        self._usado = dict.fromkeys(nombres, 0.0)

    def __call__(self, estado: Estado, jugada: dict | None) -> None:
        if jugada is not None:
            self._usado[jugada["color"]] = jugada["reloj"]
        if estado.ganador() is not None:
            return
        if self._limpiar:
            self._imprimir("\x1b[H\x1b[2J", end="")
        if jugada is not None:
            self._imprimir(f"{self._nombres[jugada['color']]} jugó {jugada['jugada']}")
        restante = max(0.0, self._reloj_s - self._usado[estado.turno])
        self._imprimir(
            f"Le toca a {self._nombres[estado.turno]} ({estado.turno}) · "
            f"reloj restante {restante:.1f} s"
        )
        self._imprimir(estado.dibujar(), flush=True)
