"""Dibuja los diagramas de reglas del README (SVG) a partir de posiciones reales del motor.

Uso (desde la carpeta sistema/):
    python -m herramientas.dibujar_reglas            # reescribe docs/img/*.svg
    python -m herramientas.dibujar_reglas --salida X # en otra carpeta

Los diagramas se calculan con `motor` (jugadas legales, probabilidades, puntos), así que
no pueden contradecir las reglas. Solo usa la biblioteca estándar para escribir el SVG.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from motor import Estado, Jugada, prob_combate
from motor.jugada import casilla_de_texto

CARPETA_IMG = Path(__file__).resolve().parents[2] / "docs" / "img"
LADO = 9
CELDA = 52
ANCHO = 460
FUENTE = "'DejaVu Sans', Verdana, Arial, Helvetica, sans-serif"

FONDO = "#fbf8f1"
BORDE = "#d8cfbd"
TINTA = "#2b2b2b"
TINTA_SUAVE = "#6b6558"
CLARA = "#f0e2c4"
OSCURA = "#c49a6c"
BLANCA = "#ffffff"
NEGRA = "#2f2f33"
VERDE = "#2e9d57"
ROJO = "#d33a3a"
AZUL = "#2f6fcb"
GRIS = "#8d877a"
TINTE = {VERDE: "#8fd1a8", ROJO: "#ee9a9a", AZUL: "#9db9ea"}


def _num(x: float) -> str:
    return f"{x:.1f}".rstrip("0").rstrip(".")


def _texto(x, y, s, tam=14, color=TINTA, ancla="middle", peso="normal") -> str:
    return (
        f'<text x="{_num(x)}" y="{_num(y)}" font-family="{FUENTE}" font-size="{tam}" '
        f'fill="{color}" text-anchor="{ancla}" font-weight="{peso}">{s}</text>'
    )


class Tablero:
    """Ventana rectangular del tablero (columnas y filas, base 0) con su geometría."""

    def __init__(self, x0, y0, cols, filas, estado: Estado, celda=CELDA) -> None:
        self.x0, self.y0, self.celda = x0, y0, celda
        self.c0, self.c1 = cols
        self.f0, self.f1 = filas
        self.estado = estado

    @property
    def ancho(self) -> float:
        return (self.c1 - self.c0 + 1) * self.celda

    @property
    def alto(self) -> float:
        return (self.f1 - self.f0 + 1) * self.celda

    def centro(self, casilla: str) -> tuple[float, float]:
        c = casilla_de_texto(casilla)
        col, fila = c % LADO, c // LADO
        x = self.x0 + (col - self.c0 + 0.5) * self.celda
        y = self.y0 + (self.f1 - fila + 0.5) * self.celda
        return x, y

    def casillas(self) -> str:
        out = []
        for fila in range(self.f0, self.f1 + 1):
            for col in range(self.c0, self.c1 + 1):
                x = self.x0 + (col - self.c0) * self.celda
                y = self.y0 + (self.f1 - fila) * self.celda
                color = OSCURA if (col + fila) % 2 == 0 else CLARA
                out.append(
                    f'<rect x="{_num(x)}" y="{_num(y)}" width="{self.celda}" '
                    f'height="{self.celda}" fill="{color}"/>'
                )
        out.append(
            f'<rect x="{_num(self.x0)}" y="{_num(self.y0)}" width="{_num(self.ancho)}" '
            f'height="{_num(self.alto)}" fill="none" stroke="{TINTA}" stroke-width="1.5"/>'
        )
        return "\n".join(out)

    def coordenadas(self) -> str:
        out = []
        for col in range(self.c0, self.c1 + 1):
            x = self.x0 + (col - self.c0 + 0.5) * self.celda
            letra = "abcdefghi"[col]
            out.append(_texto(x, self.y0 - 7, letra, 13, TINTA_SUAVE, peso="bold"))
            out.append(_texto(x, self.y0 + self.alto + 17, letra, 13, TINTA_SUAVE, peso="bold"))
        for fila in range(self.f0, self.f1 + 1):
            y = self.y0 + (self.f1 - fila + 0.5) * self.celda + 4.5
            out.append(_texto(self.x0 - 10, y, str(fila + 1), 13, TINTA_SUAVE, peso="bold"))
            out.append(
                _texto(
                    self.x0 + self.ancho + 10, y, str(fila + 1), 13, TINTA_SUAVE, "middle", "bold"
                )
            )
        return "\n".join(out)

    def piezas(self) -> str:
        d = self.estado.a_dict()
        out = []
        for nombre, relleno, trazo in (("blancas", BLANCA, TINTA), ("negras", NEGRA, "#000000")):
            for casilla in d[nombre]:
                c = casilla_de_texto(casilla)
                if not (self.c0 <= c % LADO <= self.c1 and self.f0 <= c // LADO <= self.f1):
                    continue
                out.append(pieza(*self.centro(casilla), relleno, trazo, self.celda * 0.33))
        return "\n".join(out)

    def marco(self) -> str:
        return "\n".join((self.casillas(), self.coordenadas()))


def pieza(x, y, relleno, trazo, radio=None) -> str:
    r = radio or CELDA * 0.33
    brillo = "#ffffff" if relleno == NEGRA else "#e5e0d3"
    return (
        f'<circle cx="{_num(x)}" cy="{_num(y)}" r="{_num(r)}" fill="{relleno}" '
        f'stroke="{trazo}" stroke-width="2"/>'
        f'<circle cx="{_num(x)}" cy="{_num(y)}" r="{_num(r * 0.55)}" fill="none" '
        f'stroke="{brillo}" stroke-width="1.5" opacity="0.55"/>'
    )


def flecha(p, q, color, ancho=5, recorte_ini=18, recorte_fin=20, trazo="") -> str:
    """Flecha de p a q, acortada en los extremos para no tapar las fichas."""
    dx, dy = q[0] - p[0], q[1] - p[1]
    largo = math.hypot(dx, dy)
    ux, uy = dx / largo, dy / largo
    x1, y1 = p[0] + ux * recorte_ini, p[1] + uy * recorte_ini
    x2, y2 = q[0] - ux * recorte_fin, q[1] - uy * recorte_fin
    cabeza = 15
    bx, by = x2 - ux * cabeza, y2 - uy * cabeza
    nx, ny = -uy, ux
    puntos = (
        f"{_num(x2)},{_num(y2)} {_num(bx + nx * 8)},{_num(by + ny * 8)} "
        f"{_num(bx - nx * 8)},{_num(by - ny * 8)}"
    )
    return (
        f'<line x1="{_num(x1)}" y1="{_num(y1)}" x2="{_num(bx)}" y2="{_num(by)}" '
        f'stroke="{color}" stroke-width="{ancho}" stroke-linecap="round"{trazo}/>'
        f'<polygon points="{puntos}" fill="{color}"/>'
    )


def marca_destino(x, y, color) -> str:
    """Resalta una casilla destino con el color de la jugada."""
    return (
        f'<rect x="{_num(x - CELDA / 2 + 2)}" y="{_num(y - CELDA / 2 + 2)}" '
        f'width="{CELDA - 4}" height="{CELDA - 4}" fill="{TINTE[color]}" '
        f'stroke="{color}" stroke-width="3"/>'
    )


def cruz(x, y, color=GRIS) -> str:
    d = 11
    return (
        f'<path d="M{_num(x - d)} {_num(y - d)} L{_num(x + d)} {_num(y + d)} '
        f'M{_num(x + d)} {_num(y - d)} L{_num(x - d)} {_num(y + d)}" '
        f'stroke="{color}" stroke-width="5" stroke-linecap="round" opacity="0.85"/>'
    )


def documento(ancho, alto, titulo, descripcion, cuerpo: list[str]) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ancho} {alto}" '
        f'width="{ancho}" height="{alto}" role="img" aria-labelledby="t d">\n'
        f'<title id="t">{titulo}</title>\n<desc id="d">{descripcion}</desc>\n'
        f'<rect x="1" y="1" width="{ancho - 2}" height="{alto - 2}" rx="14" fill="{FONDO}" '
        f'stroke="{BORDE}" stroke-width="2"/>\n' + "\n".join(cuerpo) + "\n</svg>\n"
    )


def _leyenda(x, y, color, texto) -> list[str]:
    return [
        f'<rect x="{x}" y="{y - 13}" width="18" height="18" rx="3" fill="{TINTE[color]}" '
        f'stroke="{color}" stroke-width="2.5"/>',
        _texto(x + 26, y + 1, texto, 14, TINTA, "start"),
    ]


# --- Diagramas ----------------------------------------------------------------


def tablero_inicial() -> str:
    e = Estado.inicial()
    celda = 44
    x0, y0 = (ANCHO - 9 * celda) / 2, 66
    t = Tablero(x0, y0, (0, 8), (0, 8), e, celda)
    ancho, alto = ANCHO, y0 + t.alto + 98
    cuerpo = [
        _texto(ancho / 2, 32, "Tablero inicial: 9 × 9", 20, TINTA, peso="bold"),
        t.marco(),
        t.piezas(),
    ]
    # etiquetas laterales de cada ejército
    cuerpo.append(
        _texto(
            ancho / 2,
            y0 + t.alto + 44,
            "Blancas: filas 1 y 2 (18 peones), avanzan hacia arriba",
            13,
            TINTA,
        )
    )
    cuerpo.append(
        _texto(
            ancho / 2,
            y0 + t.alto + 64,
            "Negras: filas 8 y 9 (18 peones), avanzan hacia abajo",
            13,
            TINTA,
        )
    )
    cuerpo.append(_texto(ancho / 2, y0 + t.alto + 84, "Empiezan las Blancas", 13, TINTA_SUAVE))
    return documento(
        ancho,
        alto,
        "Tablero inicial",
        "Tablero de 9 por 9 con 18 peones blancos en las filas 1 y 2 y 18 negros en las filas 8 y 9.",  # noqa: E501
        cuerpo,
    )


def moverse() -> str:
    e = Estado.desde_dict({"blancas": ["e4"], "negras": ["f5"], "turno": "blancas"})
    movs = {str(j): j for j in e.jugadas()}
    assert set(movs) == {"e4-e5", "e4-d5", "e4-f5"}
    x0, y0 = (ANCHO - 5 * CELDA) / 2, 66
    t = Tablero(x0, y0, (2, 6), (2, 5), e)
    ancho, alto = ANCHO, y0 + t.alto + 150
    origen = t.centro("e4")
    cuerpo = [_texto(ancho / 2, 32, "Cómo se mueve un peón", 20, TINTA, peso="bold"), t.casillas()]
    for texto, j in movs.items():
        ataque = e.es_ataque(j)
        destino = t.centro(texto.split("-")[1])
        cuerpo.append(marca_destino(*destino, ROJO if ataque else VERDE))
    cuerpo.append(t.coordenadas())
    cuerpo.append(t.piezas())
    for texto, j in movs.items():
        ataque = e.es_ataque(j)
        cuerpo.append(flecha(origen, t.centro(texto.split("-")[1]), ROJO if ataque else VERDE))
    for casilla in ("d4", "f4", "e3"):  # lo que NO se puede
        cuerpo.append(cruz(*t.centro(casilla)))
    ly = y0 + t.alto + 46
    cuerpo += _leyenda(46, ly, VERDE, "Avanza a una casilla vacía (recto o diagonal)")
    cuerpo += _leyenda(46, ly + 28, ROJO, "Ataca en diagonal a un rival (se tira un dado)")
    cuerpo.append(
        f'<path d="M52 {ly + 49} l12 12 m0 -12 l-12 12" stroke="{GRIS}" stroke-width="3.5" stroke-linecap="round"/>'  # noqa: E501
    )
    cuerpo.append(
        _texto(76, ly + 60, "Nunca hacia atrás ni de lado; no se ataca recto", 14, TINTA, "start")
    )
    return documento(
        ancho,
        alto,
        "Movimiento del peón",
        "Un peón blanco en e4 puede avanzar recto a e5 y en diagonal a d5, ambas casillas vacías, "
        "o atacar en diagonal al peón negro en f5. No puede ir hacia atrás ni de lado.",
        cuerpo,
    )


def combate() -> str:
    e = Estado.desde_dict(
        {
            "blancas": ["e4", "d3", "f3"],
            "negras": ["f5", "g6"],
            "turno": "blancas",
        }
    )
    ataque = Jugada.desde_texto("e4-f5")
    assert e.es_ataque(ataque)
    p = e.prob_ataque(ataque)
    assert p == prob_combate(2, 1) == 0.65
    x0, y0 = (ANCHO - 6 * CELDA) / 2, 74
    t = Tablero(x0, y0, (2, 7), (1, 6), e)
    ancho = ANCHO
    ty = y0 + t.alto + 44  # tabla
    alto = ty + 220
    cuerpo = [
        _texto(ancho / 2, 32, "Combate: el apoyo decide", 20, TINTA, peso="bold"),
        t.marco(),
    ]
    atq, dfn = t.centro("e4"), t.centro("f5")
    cuerpo.append(marca_destino(*dfn, ROJO))
    cuerpo.append(t.piezas())
    for apoyo in ("d3", "f3"):
        a = t.centro(apoyo)
        cuerpo.append(_linea_apoyo(a, atq, AZUL))
    cuerpo.append(_linea_apoyo(t.centro("g6"), dfn, ROJO))
    cuerpo.append(flecha(atq, dfn, ROJO, 5, 20, 20))
    # rótulos
    cuerpo.append(_texto(atq[0] - 33, atq[1] + 5.5, "A", 18, TINTA, peso="bold"))
    cuerpo.append(_texto(dfn[0] + 33, dfn[1] + 5.5, "D", 18, TINTA, peso="bold"))
    cuerpo.append(_insignia(t.centro("d3"), "+1", AZUL))
    cuerpo.append(_insignia(t.centro("f3"), "+1", AZUL))
    cuerpo.append(_insignia(t.centro("g6"), "+1", ROJO))
    # explicación
    cuerpo.append(
        _texto(
            ancho / 2,
            ty - 8,
            "A ataca a D: apoyo 2 contra 1, diferencia +1",
            14,
            TINTA,
            peso="bold",
        )
    )
    cuerpo.append(
        _texto(
            ancho / 2, ty + 14, "Apoyo = tus peones en las 2 diagonales de atrás", 13, TINTA_SUAVE
        )
    )
    cuerpo.append(_texto(ancho / 2, ty + 50, "p = 0.5 + 0.15 × diferencia", 13, TINTA_SUAVE))
    cuerpo.append(
        _texto(
            ancho / 2,
            ty + 32,
            "Líneas punteadas: azul = apoyo de A · rojo = apoyo de D",
            13,
            TINTA_SUAVE,
        )
    )
    cuerpo.append(_probabilidad(ancho / 2, ty + 90, p))
    cuerpo.append(_tabla(ancho / 2, ty + 138, resaltar=1))
    return documento(
        ancho,
        alto,
        "Combate",
        "Un peón blanco en e4 con dos peones de apoyo ataca a un peón negro en f5 con un apoyo: "
        "diferencia +1, probabilidad de ganar 0.65. Tabla: diferencia -2 a +2, "
        "probabilidades 0.20, 0.35, 0.50, 0.65, 0.80.",
        cuerpo,
    )


def _linea_apoyo(p, q, color) -> str:
    dx, dy = q[0] - p[0], q[1] - p[1]
    largo = math.hypot(dx, dy)
    ux, uy = dx / largo, dy / largo
    return (
        f'<line x1="{_num(p[0] + ux * 20)}" y1="{_num(p[1] + uy * 20)}" '
        f'x2="{_num(q[0] - ux * 20)}" y2="{_num(q[1] - uy * 20)}" stroke="{color}" '
        f'stroke-width="3.5" stroke-dasharray="7 6" stroke-linecap="round"/>'
    )


def _insignia(c, texto, color) -> str:
    x, y = c[0] + 17, c[1] - 17
    return (
        f'<circle cx="{_num(x)}" cy="{_num(y)}" r="11" fill="{color}" stroke="#ffffff" stroke-width="2"/>'  # noqa: E501
        + _texto(x, y + 4, texto, 11, "#ffffff", peso="bold")
    )


def _probabilidad(cx, y, p) -> str:
    return (
        f'<rect x="{_num(cx - 160)}" y="{y - 24}" width="320" height="38" rx="19" '
        f'fill="#f8dede" stroke="{ROJO}" stroke-width="2"/>'
        + _texto(cx, y + 1, f"Probabilidad de ganar: p = {p:.2f}", 17, TINTA, peso="bold")
    )


def _tabla(cx, y, resaltar: int) -> str:
    anchos = 62
    etiquetas = [-2, -1, 0, 1, 2]
    x0 = cx - (len(etiquetas) + 1) * anchos / 2 - 4
    out = [
        _texto(
            x0 - 0,
            y - 12,
            "Diferencia de apoyo (A − D) y probabilidad p:",
            13,
            TINTA_SUAVE,
            "start",
        )
    ]
    y_top = y
    for fila, (rotulo, valores) in enumerate(
        (("diferencia", etiquetas), ("p", [prob_combate(2 + d, 2) for d in etiquetas]))
    ):
        # prob_combate(2 + d, 2) con d en -2..2 queda dentro de [0.2, 0.9]: sin recorte
        yy = y_top + fila * 34
        out.append(_texto(x0 + 40, yy + 23, rotulo, 13, TINTA_SUAVE, "end"))
        for i, v in enumerate(valores):
            xx = x0 + 52 + i * anchos
            activo = etiquetas[i] == resaltar
            relleno = ROJO if activo else "#ffffff"
            out.append(
                f'<rect x="{_num(xx)}" y="{yy + 4}" width="{anchos - 4}" height="28" rx="5" '
                f'fill="{relleno}" stroke="{BORDE}" stroke-width="1.5"/>'
            )
            txt = (f"{v:+d}" if v else "0") if fila == 0 else f"{v:.2f}"
            color = "#ffffff" if activo else TINTA
            out.append(
                _texto(
                    xx + (anchos - 4) / 2, yy + 23, txt.replace("-", "−"), 14, color, peso="bold"
                )
            )
    return "\n".join(out)


def anotar() -> str:
    e = Estado.desde_dict({"blancas": ["e8"], "negras": [], "turno": "blancas"})
    j = Jugada.desde_texto("e8-e9")
    assert j in e.jugadas()
    despues = e.aplicar(j)
    assert despues.puntos == {"blancas": 1, "negras": 0}
    assert "e9" not in despues.a_dict()["blancas"]
    x0, y0 = (ANCHO - 5 * CELDA) / 2, 66
    t = Tablero(x0, y0, (2, 6), (5, 8), e)
    ancho, alto = ANCHO, y0 + t.alto + 170
    origen, meta = t.centro("e8"), t.centro("e9")
    cuerpo = [_texto(ancho / 2, 32, "Cómo se anota un punto", 20, TINTA, peso="bold"), t.casillas()]
    # franja de la meta
    cuerpo.append(
        f'<rect x="{_num(t.x0)}" y="{_num(t.y0)}" width="{_num(t.ancho)}" height="{t.celda}" '
        f'fill="none" stroke="{VERDE}" stroke-width="3" stroke-dasharray="6 5"/>'
    )
    cuerpo.append(marca_destino(*meta, VERDE))
    cuerpo.append(t.coordenadas())
    cuerpo.append(t.piezas())
    cuerpo.append(flecha(origen, meta, VERDE))
    cuerpo.append(_texto(t.x0 + t.ancho - 6, t.y0 + 16, "última fila", 12, TINTA_SUAVE, "end"))
    ly = y0 + t.alto + 46
    cuerpo.append(
        _texto(
            ancho / 2,
            ly,
            "Llega a la última fila: +1 punto y sale del tablero",
            14,
            TINTA,
            peso="bold",
        )
    )
    cuerpo.append(
        _texto(
            ancho / 2,
            ly + 22,
            "Blancas anotan en la fila 9, Negras en la fila 1.",
            13,
            TINTA_SUAVE,
        )
    )
    cuerpo.append(_marcador(ancho / 2, ly + 52, despues.puntos["blancas"]))
    cuerpo.append(
        _texto(ancho / 2, ly + 100, "Gana quien llega a 3 puntos", 16, TINTA, peso="bold")
    )
    return documento(
        ancho,
        alto,
        "Anotar un punto",
        "Un peón blanco en e8 avanza a la fila 9, anota un punto y sale del tablero. "
        "Gana quien llegue a 3 puntos.",
        cuerpo,
    )


def _marcador(cx, y, puntos) -> str:
    out = []
    for i in range(3):
        x = cx - 40 + i * 40
        lleno = i < puntos
        out.append(
            f'<circle cx="{_num(x)}" cy="{y}" r="13" fill="{VERDE if lleno else "#ffffff"}" '
            f'stroke="{VERDE}" stroke-width="2.5"/>'
        )
        if lleno:
            out.append(_texto(x, y + 5, "+1", 12, "#ffffff", peso="bold"))
    return "\n".join(out)


DIAGRAMAS = {
    "tablero_inicial.svg": tablero_inicial,
    "moverse.svg": moverse,
    "combate.svg": combate,
    "anotar.svg": anotar,
}


def generar(salida: Path = CARPETA_IMG) -> list[Path]:
    """Escribe los SVG en `salida` y regresa sus rutas."""
    salida.mkdir(parents=True, exist_ok=True)
    rutas = []
    for nombre, f in DIAGRAMAS.items():
        ruta = salida / nombre
        ruta.write_text(f(), encoding="utf-8", newline="\n")
        rutas.append(ruta)
    return rutas


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--salida", type=Path, default=CARPETA_IMG)
    for r in generar(ap.parse_args().salida):
        print(r)


if __name__ == "__main__":
    main()
