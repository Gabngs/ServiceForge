from generador.db import Column
from generador.fk_resolver import FkResolution
from generador.generator import (
    Renderer,
    build_manifest,
    existing_target_files,
    generate_files,
    render_all,
    strip_line_comments,
    write_files,
)
from generador.paths import backend_paths


def _siaw_usuarios_columns() -> list[Column]:
    # Caso guía del documento: tabla siaw_usuarios con FK rol_id -> siaw_roles
    return [
        Column("pkid", "int", nullable=False, key="", default=None, extra="auto_increment"),
        Column("id", "varchar(36)", nullable=False, key="PRI", default=None, extra=""),
        Column("nombre", "varchar(100)", nullable=False, key="", default=None, extra=""),
        Column("email", "varchar(150)", nullable=False, key="UNI", default=None, extra=""),
        Column("rol_id", "int", nullable=False, key="MUL", default=None, extra=""),
        Column("activo", "tinyint(1)", nullable=True, key="", default="1", extra=""),
        Column("created_at", "timestamp", nullable=True, key="", default=None, extra=""),
        Column("updated_at", "timestamp", nullable=True, key="", default=None, extra=""),
        Column("deleted_at", "timestamp", nullable=True, key="", default=None, extra=""),
        Column("created_by_id", "int", nullable=True, key="", default=None, extra=""),
        Column("updated_by_id", "int", nullable=True, key="", default=None, extra=""),
        Column("deleted_by_id", "int", nullable=True, key="", default=None, extra=""),
    ]


def _build_test_manifest(columns=None, **overrides):
    columns = columns if columns is not None else _siaw_usuarios_columns()
    fk_resolutions = {
        "rol_id": FkResolution(
            column="rol_id", base_name="rol", candidates=["siaw_roles"], status="auto", table="siaw_roles"
        )
    }
    included = {"nombre", "email", "rol_id", "activo"}
    tiny = {"nombre"}
    kwargs = dict(
        fk_resolutions=fk_resolutions,
        unique_indexes={"email_unique": ["email"]},
        included_fields=included,
        tiny_fields=tiny,
        relation_fields=tiny,  # mismo criterio que tiny por default en estos tests
        connection_name="mysql_dbmdt_siaw",
    )
    kwargs.update(overrides)
    return build_manifest("siaw_usuarios", columns, **kwargs)


def test_build_manifest_excludes_audit_and_pk_fields():
    manifest = _build_test_manifest()
    field_names = {f.name for f in manifest.fields}
    assert field_names == {"nombre", "email", "rol_id", "activo"}


def test_build_manifest_naming():
    manifest = _build_test_manifest()
    assert manifest.prefijo == "siaw"
    assert manifest.prefijo_studly == "Siaw"
    assert manifest.modulo == "usuarios"
    assert manifest.modulo_studly == "Usuarios"
    assert manifest.model_class == "siaw_usuarios"


def test_build_manifest_relation_detected():
    """El método belongsTo usa el nombre LITERAL de la tabla relacionada (ver
    Model.md#Relaciones), no una abreviatura derivada de la columna -- la
    clave pública corta ("rol") queda en relation_alias, para el Resource."""
    manifest = _build_test_manifest()
    assert len(manifest.relations) == 1
    relation = manifest.relations[0]
    assert relation.column == "rol_id"
    assert relation.method == "siaw_roles"
    assert relation.model_class == "siaw_roles"

    rol_field = next(f for f in manifest.fields if f.name == "rol_id")
    assert rol_field.relation_method == "siaw_roles"
    assert rol_field.relation_alias == "roles"  # modulo de "siaw_roles"


def test_build_manifest_default_soft_delete_column_is_none():
    # Caso normal: la tabla usa 'deleted_at' -- no hace falta declarar nada
    # de más en el Model, SoftDeletes ya asume ese nombre.
    manifest = _build_test_manifest()
    assert manifest.soft_delete_column is None


def test_build_manifest_detects_legacy_deleted_column():
    """Tabla legada con 'deleted' en vez de 'deleted_at' -- sin esto, el
    Model generado usa SoftDeletes asumiendo 'deleted_at' y rompe contra una
    columna que no existe (ver Model.php.j2 / mapping.soft_delete_column)."""
    columns = [c for c in _siaw_usuarios_columns() if c.name != "deleted_at"]
    columns.append(Column("deleted", "tinyint(1)", nullable=True, key="", default="0", extra=""))

    manifest = _build_test_manifest(columns=columns)

    assert manifest.soft_delete_column == "deleted"
    # 'deleted' nunca es un campo de negocio (ni fillable ni validación),
    # igual que 'deleted_at' en el caso normal.
    assert "deleted" not in {f.name for f in manifest.fields}


