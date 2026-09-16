"""Analiza (de solo lectura) la estructura del proyecto Laravel destino antes
de generar archivos — para saber si `routes/modules/{modulo}.php` se va a
cargar solo o si hace falta wirearlo a mano.

Deliberadamente NO edita `RouteServiceProvider.php` / `bootstrap/app.php` en
automático: son archivos de boot de un proyecto real y el patrón de carga de
rutas varía entre proyectos — mejor mostrar un snippet sugerido y que el
desarrollador lo pegue, que adivinar mal y romper el arranque de la app.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

_MODULES_LOADER_MARKERS = ("routes/modules", "routes.modules")


@dataclass
class ProjectScanResult:
    backend_root: Path
    laravel_version_hint: str  # "L11+" | "L10-" | "desconocido"
    routes_modules_dir_exists: bool
    existing_module_routes: list[str]
    modules_loader_registered: bool
    provider_file_checked: Path | None
    warnings: list[str] = field(default_factory=list)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def scan_backend_project(backend_root: Path) -> ProjectScanResult:
    warnings: list[str] = []

    bootstrap_app = backend_root / "bootstrap" / "app.php"
    route_service_provider = backend_root / "app" / "Providers" / "RouteServiceProvider.php"

    if bootstrap_app.exists() and "withRouting" in _read_text(bootstrap_app):
        version_hint = "L11+"
        provider_file: Path | None = bootstrap_app
    elif route_service_provider.exists():
        version_hint = "L10-"
        provider_file = route_service_provider
    else:
        version_hint = "desconocido"
        provider_file = None
        warnings.append(
            "No se encontró bootstrap/app.php ni app/Providers/RouteServiceProvider.php "
            "— ¿es la raíz correcta del proyecto Laravel?"
        )

    routes_modules_dir = backend_root / "routes" / "modules"
    routes_modules_dir_exists = routes_modules_dir.is_dir()
    existing_module_routes = (
        sorted(p.name for p in routes_modules_dir.glob("*.php")) if routes_modules_dir_exists else []
    )

    modules_loader_registered = False
    if provider_file is not None:
        text = _read_text(provider_file)
        modules_loader_registered = any(marker in text for marker in _MODULES_LOADER_MARKERS)
        if not modules_loader_registered:
            warnings.append(
                f"No se detectó automáticamente un loader de routes/modules/*.php en {provider_file.name} "
                "— puede ser un falso negativo (esta detección busca texto literal, no ejecuta el proyecto). "
                "Si las rutas de otros módulos ya funcionan en producción, probablemente no hace falta hacer "
                "nada; si es un proyecto nuevo, agregá el snippet sugerido."
            )

    return ProjectScanResult(
        backend_root=backend_root,
        laravel_version_hint=version_hint,
        routes_modules_dir_exists=routes_modules_dir_exists,
        existing_module_routes=existing_module_routes,
        modules_loader_registered=modules_loader_registered,
        provider_file_checked=provider_file,
        warnings=warnings,
    )


def suggested_loader_snippet(version_hint: str) -> str:
    if version_hint == "L11+":
        return (
            "// bootstrap/app.php, dentro de ->withRouting(..., then: function () {\n"
            "foreach (glob(base_path('routes/modules/*.php')) as $routeFile) {\n"
            "    require $routeFile;\n"
            "}\n"
        )
    return (
        "// app/Providers/RouteServiceProvider.php, dentro de boot()/map():\n"
        "foreach (glob(base_path('routes/modules/*.php')) as $routeFile) {\n"
        "    Route::middleware('api')->prefix('api')->group($routeFile);\n"
        "}\n"
    )
