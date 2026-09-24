"""Dónde se escribe cada archivo generado, relativo a la raíz de cada proyecto.

Por defecto sigue la "Estructura de Carpetas" documentada en Estandar Desarrollo Backend.md /
Interfaz de Modulo.md (`layout.STANDARD_LAYOUT`); si el proyecto tiene su propia estructura y el
desarrollador la elige, el manifiesto trae ese layout -- ver layout.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from . import layout

if TYPE_CHECKING:
    from .generator import ModuleManifest


def backend_paths(manifest: "ModuleManifest") -> dict[str, Path]:
    """Ruta de cada archivo del módulo según el layout del manifiesto (el estándar, salvo
    que el desarrollador haya elegido el del proyecto -- ver layout.py)."""
    return {role: manifest.layout.path(role, manifest.table) for role in layout.ROLES}


def frontend_paths(manifest: "ModuleManifest") -> dict[str, Path]:
    return {
        "interfaces": Path(f"src/app/interfaces/models/{manifest.modulo}.interface.ts"),
        "audit_user": Path("src/app/interfaces/shared/audit-user.interface.ts"),
    }