def test_render_model_php_declares_deleted_at_const_for_legacy_column():
    columns = [c for c in _siaw_usuarios_columns() if c.name != "deleted_at"]
    columns.append(Column("deleted", "tinyint(1)", nullable=True, key="", default="0", extra=""))
    manifest = _build_test_manifest(columns=columns)

    php = Renderer().render_model_php(manifest)

    assert "const DELETED_AT = 'deleted';" in php


def test_render_model_php_omits_deleted_at_const_for_normal_table():
    manifest = _build_test_manifest()
    php = Renderer().render_model_php(manifest)
    assert "const DELETED_AT" not in php


def test_build_manifest_relation_method_for_manually_assigned_non_id_column():
    """Una FK asignada a mano (combo 'FK -> tabla' en la GUI, ver gui.py
    _on_fk_combo_changed) puede vivir en una columna que no termina en
    '_id' -- la detección automática (fk_resolver.find_fk_candidates) exige
    ese sufijo, pero el combo permite asignar cualquier columna igual. El
    método sigue siendo el nombre literal de la tabla relacionada, sin
    importar cómo se llame la columna que guarda la FK."""
    columns = [
        Column("pkid", "int", nullable=False, key="", default=None, extra="auto_increment"),
        Column("id", "varchar(36)", nullable=False, key="PRI", default=None, extra=""),
        Column("nombre", "varchar(100)", nullable=False, key="", default=None, extra=""),
        Column("tienda", "int", nullable=False, key="MUL", default=None, extra=""),  # sin sufijo _id
    ]
    fk_resolutions = {
        "tienda": FkResolution(
            column="tienda", base_name="tienda", candidates=["catalogo_tienda"], status="manual", table="catalogo_tienda"
        )
    }
    manifest = build_manifest(
        "siaw_productos",
        columns,
        fk_resolutions=fk_resolutions,
        unique_indexes={},
        included_fields={"nombre", "tienda"},
        tiny_fields=set(),
    )
    tienda_field = next(f for f in manifest.fields if f.name == "tienda")
    assert tienda_field.is_fk is True
    assert tienda_field.relation_method == "catalogo_tienda"
    assert tienda_field.relation_alias == "tienda"

    php = Renderer().render_model_php(manifest)
    assert "public function catalogo_tienda(): BelongsTo" in php
    assert "return $this->belongsTo(catalogo_tienda::class, 'tienda', 'pkid');" in php


def test_build_manifest_relation_method_falls_back_on_same_table_collision():
    """Dos columnas del mismo módulo apuntando a la MISMA tabla (ej. tienda
    de origen/destino) no pueden compartir el nombre literal de la tabla como
    método -- ahí sí se cae al nombre derivado de columna (único disponible)."""
    columns = [
        Column("pkid", "int", nullable=False, key="", default=None, extra="auto_increment"),
        Column("id", "varchar(36)", nullable=False, key="PRI", default=None, extra=""),
        Column("tienda_origen_id", "int", nullable=False, key="MUL", default=None, extra=""),
        Column("tienda_destino_id", "int", nullable=False, key="MUL", default=None, extra=""),
    ]
    fk_resolutions = {
        "tienda_origen_id": FkResolution(
            column="tienda_origen_id", base_name="tienda_origen", candidates=["catalogo_tienda"],
            status="manual", table="catalogo_tienda",
        ),
        "tienda_destino_id": FkResolution(
            column="tienda_destino_id", base_name="tienda_destino", candidates=["catalogo_tienda"],
            status="manual", table="catalogo_tienda",
        ),
    }
    manifest = build_manifest(
        "siaw_traspasos",
        columns,
        fk_resolutions=fk_resolutions,
        unique_indexes={},
        included_fields={"tienda_origen_id", "tienda_destino_id"},
        tiny_fields=set(),
    )
    origen = next(f for f in manifest.fields if f.name == "tienda_origen_id")
    destino = next(f for f in manifest.fields if f.name == "tienda_destino_id")
    assert origen.relation_method == "tienda_origen"
    assert destino.relation_method == "tienda_destino"
    assert {r.method for r in manifest.relations} == {"tienda_origen", "tienda_destino"}


