"""pytest en herramientas/: hace importable la raíz del equipo.

`specs.py` vive en la raíz (lo importa strategy.py, y el código de la liga no puede importar
herramientas/), pero los tests lo importan como `from specs import ...`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
