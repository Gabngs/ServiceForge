"""Arma el manifiesto de un módulo a partir del análisis de columnas/relaciones
y renderiza el patrón de servicio completo: Model, Service, Filters,
Store/Update Request + Trait, Resource/RelationResource/TinyResource (con sus
anotaciones @OA\\Schema), Controller (con anotaciones @OA\\... por método) +
ruta, y el set de interfaces TypeScript del frontend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import mapping, naming, paths
from .db import Column
from .fk_resolver import FkResolution

_TEMPLATES_DIR = Path(__file__).parent / "templates"

DEFAULT_USER_MODEL_CLASS = "App\\Models\\User"


@dataclass
class ManifestField:
    name: str  # nombre de columna
    parsed: mapping.ParsedType
    nullable: bool
    include: bool  # incluir en fillable / interfaces (checkbox "incluir")
    tiny: bool  # incluir en I{Modulo}Tiny
    is_fk: bool = False
    fk_table: str | None = None
    store_rule: str = ""
    update_rule: str = ""
    store_rule_final: str = ""  # store_rule + unique:... si el campo tiene índice único
    update_rule_final: str = ""  # update_rule + unique:...,{$modelId},pkid si aplica
    is_unique: bool = False
    cast: str | None = None

    @property
    def relation_method(self) -> str | None:
        """Nombre del método belongsTo. La convención `{campo}_id` -> `{campo}`
        asume que la columna termina en `_id`, pero una FK asignada a mano
        (ver GUI: combo "FK -> tabla" en cualquier columna) puede no seguir
        esa convención -- en ese caso el método usa el nombre de columna tal
        cual, en vez de cortar mal los últimos 3 caracteres."""
        if not self.is_fk:
            return None
        if self.name.endswith("_id") and self.name != "_id":
            return self.name[: -len("_id")]
        return self.name

    @property
    def fk_related_modulo_studly(self) -> str | None:
        if not self.fk_table:
            return None
        _, modulo = naming.split_prefijo_modulo(self.fk_table)
        return naming.studly(modulo)

    @property
    def fk_related_modulo_snake(self) -> str | None:
        if not self.fk_table:
            return None
        _, modulo = naming.split_prefijo_modulo(self.fk_table)
        return modulo

    @property
    def fk_table_prefijo(self) -> str | None:
        """Prefijo (lowercase, `db{prefijo}` de namespace) de la tabla relacionada —
        puede ser distinto del prefijo del propio módulo (FK cruzando prefijos)."""
        if not self.fk_table:
            return None
        prefijo, _ = naming.split_prefijo_modulo(self.fk_table)
        return prefijo

    @property
    def fk_table_prefijo_studly(self) -> str | None:
        """Namespace `App\\Http\\Resources\\{Prefijo}` de la tabla relacionada."""
        if not self.fk_table_prefijo:
            return None
        return naming.studly(self.fk_table_prefijo)

    @property
    def is_required_on_store(self) -> bool:
        return self.store_rule.startswith("required")

    def ts_type_full(self) -> str:
        """Tipo TS en I{Modulo} — si es FK cargada, la Tiny de la entidad relacionada."""
        if self.is_fk and self.fk_related_modulo_studly:
            return f"I{self.fk_related_modulo_studly}Tiny | null"
        return mapping.ts_type(self.parsed)

    def ts_type_create(self) -> str:
        """Tipo TS en Create/Update — si es FK, el UUID plano que manda el front."""
        return mapping.ts_type(self.parsed, is_fk=self.is_fk)

    def oa_type(self) -> str:
        """Tipo OpenAPI (`@OA\\Property(type=...)`) — ver Documentación Swagger (OpenAPI).md."""
        return mapping.oa_type(self.parsed)

    def oa_format(self) -> str | None:
        return mapping.oa_format(self.parsed)

    def oa_max_length(self) -> int | None:
        if self.parsed.base in ("varchar", "char") and self.parsed.length:
            return self.parsed.length
        return None


@dataclass
class ManifestRelation:
    column: str
    method: str
    model_class: str  # clase del Model relacionado (nombre literal de tabla, ver naming.model_class_name)
    fk_table_prefijo: str  # prefijo (namespace App\Models\db{prefijo}) de la tabla relacionada


@dataclass
class ModuleManifest:
    table: str
    prefijo: str
    modulo: str  # snake_case, puede tener guiones bajos internos
    modulo_studly: str  # StudlyCase, para nombres de clase
    connection_name: str
    fields: list[ManifestField]
    relations: list[ManifestRelation]
    user_model_class: str = DEFAULT_USER_MODEL_CLASS
    unique_indexes: dict[str, list[str]] = field(default_factory=dict)

    @property
    def model_class(self) -> str:
        return naming.model_class_name(self.table)

    @property
    def prefijo_studly(self) -> str:
        return naming.studly(self.prefijo)

    @property
    def user_model_namespace(self) -> str:
        """`App\\Models\\User` -> `App\\Models`. Usado para decidir si hace
        falta un `use` para el modelo de usuario, o si ya cae en el mismo
        namespace que este Model (ver `Model.php.j2` — importar una clase
        que ya está en el namespace actual es un fatal error de PHP, no un
        warning: "Cannot use X as X because the name is already in use")."""
        return self.user_model_class.rsplit("\\", 1)[0] if "\\" in self.user_model_class else ""

    @property
    def user_model_short_class(self) -> str:
        return self.user_model_class.rsplit("\\", 1)[-1]

    @property
    def user_model_needs_import(self) -> bool:
        return self.user_model_namespace != "" and self.user_model_namespace != f"App\\Models\\db{self.prefijo}"


def build_manifest(
    table: str,
    columns: list[Column],
    *,
    fk_resolutions: dict[str, FkResolution],
    unique_indexes: dict[str, list[str]],
    included_fields: set[str] | None = None,
    tiny_fields: set[str] | None = None,
    connection_name: str = "mysql",
    user_model_class: str = DEFAULT_USER_MODEL_CLASS,
) -> ModuleManifest:
    prefijo, modulo = naming.split_prefijo_modulo(table)
    modulo_studly = naming.studly(modulo)

    # Columnas con índice único de una sola columna -> el ignore del `unique`
    # en Update va contra pkid (ver Model.md#Regla: pkid vs id como PK).
    unique_single_fields = {cols[0] for cols in unique_indexes.values() if len(cols) == 1}

    fields: list[ManifestField] = []
    relations: list[ManifestRelation] = []

    for column in columns:
        if column.name in mapping.EXCLUDED_FIELDS:
            continue

        parsed = mapping.parse_sql_type(column.sql_type)
        resolution = fk_resolutions.get(column.name)
        is_fk = bool(resolution and resolution.table)
        fk_table = resolution.table if is_fk else None

        include = included_fields is None or column.name in included_fields
        tiny = tiny_fields is not None and column.name in tiny_fields
        is_unique = column.name in unique_single_fields

        store_rule, update_rule = mapping.validation_rules(
            parsed, column.nullable, is_fk=is_fk, fk_table=fk_table
        )

        store_rule_final = store_rule
        update_rule_final = update_rule
        if is_unique and not is_fk:
            store_rule_final = f"{store_rule}|unique:{table},{column.name}"
            update_rule_final = f"{update_rule}|unique:{table},{column.name},{{$modelId}},pkid"

        manifest_field = ManifestField(
            name=column.name,
            parsed=parsed,
            nullable=column.nullable,
            include=include,
            tiny=tiny,
            is_fk=is_fk,
            fk_table=fk_table,
            store_rule=store_rule,
            update_rule=update_rule,
            store_rule_final=store_rule_final,
            update_rule_final=update_rule_final,
            is_unique=is_unique,
            cast=mapping.laravel_cast(parsed),
        )
        fields.append(manifest_field)

        if is_fk and fk_table:
            fk_prefijo, _ = naming.split_prefijo_modulo(fk_table)
            relations.append(
                ManifestRelation(
                    column=column.name,
                    method=manifest_field.relation_method or fk_table,
                    model_class=naming.model_class_name(fk_table),
                    fk_table_prefijo=fk_prefijo,
                )
            )

    return ModuleManifest(
        table=table,
        prefijo=prefijo,
        modulo=modulo,
        modulo_studly=modulo_studly,
        connection_name=connection_name,
        fields=fields,
        relations=relations,
        user_model_class=user_model_class,
        unique_indexes=unique_indexes,
    )


class Renderer:
    def __init__(self, templates_dir: Path | None = None) -> None:
        self.env = Environment(
            loader=FileSystemLoader(str(templates_dir or _TEMPLATES_DIR)),
            autoescape=select_autoescape(disabled_extensions=(".j2",), default=False),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

    def _included(self, manifest: ModuleManifest) -> list[ManifestField]:
        return [f for f in manifest.fields if f.include]

    def render_model_php(self, manifest: ModuleManifest) -> str:
        included = self._included(manifest)
        casts = [(f.name, f.cast) for f in included if f.cast]
        # Import solo para relaciones que cruzan de prefijo -- una del MISMO
        # prefijo que este Model ya resuelve el nombre corto por estar en el
        # mismo namespace (App\Models\db{prefijo}); importarla igual sería un
        # fatal error de PHP ("already in use"), no un problema cosmético.
        cross_prefix_imports = sorted(
            {
                (rel.fk_table_prefijo, rel.model_class)
                for rel in manifest.relations
                if rel.fk_table_prefijo != manifest.prefijo
            }
        )
        return self.env.get_template("Model.php.j2").render(
            manifest=manifest,
            fields=included,
            casts=casts,
            relations=manifest.relations,
            cross_prefix_imports=cross_prefix_imports,
        )

    def render_service_php(self, manifest: ModuleManifest) -> str:
        included = self._included(manifest)
        # Service.php vive en el namespace App\Services -- distinto del
        # árbol App\Models\db*, así que acá SIEMPRE se puede importar (nunca
        # hay riesgo de "already in use" por namespace), salvo el caso
        # degenerado de una FK autorreferencial (ej. parent_id -> la misma
        # tabla, posible ahora que el combo "FK -> tabla" de la GUI permite
        # asignar cualquier columna a cualquier tabla) -- ese caso ya está
        # importado por la línea de arriba (el propio modelo del módulo), y
        # un `use` duplicado de la misma clase es un fatal error de PHP.
        own = (manifest.prefijo, manifest.model_class)
        relation_imports = sorted(
            {(rel.fk_table_prefijo, rel.model_class) for rel in manifest.relations} - {own}
        )
        return self.env.get_template("Service.php.j2").render(
            manifest=manifest, fields=included, relations=manifest.relations, relation_imports=relation_imports
        )

    def render_filters_php(self, manifest: ModuleManifest) -> str:
        non_fk = self._non_fk_fields(manifest)
        search_fields = [f for f in non_fk if mapping.is_searchable(f.parsed)]
        return self.env.get_template("Filters.php.j2").render(
            manifest=manifest,
            # $allowedFilters / $allowedSorts: SOLO columnas directas -- un FK
            # que guarda pkid nunca va acá (ver useFilters.md#FKs que guardan
            # pkid). Dejarlo también en $allowedFilters duplica el WHERE: el
            # método resolver ya filtra por pkid, y el pipeline genérico de
            # QueryFilters agrega ADEMÁS "WHERE columna = <uuid crudo>" contra
            # una columna entera -- esa segunda condición nunca matchea, y al
            # ir en AND con la primera, el resultado final es siempre vacío.
            fields=non_fk,
            relations=manifest.relations,
            search_fields=search_fields,
            fk_fields=self._fk_fields(manifest),
            fk_model_imports=self._fk_model_imports(manifest),
        )

    def _fk_fields(self, manifest: ModuleManifest) -> list[ManifestField]:
        return [f for f in self._included(manifest) if f.is_fk]

    def _fk_model_imports(self, manifest: ModuleManifest) -> list[tuple[str, str]]:
        return sorted(
            {
                (f.fk_table_prefijo, f.fk_table)
                for f in self._fk_fields(manifest)
                if f.fk_table_prefijo and f.fk_table
            }
        )

    def _non_fk_fields(self, manifest: ModuleManifest) -> list[ManifestField]:
        return [f for f in self._included(manifest) if not f.is_fk]

    def _tiny_fields(self, manifest: ModuleManifest) -> list[ManifestField]:
        """Campos mínimos — comparten selección con I{Modulo}Tiny (ver interfaces.ts.j2)
        y con {Modulo}RelationResource/{Modulo}TinyResource (ver ApiResponse.md#Resource
        triple: completo, relación y tiny)."""
        return [f for f in self._included(manifest) if f.tiny]

    def _fk_resource_imports(self, manifest: ModuleManifest) -> list[tuple[str, str]]:
        return sorted(
            {
                (f.fk_table_prefijo_studly, f.fk_related_modulo_studly)
                for f in self._fk_fields(manifest)
                if f.fk_table_prefijo_studly and f.fk_related_modulo_studly
            }
        )

    def render_store_request_php(self, manifest: ModuleManifest) -> str:
        non_fk = self._non_fk_fields(manifest)
        return self.env.get_template("StoreRequest.php.j2").render(
            manifest=manifest,
            non_fk_fields=non_fk,
            required_fields=[f for f in non_fk if f.is_required_on_store],
            unique_fields=[f for f in non_fk if f.is_unique],
        )

    def render_update_request_php(self, manifest: ModuleManifest) -> str:
        non_fk = self._non_fk_fields(manifest)
        return self.env.get_template("UpdateRequest.php.j2").render(
            manifest=manifest,
            non_fk_fields=non_fk,
            unique_fields=[f for f in non_fk if f.is_unique],
        )

    def render_trait_php(self, manifest: ModuleManifest) -> str:
        return self.env.get_template("ValidatesTrait.php.j2").render(
            manifest=manifest, fk_fields=self._fk_fields(manifest)
        )

    def render_resource_php(self, manifest: ModuleManifest) -> str:
        included = self._included(manifest)
        return self.env.get_template("Resource.php.j2").render(
            manifest=manifest, fields=included, fk_imports=self._fk_resource_imports(manifest)
        )

    def render_relation_resource_php(self, manifest: ModuleManifest) -> str:
        return self.env.get_template("RelationResource.php.j2").render(
            manifest=manifest, relation_fields=self._tiny_fields(manifest)
        )

    def render_tiny_resource_php(self, manifest: ModuleManifest) -> str:
        return self.env.get_template("TinyResource.php.j2").render(
            manifest=manifest, tiny_fields=self._tiny_fields(manifest)
        )

    def render_controller_php(self, manifest: ModuleManifest) -> str:
        included = self._included(manifest)
        return self.env.get_template("Controller.php.j2").render(
            manifest=manifest,
            fields=included,
            required_fields=[f for f in included if f.is_required_on_store],
        )

    def render_routes_module_php(self, manifest: ModuleManifest) -> str:
        return self.env.get_template("routes_module.php.j2").render(manifest=manifest)

    def render_interfaces_ts(self, manifest: ModuleManifest) -> str:
        included = self._included(manifest)
        fk_imports = sorted(
            {
                (f.fk_related_modulo_studly, f.fk_related_modulo_snake)
                for f in included
                if f.is_fk and f.fk_related_modulo_studly
            }
        )
        return self.env.get_template("interfaces.ts.j2").render(
            manifest=manifest, fields=included, fk_imports=fk_imports
        )

    def audit_user_interface_ts(self) -> str:
        return self.env.get_template("audit-user.interface.ts.j2").render()


BACKEND_KEYS = (
    "model",
    "service",
    "filters",
    "store_request",
    "update_request",
    "trait",
    "resource",
    "relation_resource",
    "tiny_resource",
    "controller",
    "routes_module",
)
FRONTEND_KEYS = ("interfaces", "audit_user")


def render_all(manifest: ModuleManifest, *, renderer: Renderer | None = None) -> dict[str, str]:
    """Renderiza todo el patrón a texto, sin tocar el filesystem.

    Este es el contenido que puebla el preview editable de la GUI — lo que
    termine escrito en disco es lo que esté en el editor al momento de
    confirmar, no necesariamente este render "de fábrica" (ver GUI: el
    desarrollador puede corregir el preview antes de generar).
    """
    renderer = renderer or Renderer()
    return {
        "model": renderer.render_model_php(manifest),
        "service": renderer.render_service_php(manifest),
        "filters": renderer.render_filters_php(manifest),
        "store_request": renderer.render_store_request_php(manifest),
        "update_request": renderer.render_update_request_php(manifest),
        "trait": renderer.render_trait_php(manifest),
        "resource": renderer.render_resource_php(manifest),
        "relation_resource": renderer.render_relation_resource_php(manifest),
        "tiny_resource": renderer.render_tiny_resource_php(manifest),
        "controller": renderer.render_controller_php(manifest),
        "routes_module": renderer.render_routes_module_php(manifest),
        "interfaces": renderer.render_interfaces_ts(manifest),
        "audit_user": renderer.audit_user_interface_ts(),
    }


def write_files(
    manifest: ModuleManifest,
    backend_root: Path,
    frontend_root: Path,
    contents: dict[str, str],
    *,
    write_audit_interface: bool = False,
) -> dict[str, Path]:
    """Escribe `contents` (ya renderizado, potencialmente editado a mano) en la
    estructura de carpetas del proyecto real — ver paths.py para el layout.

    `backend_root` / `frontend_root` son la raíz de cada proyecto (donde vive
    `app/` o `src/`), no una carpeta de salida plana. `write_audit_interface`
    está en False por default: el programa normalmente se usa sobre un
    proyecto que ya existe y que ya tiene su propio `audit-user.interface.ts`
    compartido — activarlo solo hace falta la primera vez que se arranca un
    proyecto desde cero. Nunca sobreescribe ese archivo si ya existe.
    Retorna un dict {tipo_archivo: ruta_escrita}.
    """
    backend_files = paths.backend_paths(manifest)
    frontend_files = paths.frontend_paths(manifest)

    written: dict[str, Path] = {}

    for key in BACKEND_KEYS:
        if key not in contents:
            continue
        target = backend_root / backend_files[key]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents[key], encoding="utf-8")
        written[key] = target

    if "interfaces" in contents:
        target = frontend_root / frontend_files["interfaces"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents["interfaces"], encoding="utf-8")
        written["interfaces"] = target

    if write_audit_interface and "audit_user" in contents:
        target = frontend_root / frontend_files["audit_user"]
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(contents["audit_user"], encoding="utf-8")
            written["audit_user"] = target

    return written


def generate_files(
    manifest: ModuleManifest,
    backend_root: Path,
    frontend_root: Path,
    *,
    write_audit_interface: bool = False,
    renderer: Renderer | None = None,
) -> dict[str, Path]:
    """Atajo: renderiza todo de cero (sin edición manual) y lo escribe. Ver
    `render_all` + `write_files` para el flujo que usa la GUI (preview editable)."""
    renderer = renderer or Renderer()
    contents = render_all(manifest, renderer=renderer)
    return write_files(
        manifest, backend_root, frontend_root, contents, write_audit_interface=write_audit_interface
    )