def test_build_manifest_unique_field_gets_unique_rule():
    manifest = _build_test_manifest()
    email_field = next(f for f in manifest.fields if f.name == "email")
    assert email_field.is_unique is True
    assert email_field.store_rule_final == "required|string|max:150|unique:siaw_usuarios,email"
    assert email_field.update_rule_final == (
        "sometimes|string|max:150|unique:siaw_usuarios,email,{$modelId},pkid"
    )


def test_build_manifest_non_unique_field_rule_unchanged():
    manifest = _build_test_manifest()
    nombre_field = next(f for f in manifest.fields if f.name == "nombre")
    assert nombre_field.is_unique is False
    assert nombre_field.store_rule_final == nombre_field.store_rule


def test_build_manifest_default_user_model():
    manifest = _build_test_manifest()
    assert manifest.user_model_class == "App\\Models\\User"


def test_build_manifest_custom_user_model():
    manifest = _build_test_manifest(user_model_class="App\\Models\\dbcore\\core_usuarios")
    assert manifest.user_model_class == "App\\Models\\dbcore\\core_usuarios"


def test_render_model_php_contains_belongs_to():
    manifest = _build_test_manifest()
    php = Renderer().render_model_php(manifest)
    assert "class siaw_usuarios extends Model" in php
    assert "public function siaw_roles(): BelongsTo" in php
    # rol_id -> siaw_roles: MISMO prefijo (siaw) que este propio Model --
    # nombre corto sin `use`, importarlo sería fatal error de PHP
    # ("already in use", ver Model.php.j2 / generator.py).
    assert "return $this->belongsTo(siaw_roles::class, 'rol_id', 'pkid');" in php
    assert "use App\\Models\\dbsiaw\\siaw_roles;" not in php
    assert "'activo' => 'boolean'" in php
    assert "'pkid'" not in php.split("$fillable")[1].split("];")[0]  # nunca en fillable


def test_render_model_php_imports_cross_prefix_relation():
    """rol_id -> catalogo_roles (prefijo "catalogo", distinto del propio
    módulo "siaw") sí necesita `use` — el nombre corto solo no resuelve
    porque la clase vive en un namespace distinto (App\\Models\\dbcatalogo)."""
    manifest = _build_test_manifest(
        fk_resolutions={
            "rol_id": FkResolution(
                column="rol_id", base_name="rol", candidates=["catalogo_roles"], status="auto", table="catalogo_roles"
            )
        }
    )
    php = Renderer().render_model_php(manifest)
    assert "use App\\Models\\dbcatalogo\\catalogo_roles;" in php
    assert "return $this->belongsTo(catalogo_roles::class, 'rol_id', 'pkid');" in php


def test_render_model_php_contains_audit_relations():
    manifest = _build_test_manifest()
    php = Renderer().render_model_php(manifest)
    assert "use App\\Models\\User;" in php
    for method, column in [("created_by", "created_by_id"), ("updated_by", "updated_by_id"), ("deleted_by", "deleted_by_id")]:
        assert f"public function {method}(): BelongsTo" in php
        assert f"return $this->belongsTo(User::class, '{column}', 'pkid');" in php


def test_render_model_php_user_model_same_prefix_skips_import():
    """Si el modelo de usuario configurado vive en el MISMO db{prefijo} que
    el módulo generado, no se importa (sería fatal error) -- se referencia
    directo por nombre corto, igual que una relación de negocio del mismo
    prefijo."""
    manifest = _build_test_manifest(user_model_class="App\\Models\\dbsiaw\\siaw_usuarios_admin")
    php = Renderer().render_model_php(manifest)
    assert "use App\\Models\\dbsiaw\\siaw_usuarios_admin;" not in php
    assert "return $this->belongsTo(siaw_usuarios_admin::class, 'created_by_id', 'pkid');" in php


