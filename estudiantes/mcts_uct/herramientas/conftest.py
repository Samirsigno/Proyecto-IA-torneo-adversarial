"""pytest en herramientas/: hace importable la raíz del equipo (`import strategy`)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
