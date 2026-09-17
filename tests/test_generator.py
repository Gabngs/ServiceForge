from generador.db import Column
from generador.fk_resolver import FkResolution
from generador.generator import Renderer, build_manifest, generate_files, render_all, write_files


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


def _build_test_manifest(**overrides):
    columns = _siaw_usuarios_columns()
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
    manifest = _build_test_manifest()
    assert len(manifest.relations) == 1
    relation = manifest.relations[0]
    assert relation.column == "rol_id"
    assert relation.method == "rol"
    assert relation.model_class == "siaw_roles"


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
    assert "public function rol(): BelongsTo" in php
    assert "return $this->belongsTo(siaw_roles::class, 'rol_id', 'pkid');" in php
    assert "'activo' => 'boolean'" in php
    assert "'pkid'" not in php.split("$fillable")[1].split("];")[0]  # nunca en fillable


def test_render_model_php_contains_audit_relations():
    manifest = _build_test_manifest()
    php = Renderer().render_model_php(manifest)
    for method, column in [("created_by", "created_by_id"), ("updated_by", "updated_by_id"), ("deleted_by", "deleted_by_id")]:
        assert f"public function {method}(): BelongsTo" in php
        assert f"return $this->belongsTo(\\App\\Models\\User::class, '{column}', 'pkid');" in php


def test_render_service_php_uses_english_method_names():
    manifest = _build_test_manifest()
    php = Renderer().render_service_php(manifest)
    assert "class UsuariosService extends AbstractModuleService" in php
    for method in ("index", "show", "store", "update", "destroy"):
        assert f"function {method}(" in php
    assert "'rol'," in php  # en RELATIONS
    assert "'created_by', 'updated_by', 'deleted_by'" in php
    assert "'rol_id' => \\App\\Models\\dbsiaw\\siaw_roles::class," in php


def test_render_filters_php():
    manifest = _build_test_manifest()
    php = Renderer().render_filters_php(manifest)
    assert "class siaw_usuariosFilters extends QueryFilters" in php
    search_block = php.split("$allowedSearch")[1].split("];")[0]
    assert "'nombre'," in search_block
    assert "'email'," in search_block  # varchar -> texto libre, elegible para LIKE
    assert "'rol'," in php.split("$allowedIncludes")[1].split("];")[0]
    for field_name in ("nombre", "email", "rol_id", "activo"):
        assert f"'{field_name}'," in php.split("$allowedFilters")[1].split("];")[0]


def test_render_filters_php_generates_fk_resolution_method():
    manifest = _build_test_manifest()
    php = Renderer().render_filters_php(manifest)
    assert "public function rol_id($value)" in php
    assert "\\App\\Models\\dbsiaw\\siaw_roles::where('id', $value)->value('pkid');" in php
    assert "return $this->builder->where('rol_id', $pkid);" in php
    assert "return $this->builder->whereNull('rol_id');" in php


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
    assert "'rol' => $this->whenLoaded('rol', fn () => new RolesRelationResource($this->rol))," in php
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
    assert "rol?: IRolesTiny | null;" in ts  # relación anidada en la interfaz completa
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
