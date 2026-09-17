"""Arranque del estándar ("scaffolding") para proyectos backend que todavía
no lo siguen — ver Sugerencias del informe: "Generación de scaffolding base
del estándar (fallback para proyectos que todavía no lo siguen)".

El generador de módulos (generator.py) asume que estas piezas de base ya
existen en el proyecto destino: AbstractModuleService, CrudService (con
auditoría), el Controller base con las anotaciones Swagger globales, y
RouteServiceProvider. Si un desarrollador apunta la herramienta a un
proyecto que nunca adoptó el patrón, este módulo detecta qué falta y genera
solo lo que falta — nunca sobrescribe un archivo que ya existe.

CrudService es el único caso que depende de contexto del proyecto (no es
autocontenido): necesita el prefijo de negocio (para nombrar la tabla/modelo
de auditoría `{prefijo}_procesosaudit`, completamente especificada en
Auditoría.md) y necesita saber si el proyecto ya tiene una clase `Token`
propia para resolver el usuario autenticado. Si no la tiene, se usa
`Auth::user()` nativo de Laravel (funcionalmente equivalente bajo Sanctum)
en su lugar, dejado explícito en un comentario — nunca se inventa un
formato de sesión/token, eso sí es una decisión de seguridad del proyecto.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATES_DIR = Path(__file__).parent / "templates" / "scaffold"

_TOKEN_CLASS_RE_HINT = "class Token"


@dataclass
class ScaffoldStatus:
    backend_root: Path
    abstract_module_service_path: Path
    abstract_module_service_exists: bool
    crud_service_path: Path
    crud_service_exists: bool
    base_controller_path: Path
    base_controller_exists: bool
    base_controller_has_swagger: bool
    route_service_provider_path: Path
    route_service_provider_exists: bool
    composer_json_exists: bool
    composer_has_api_toolkit: bool
    composer_has_l5_swagger: bool
    token_class_path: Path | None
    procesosaudit_migration_path: Path | None

    @property
    def token_class_found(self) -> bool:
        return self.token_class_path is not None

    @property
    def procesosaudit_migration_found(self) -> bool:
        return self.procesosaudit_migration_path is not None

    @property
    def missing_base_pieces(self) -> list[str]:
        """Piezas autocontenidas que se pueden generar sin más contexto que
        la raíz del backend (a diferencia de CrudService, ver módulo)."""
        missing = []
        if not self.abstract_module_service_exists:
            missing.append("AbstractModuleService.php")
        if not self.route_service_provider_exists:
            missing.append("RouteServiceProvider.php")
        if not self.base_controller_exists:
            missing.append("Controller.php (base)")
        return missing

    @property
    def base_controller_needs_swagger_snippet(self) -> bool:
        """El Controller base existe (caso normal — viene con el skeleton de
        Laravel) pero sin las anotaciones Swagger: no se edita solo (mismo
        criterio que el loader de rutas), se sugiere un snippet."""
        return self.base_controller_exists and not self.base_controller_has_swagger


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _find_token_class(backend_root: Path) -> Path | None:
    app_dir = backend_root / "app"
    if not app_dir.is_dir():
        return None
    for php_file in app_dir.rglob("*.php"):
        if _TOKEN_CLASS_RE_HINT in _read_text(php_file):
            return php_file
    return None


def _find_procesosaudit_migration(backend_root: Path) -> Path | None:
    migrations_dir = backend_root / "database" / "migrations"
    if not migrations_dir.is_dir():
        return None
    matches = sorted(migrations_dir.rglob("*procesosaudit*.php"))
    return matches[0] if matches else None


def detect_scaffold_status(backend_root: Path) -> ScaffoldStatus:
    abstract_module_service_path = backend_root / "app" / "Services" / "AbstractModuleService.php"
    crud_service_path = backend_root / "app" / "Services" / "CrudService.php"
    base_controller_path = backend_root / "app" / "Http" / "Controllers" / "Controller.php"
    route_service_provider_path = backend_root / "app" / "Providers" / "RouteServiceProvider.php"
    composer_json_path = backend_root / "composer.json"

    base_controller_exists = base_controller_path.exists()
    base_controller_text = _read_text(base_controller_path) if base_controller_exists else ""

    composer_json_exists = composer_json_path.exists()
    composer_text = _read_text(composer_json_path).lower() if composer_json_exists else ""

    return ScaffoldStatus(
        backend_root=backend_root,
        abstract_module_service_path=abstract_module_service_path,
        abstract_module_service_exists=abstract_module_service_path.exists(),
        crud_service_path=crud_service_path,
        crud_service_exists=crud_service_path.exists(),
        base_controller_path=base_controller_path,
        base_controller_exists=base_controller_exists,
        base_controller_has_swagger="@OA\\Info" in base_controller_text,
        route_service_provider_path=route_service_provider_path,
        route_service_provider_exists=route_service_provider_path.exists(),
        composer_json_exists=composer_json_exists,
        composer_has_api_toolkit="api-toolkit" in composer_text,
        composer_has_l5_swagger="l5-swagger" in composer_text,
        token_class_path=_find_token_class(backend_root),
        procesosaudit_migration_path=_find_procesosaudit_migration(backend_root),
    )


class ScaffoldRenderer:
    def __init__(self, templates_dir: Path | None = None) -> None:
        self.env = Environment(
            loader=FileSystemLoader(str(templates_dir or _TEMPLATES_DIR)),
            autoescape=select_autoescape(disabled_extensions=(".j2",), default=False),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

    def render_abstract_module_service(self) -> str:
        return self.env.get_template("AbstractModuleService.php.j2").render()

    def render_route_service_provider(self) -> str:
        return self.env.get_template("RouteServiceProvider.php.j2").render()

    def render_base_controller(self, project_name: str) -> str:
        return self.env.get_template("BaseController.php.j2").render(project_name=project_name)

    def render_crud_service(self, prefijo: str, *, use_token_class: bool) -> str:
        return self.env.get_template("CrudService.php.j2").render(prefijo=prefijo, use_token_class=use_token_class)

    def render_procesosaudit_model(self, prefijo: str) -> str:
        return self.env.get_template("ProcesosAuditModel.php.j2").render(prefijo=prefijo)

    def render_procesosaudit_migration(self, prefijo: str) -> str:
        return self.env.get_template("ProcesosAuditMigration.php.j2").render(prefijo=prefijo)


def procesosaudit_migration_filename(prefijo: str, *, when: datetime | None = None) -> str:
    timestamp = (when or datetime.now()).strftime("%Y_%m_%d_%H%M%S")
    return f"{timestamp}_create_{prefijo}_procesosaudit_table.php"


def write_missing_base_pieces(
    status: ScaffoldStatus,
    *,
    project_name: str,
    renderer: ScaffoldRenderer | None = None,
) -> dict[str, Path]:
    """Escribe SOLO las piezas autocontenidas que `status` reporta como
    faltantes (AbstractModuleService / RouteServiceProvider / Controller
    base) — nunca sobrescribe un archivo existente. No incluye CrudService
    ni la migración/modelo de auditoría: esos necesitan el prefijo de
    negocio, ver `write_crud_service_with_audit`."""
    # Re-chequea el filesystem acá (no solo los booleanos de `status`, que
    # pueden quedar desactualizados si el caller reusa un snapshot viejo) —
    # la garantía de "nunca sobrescribe" no debe depender de que el caller
    # siempre vuelva a llamar detect_scaffold_status() antes de escribir.
    renderer = renderer or ScaffoldRenderer()
    written: dict[str, Path] = {}

    if not status.abstract_module_service_path.exists():
        status.abstract_module_service_path.parent.mkdir(parents=True, exist_ok=True)
        status.abstract_module_service_path.write_text(
            renderer.render_abstract_module_service(), encoding="utf-8"
        )
        written["abstract_module_service"] = status.abstract_module_service_path

    if not status.route_service_provider_path.exists():
        status.route_service_provider_path.parent.mkdir(parents=True, exist_ok=True)
        status.route_service_provider_path.write_text(
            renderer.render_route_service_provider(), encoding="utf-8"
        )
        written["route_service_provider"] = status.route_service_provider_path

    if not status.base_controller_path.exists():
        status.base_controller_path.parent.mkdir(parents=True, exist_ok=True)
        status.base_controller_path.write_text(
            renderer.render_base_controller(project_name), encoding="utf-8"
        )
        written["base_controller"] = status.base_controller_path

    return written


def write_crud_service_with_audit(
    status: ScaffoldStatus,
    prefijo: str,
    *,
    renderer: ScaffoldRenderer | None = None,
) -> dict[str, Path]:
    """Genera CrudService.php siempre completo, con auditoría activa —
    nunca en una versión reducida (ver Sugerencias del informe). Si la
    migración/modelo de `{prefijo}_procesosaudit` no existen todavía, se
    generan acá mismo; si `status.token_class_found` es False, el
    CrudService generado usa Auth::user() en vez de Token::user(). Nunca
    sobrescribe un archivo que ya exista."""
    # Ver nota de write_missing_base_pieces: se re-chequea el filesystem acá,
    # no solo los booleanos de `status`.
    renderer = renderer or ScaffoldRenderer()
    written: dict[str, Path] = {}

    if not status.crud_service_path.exists():
        status.crud_service_path.parent.mkdir(parents=True, exist_ok=True)
        status.crud_service_path.write_text(
            renderer.render_crud_service(prefijo, use_token_class=status.token_class_found),
            encoding="utf-8",
        )
        written["crud_service"] = status.crud_service_path

    if _find_procesosaudit_migration(status.backend_root) is None:
        model_path = status.backend_root / "app" / "Models" / f"db{prefijo}" / f"{prefijo}_procesosaudit.php"
        if not model_path.exists():
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_text(renderer.render_procesosaudit_model(prefijo), encoding="utf-8")
            written["procesosaudit_model"] = model_path

        migration_dir = status.backend_root / "database" / "migrations" / "Auditoria"
        migration_path = migration_dir / procesosaudit_migration_filename(prefijo)
        migration_dir.mkdir(parents=True, exist_ok=True)
        migration_path.write_text(renderer.render_procesosaudit_migration(prefijo), encoding="utf-8")
        written["procesosaudit_migration"] = migration_path

    return written
