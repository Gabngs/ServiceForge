"""Núcleo del pipeline de dataset de ESTRUCTURA (scripts/*.py).

La lógica vive en `src/generador/structure_scan.py`, que también usa la app: un solo código para
armar el dataset, entrenar y usar el modelo, así las features de entrenamiento y las de runtime no
pueden divergir. Este módulo solo lo expone con el nombre que ya usan los scripts.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import generador.structure_scan as _scan  # noqa: E402

# Re-exporta TODO (incluidos los nombres con guion bajo que usan los scripts: _sim, _GENERIC_FOLDERS...).
globals().update({name: value for name, value in vars(_scan).items() if not name.startswith("__")})
