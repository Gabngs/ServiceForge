"""Dónde se escribe cada archivo generado, relativo a la raíz de cada proyecto.

Sigue la "Estructura de Carpetas" documentada en Estandar Desarrollo Backend.md /
Interfaz de Modulo.md — el generador no inventa su propio layout, escribe donde
un desarrollador humano ya escribiría estos archivos a mano.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .generator import ModuleManifest


def backend_paths(manifest: "ModuleManifest") -> dict[str, Path]:
    modulo = manifest.modulo_studly
    prefijo = manifest.prefijo_studly
    return {
        "model": Path(f"app/Models/db{manifest.prefijo}/{manifest.model_class}.php"),
        "service": Path(f"app/Services/{modulo}Service.php"),
        "filters": Path(f"app/Filters/{manifest.model_class}Filters.php"),
        "store_request": Path(f"app/Http/Requests/{prefijo}/{modulo}/Store{modulo}Request.php"),
        "update_request": Path(f"app/Http/Requests/{prefijo}/{modulo}/Update{modulo}Request.php"),
        "trait": Path(f"app/Http/Requests/{prefijo}/Traits/{modulo}/Validates{modulo}.php"),
        "controller": Path(f"app/Http/Controllers/Api/{prefijo}/{manifest.model_class}Controller.php"),
        "routes_module": Path(f"routes/modules/{manifest.modulo}.php"),
    }


def frontend_paths(manifest: "ModuleManifest") -> dict[str, Path]:
    return {
        "interfaces": Path(f"src/app/interfaces/models/{manifest.modulo}.interface.ts"),
        "audit_user": Path("src/app/interfaces/shared/audit-user.interface.ts"),
    }