def test_render_service_php_uses_english_method_names():
    manifest = _build_test_manifest()
    php = Renderer().render_service_php(manifest)
    assert "class UsuariosService extends AbstractModuleService" in php
    for method in ("index", "show", "store", "update", "destroy"):
        assert f"function {method}(" in php
    assert "'siaw_roles'," in php  # en RELATIONS -- nombre literal de la tabla, ver Model.md#Relaciones
    assert "'created_by', 'updated_by', 'deleted_by'" in php
    assert "use App\\Models\\dbsiaw\\siaw_roles;" in php
    assert "'rol_id' => siaw_roles::class," in php
    assert "\\App\\Models\\dbsiaw\\siaw_roles::class" not in php


def test_render_service_php_imports_cross_prefix_relation():
    manifest = _build_test_manifest(
        fk_resolutions={
            "rol_id": FkResolution(
                column="rol_id", base_name="rol", candidates=["catalogo_roles"], status="auto", table="catalogo_roles"
            )
        }
    )
    php = Renderer().render_service_php(manifest)
    assert "use App\\Models\\dbcatalogo\\catalogo_roles;" in php
    assert "'rol_id' => catalogo_roles::class," in php


def test_render_filters_php():
    manifest = _build_test_manifest()
    php = Renderer().render_filters_php(manifest)
    assert "class siaw_usuariosFilters extends QueryFilters" in php
    search_block = php.split("protected array $columnSearch = [")[1].split("];")[0]
    assert "'nombre'," in search_block
    assert "'email'," in search_block  # varchar -> texto libre, elegible para LIKE
    assert "'siaw_roles'," in php.split("$allowedIncludes")[1].split("];")[0]

    # $allowedFilters / $allowedSorts: solo columnas directas -- rol_id (FK)
    # NUNCA va acá, tiene su propio método resolver (ver test de abajo). Si
    # quedara acá también, QueryFilters aplicaría el WHERE genérico (UUID
    # crudo contra la columna entera) en AND con el del método, y el
    # resultado sería siempre vacío -- ver useFilters.md#FKs que guardan pkid.
    allowed_filters_block = php.split("protected array $allowedFilters = [")[1].split("];")[0]
    allowed_sorts_block = php.split("protected array $allowedSorts = [")[1].split("];")[0]
    for field_name in ("nombre", "email", "activo"):
        assert f"'{field_name}'," in allowed_filters_block
        assert f"'{field_name}'," in allowed_sorts_block
    assert "'rol_id'," not in allowed_filters_block
    assert "'rol_id'," not in allowed_sorts_block


def test_render_filters_php_generates_fk_resolution_method():
    manifest = _build_test_manifest()
    php = Renderer().render_filters_php(manifest)
    # Import arriba + nombre corto en el método (nunca FQCN inline) -- así lo
    # documenta el estándar (ver useFilters.md, ejemplo AghTareasLimpiezaFilters).
    assert "use App\\Models\\dbsiaw\\siaw_roles;" in php
    assert "public function rol_id($value)" in php
    assert "\\App\\Models\\dbsiaw\\siaw_roles::where" not in php
    assert "siaw_roles::where('id', $value)->value('pkid');" in php
    # Si el UUID no resuelve, forzar pkid a 0 -- nunca whereNull, que traería
    # las filas con la FK nula (ver useFilters.md#FKs que guardan pkid)
    assert "return $this->builder->where('rol_id', $pkid ?? 0);" in php
    assert "whereNull('rol_id')" not in php


def test_render_store_request_php():
    manifest = _build_test_manifest()
    php = Renderer().render_store_request_php(manifest)
    assert "class StoreUsuariosRequest extends FormRequest" in php
    assert "use ValidatesUsuarios;" in php
    assert "'email' => 'required|string|max:150|unique:siaw_usuarios,email'," in php
    assert "'nombre' => 'required|string|max:100'," in php
    assert "rol_id" not in php.split("public function rules")[1].split("public function messages")[0]
    assert "getRelacionesRules()" in php


def test_render_update_request_php():
    manifest = _build_test_manifest()
    php = Renderer().render_update_request_php(manifest)
    assert "class UpdateUsuariosRequest extends FormRequest" in php
    assert "$this->route('siaw_usuarios')?->pkid;" in php
    assert '"sometimes|string|max:150|unique:siaw_usuarios,email,{$modelId},pkid",' in php
    assert "getRelacionesRules(forUpdate: true)" in php


