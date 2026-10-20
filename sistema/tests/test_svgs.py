"""Los dibujos de reglas del README deben coincidir con lo que genera el motor."""

import xml.dom.minidom

from herramientas.dibujar_reglas import CARPETA_IMG, DIAGRAMAS, generar


def test_svgs_generados_actuales(tmp_path):
    generar(tmp_path)
    for nombre in DIAGRAMAS:
        actual = (CARPETA_IMG / nombre).read_text(encoding="utf-8")
        assert actual == (tmp_path / nombre).read_text(encoding="utf-8"), (
            f"{nombre} está desactualizado: corre `python -m herramientas.dibujar_reglas` "
            "desde sistema/."
        )


def test_svgs_son_xml_valido_y_autocontenidos():
    for nombre in DIAGRAMAS:
        texto = (CARPETA_IMG / nombre).read_text(encoding="utf-8")
        xml.dom.minidom.parseString(texto)
        assert "http://" not in texto.replace("http://www.w3.org/2000/svg", "")
        assert "<image" not in texto