def test_render_trait_php():
    manifest = _build_test_manifest()
    php = Renderer().render_trait_php(manifest)
    assert "trait ValidatesUsuarios" in php
    assert '"{$prefix}rol_id" => "required|string|exists:siaw_roles,id",' in php
    assert '"{$prefix}rol_id" => "sometimes|string|exists:siaw_roles,id",' in php
    assert "function getRelacionesRules(string $prefix = '', bool $forUpdate = false)" in php


def test_render_controller_php():
    manifest = _build_test_manifest()
    php = Renderer().render_controller_php(manifest)
    assert "class siaw_usuariosController extends Controller" in php
    assert "public function __construct(protected UsuariosService $service)" in php
    assert "$request->boolean('tiny')" in php
    assert "UsuariosTinyResource::class" in php  # ?tiny=true usa Tiny, no Relation (ver Controller.md)
    assert "UsuariosResource::class" in php
    assert "function show(siaw_usuarios $siaw_usuarios)" in php
    assert "function destroy(siaw_usuarios $siaw_usuarios)" in php


def test_render_controller_php_without_pagination_support():
    """Módulo configurado sin paginación (checkbox "El Controller admite
    ?paginate=true" desmarcado en la GUI) -- ver Controller.md#Módulos sin
    paginación. No debe ofrecer ?paginate=true ni construir `meta`."""
    manifest = _build_test_manifest(supports_pagination=False)
    php = Renderer().render_controller_php(manifest)
    assert "?paginate=true" not in php
    assert "request->boolean('paginate')" not in php
    assert "'meta'" not in php
    assert "$this->service->index(false)" in php
    assert "UsuariosTinyResource::class" in php


def test_strip_line_comments_keeps_docblocks_and_collapses_blank_runs():
    php = (
        "<?php\n"
        "\n"
        "/**\n"
        " * @OA\\Tag(name=\"Usuarios\")\n"
        " */\n"
        "class Foo\n"
        "{\n"
        "    // Explica por qué esto es así -- ver useFilters.md\n"
        "    public $x = 1; // no se toca: comentario final de línea, no al inicio\n"
        "\n"
        "\n"
        "    public $y = 2;\n"
        "}\n"
    )
    stripped = strip_line_comments(php)
    assert "@OA\\Tag" in stripped  # docblock /** */ nunca se toca
    assert "Explica por qué esto es así" not in stripped
    assert "public $x = 1; // no se toca" in stripped  # solo se sacan líneas que EMPIEZAN con //
    assert "\n\n\n" not in stripped  # sin huecos de más de una línea vacía


def test_render_model_php_without_comments():
    """Checkbox "Añadir comentarios explicativos" desmarcado en la GUI --
    quita los `//` de racional/referencias a .md, deja los bloques /** */
    (PHPDoc, @OA) intactos porque son funcionales, no ruido."""
    manifest = _build_test_manifest(add_comments=False)
    php = Renderer().render_model_php(manifest)
    assert "//" not in php
    assert "class siaw_usuarios extends Model" in php
    assert "public function rol_id" not in php  # no rompe nada del contenido real, solo saca comentarios


def test_render_controller_php_without_comments_keeps_swagger_docblocks():
    manifest = _build_test_manifest(add_comments=False)
    php = Renderer().render_controller_php(manifest)
    assert "//" not in php
    assert '@OA\\Tag(name="Usuarios")' in php  # PHPDoc/@OA sobrevive el toggle
    assert "class siaw_usuariosController extends Controller" in php


def test_render_controller_php_swagger_annotations():
    manifest = _build_test_manifest()
    php = Renderer().render_controller_php(manifest)
    assert '@OA\\Tag(name="Usuarios")' in php
    assert 'path="/api/siaw_usuarios",' in php
    assert 'path="/api/siaw_usuarios/{id}",' in php
    assert 'security={{"bearerAuth":{}}},' in php
    assert 'ref="#/components/schemas/UsuariosSchema"' in php
    assert '@OA\\Property(property="nombre", type="string"' in php
    assert 'required={ "nombre", "email", "rol_id" },' in php
    store_block = php.split("public function store")[0].split("@OA\\Post(")[1]
    assert '@OA\\Property(property="rol_id", type="string", format="uuid")' in store_block


def test_render_resource_php():
    manifest = _build_test_manifest()
    php = Renderer().render_resource_php(manifest)
    assert "namespace App\\Http\\Resources\\Siaw;" in php
    assert "use App\\Http\\Resources\\Siaw\\RolesRelationResource;" in php
    assert 'schema="UsuariosSchema"' in php
    assert "class UsuariosResource extends JsonResource" in php
    assert "'id' => $this->id," in php
    # Clave pública corta ("roles", modulo de siaw_roles) vs. método real del
    # Model ("siaw_roles", nombre literal de tabla) -- ver ApiResponse.md#Resource triple.
    assert "'roles' => $this->whenLoaded('siaw_roles', fn () => new RolesRelationResource($this->siaw_roles))," in php
    assert "'activo' => (bool) $this->activo," in php
    assert "'created_by_id' => $this->whenLoaded('created_by'" in php
    assert "'pkid'" not in php


def test_render_relation_resource_php():
    manifest = _build_test_manifest()
    php = Renderer().render_relation_resource_php(manifest)
    assert "class UsuariosRelationResource extends JsonResource" in php
    assert 'schema="UsuariosRelationSchema"' in php
    assert "'id' => $this->id," in php
    assert "'nombre' => $this->nombre," in php
    assert "email" not in php  # solo campos marcados "tiny" en el manifest


def test_render_relation_resource_php_independent_from_tiny():
    """"Relación" es un checkbox propio en el mapeo -- puede llevar campos
    distintos de "Tiny" (ver ApiResponse.md#Resource triple)."""
    manifest = _build_test_manifest(tiny_fields={"nombre"}, relation_fields={"email"})
    relation_php = Renderer().render_relation_resource_php(manifest)
    tiny_php = Renderer().render_tiny_resource_php(manifest)

    assert "'email' => $this->email," in relation_php
    assert "'nombre' => $this->nombre," not in relation_php

    assert "'nombre' => $this->nombre," in tiny_php
    assert "'email' => $this->email," not in tiny_php


def test_render_tiny_resource_php():
    manifest = _build_test_manifest()
    php = Renderer().render_tiny_resource_php(manifest)
    assert "class UsuariosTinyResource extends JsonResource" in php
    assert 'schema="UsuariosTinySchema"' in php
    assert "'id' => $this->id," in php
    assert "'nombre' => $this->nombre," in php


def test_render_routes_module_php():
    manifest = _build_test_manifest()
    php = Renderer().render_routes_module_php(manifest)
    assert "use App\\Http\\Controllers\\Api\\Siaw\\siaw_usuariosController;" in php
    assert "Route::apiResource('siaw_usuarios', siaw_usuariosController::class)" in php
    assert "->parameters(['siaw_usuarios' => 'siaw_usuarios']);" in php


def test_render_interfaces_ts_shape():
    manifest = _build_test_manifest()
    ts = Renderer().render_interfaces_ts(manifest)
    assert "export interface IUsuarios {" in ts
    assert "export interface IUsuariosCreate {" in ts
    assert "export interface IUsuariosUpdate extends Partial<IUsuariosCreate> {" in ts
    assert "export interface IUsuariosTiny {" in ts
    assert "import { IRolesTiny } from '@interfaces/models/roles.interface';" in ts
    assert "roles?: IRolesTiny | null;" in ts  # relación anidada -- misma clave pública que el Resource
    assert "rol_id: string;" in ts  # UUID plano en el Create (required, no nullable)
    assert "created_by_id?: IAuditUser | null;" in ts
    # Tiny solo trae los campos marcados como tiny (acá: nombre) + id
    tiny_block = ts.split("export interface IUsuariosTiny {")[1]
    assert "nombre?:" in tiny_block
    assert "email?:" not in tiny_block


def test_generate_files_writes_full_pattern_into_project_structure(tmp_path):
    manifest = _build_test_manifest()
    backend_root = tmp_path / "backend"
    frontend_root = tmp_path / "frontend"
    written = generate_files(manifest, backend_root, frontend_root)

    expected = {
        "model": backend_root / "app/Models/dbsiaw/siaw_usuarios.php",
        "service": backend_root / "app/Services/UsuariosService.php",
        "filters": backend_root / "app/Filters/siaw_usuariosFilters.php",
        "store_request": backend_root / "app/Http/Requests/Siaw/Usuarios/StoreUsuariosRequest.php",
        "update_request": backend_root / "app/Http/Requests/Siaw/Usuarios/UpdateUsuariosRequest.php",
        "trait": backend_root / "app/Http/Requests/Siaw/Traits/Usuarios/ValidatesUsuarios.php",
        "resource": backend_root / "app/Http/Resources/Siaw/UsuariosResource.php",
        "relation_resource": backend_root / "app/Http/Resources/Siaw/UsuariosRelationResource.php",
        "tiny_resource": backend_root / "app/Http/Resources/Siaw/UsuariosTinyResource.php",
        "controller": backend_root / "app/Http/Controllers/Api/Siaw/siaw_usuariosController.php",
        "routes_module": backend_root / "routes/modules/usuarios.php",
        "interfaces": frontend_root / "src/app/interfaces/models/usuarios.interface.ts",
    }
    for key, path in expected.items():
        assert written[key] == path, key
        assert path.exists()
        assert path.read_text(encoding="utf-8").strip() != ""

    # Por default no se escribe el compartido -- ver write_audit_interface
    assert "audit_user" not in written
    assert not (frontend_root / "src/app/interfaces/shared/audit-user.interface.ts").exists()


def test_generate_files_writes_audit_interface_when_requested(tmp_path):
    manifest = _build_test_manifest()
    backend_root = tmp_path / "backend"
    frontend_root = tmp_path / "frontend"
    written = generate_files(manifest, backend_root, frontend_root, write_audit_interface=True)

    audit_path = frontend_root / "src/app/interfaces/shared/audit-user.interface.ts"
    assert written["audit_user"] == audit_path
    assert audit_path.exists()


def test_render_all_then_write_files_uses_edited_content(tmp_path):
    """El preview es editable: lo que se escribe es lo que esté en el texto
    al momento de confirmar, no necesariamente el render de fábrica."""
    manifest = _build_test_manifest()
    contents = render_all(manifest)

    hand_edited = "// corregido a mano por el desarrollador\n" + contents["model"]
    contents["model"] = hand_edited

    backend_root = tmp_path / "backend"
    frontend_root = tmp_path / "frontend"
    written = write_files(manifest, backend_root, frontend_root, contents)

    assert written["model"].read_text(encoding="utf-8") == hand_edited
    assert written["service"].read_text(encoding="utf-8") == contents["service"]


def test_generate_files_does_not_overwrite_shared_audit_interface(tmp_path):
    manifest = _build_test_manifest()
    backend_root = tmp_path / "backend"
    frontend_root = tmp_path / "frontend"
    generate_files(manifest, backend_root, frontend_root, write_audit_interface=True)

    audit_path = frontend_root / "src/app/interfaces/shared/audit-user.interface.ts"
    audit_path.write_text("// modificado a mano", encoding="utf-8")

    written_again = generate_files(manifest, backend_root, frontend_root, write_audit_interface=True)
    assert "audit_user" not in written_again
    assert audit_path.read_text(encoding="utf-8") == "// modificado a mano"


def test_existing_target_files_empty_on_fresh_project(tmp_path):
    manifest = _build_test_manifest()
    contents = render_all(manifest)
    backend_root = tmp_path / "backend"
    frontend_root = tmp_path / "frontend"

    assert existing_target_files(manifest, backend_root, frontend_root, contents) == {}


def test_existing_target_files_detects_preexisting_model_and_resource(tmp_path):
    """Simula un proyecto legado que ya tiene Model/Resource en la ruta
    convencional (ej. se está regenerando un módulo generado antes, o el
    proyecto legado por casualidad sigue esa misma convención) -- write_files
    los pisaría en silencio si no se avisa antes."""
    manifest = _build_test_manifest()
    contents = render_all(manifest)
    backend_root = tmp_path / "backend"
    frontend_root = tmp_path / "frontend"

    backend_files = backend_paths(manifest)
    model_path = backend_root / backend_files["model"]
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text("// modelo legado hecho a mano", encoding="utf-8")

    resource_path = backend_root / backend_files["resource"]
    resource_path.parent.mkdir(parents=True, exist_ok=True)
    resource_path.write_text("// resource legado hecho a mano", encoding="utf-8")

    existing = existing_target_files(manifest, backend_root, frontend_root, contents)

    assert existing == {"model": model_path, "resource": resource_path}
    # No tocó nada -- es solo el chequeo, write_files sigue siendo quien escribe.
    assert model_path.read_text(encoding="utf-8") == "// modelo legado hecho a mano"
