"""Layout de la estructura (layout.py), su detección en un proyecto (structure_profile.py) y la
generación con una estructura propia (generator.py)."""

from pathlib import Path

from generador import generator, layout, paths, structure_profile
from generador.db import Column
from generador.fk_resolver import FkResolution
from generador.generator import RelationTarget
from generador.layout import STANDARD_LAYOUT, RolePlacement, StructureLayout


# ------------------------------------------------------------------ layout
def test_expand_tokens_and_unknown_token_is_left_alone():
    assert layout.expand("app/Http/Requests/{Prefijo}/{Modulo}", "siaw_permiso_usuario") == "app/Http/Requests/Siaw/PermisoUsuario"
    assert layout.expand("{table}|{prefijo}|{modulo}|{Table}", "siaw_permiso_usuario") == (
        "siaw_permiso_usuario|siaw|permiso_usuario|Siaw_permiso_usuario"
    )
    assert layout.expand("x/{desconocido}", "a_b") == "x/{desconocido}"


def test_standard_layout_keeps_the_conventional_paths():
    # Son las rutas que la herramienta usa desde siempre: el layout estándar no las cambia.
    table = "siaw_permiso_usuario"
    expected = {
        "model": "app/Models/dbsiaw/siaw_permiso_usuario.php",
        "service": "app/Services/PermisoUsuarioService.php",
        "filters": "app/Filters/siaw_permiso_usuarioFilters.php",
        "store_request": "app/Http/Requests/Siaw/PermisoUsuario/StorePermisoUsuarioRequest.php",
        "update_request": "app/Http/Requests/Siaw/PermisoUsuario/UpdatePermisoUsuarioRequest.php",
        "trait": "app/Http/Requests/Siaw/Traits/PermisoUsuario/ValidatesPermisoUsuario.php",
        "resource": "app/Http/Resources/Siaw/PermisoUsuarioResource.php",
        "relation_resource": "app/Http/Resources/Siaw/PermisoUsuarioRelationResource.php",
        "tiny_resource": "app/Http/Resources/Siaw/PermisoUsuarioTinyResource.php",
        "controller": "app/Http/Controllers/Api/Siaw/siaw_permiso_usuarioController.php",
        "routes_module": "routes/modules/permiso_usuario.php",
    }
    for role, path in expected.items():
        assert STANDARD_LAYOUT.path(role, table).as_posix() == path, role
    assert STANDARD_LAYOUT.is_standard()


def test_namespace_and_fqcn_come_from_the_directory():
    assert STANDARD_LAYOUT.namespace("resource", "siaw_x") == "App\\Http\\Resources\\Siaw"
    assert STANDARD_LAYOUT.fqcn("model", "siaw_x") == "App\\Models\\dbsiaw\\siaw_x"
    assert layout.namespace_from_directory("Modules/Blog/app/Http") == "Modules\\Blog\\app\\Http"


def test_explicit_namespace_overrides_the_directory():
    custom = STANDARD_LAYOUT.with_placement(
        "service", RolePlacement("src/Services/{Prefijo}", "{Modulo}Service", "Acme\\Svc\\{Prefijo}"), layout.ORIGIN_MANUAL
    )
    assert custom.namespace("service", "siaw_x") == "Acme\\Svc\\Siaw"
    assert custom.path("service", "siaw_x").as_posix() == "src/Services/Siaw/XService.php"
    assert custom.origin("service") == "manual" and custom.origin("model") == "estandar"
    assert not custom.is_standard()


def test_layout_roundtrips_through_dict():
    custom = STANDARD_LAYOUT.with_placement(
        "controller", RolePlacement("app/Http/Controllers/Api/dbsiaw", "{table}Controller"), layout.ORIGIN_PROJECT
    )
    restored = StructureLayout.from_dict(custom.to_dict())
    assert restored.placements == custom.placements
    assert restored.origin("controller") == "proyecto"
    # Un dict incompleto o roto no rompe: lo que falta queda en el estándar.
    partial = StructureLayout.from_dict({"controller": {"directory": "x", "name": "{table}C"}, "model": "roto"})
    assert partial.placement("controller").directory == "x"
    assert partial.placement("model") == STANDARD_LAYOUT.placement("model")


# --------------------------------------------------------------- detección
def _php(root: Path, rel: str, body: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("<?php\n" + body, encoding="utf-8")


def _siaw_like_project(root: Path, tables=("catalogo_tienda", "catalogo_zona", "catalogo_rol", "catalogo_cargo")) -> None:
    for t in tables:
        _php(root, f"app/Models/dbsiaw/{t}.php",
             f"namespace App\\Models\\dbsiaw;\nuse Illuminate\\Database\\Eloquent\\Model;\n"
             f"class {t} extends Model {{ protected $table = '{t}'; protected $fillable = ['id','nombre']; }}\n")
        _php(root, f"app/Filters/dbsiaw/{t}Filters.php",
             f"namespace App\\Filters\\dbsiaw;\nclass {t}Filters extends QueryFilters {{}}\n")
        _php(root, f"app/Http/Resources/dbsiaw/{t}Resource.php",
             f"namespace App\\Http\\Resources\\dbsiaw;\nclass {t}Resource extends JsonResource {{ public function toArray($r) {{ return ['id' => 1]; }} }}\n")
        _php(root, f"app/Http/Request/dbsiaw/{t}/Store{t}Request.php",
             f"namespace App\\Http\\Request\\dbsiaw\\{t};\nclass Store{t}Request extends FormRequest {{}}\n")
        _php(root, f"app/Http/Request/dbsiaw/{t}/Update{t}Request.php",
             f"namespace App\\Http\\Request\\dbsiaw\\{t};\nclass Update{t}Request extends FormRequest {{}}\n")
        _php(root, f"app/Services/{t}Service.php", f"namespace App\\Services;\nclass {t}Service {{}}\n")
        _php(root, f"app/Http/Controllers/Api/dbsiaw/{t}Controller.php",
             f"namespace App\\Http\\Controllers\\Api\\dbsiaw;\nclass {t}Controller extends Controller {{}}\n")
        _php(root, f"routes/{t}.php",
             f"use App\\Http\\Controllers\\Api\\dbsiaw\\{t}Controller;\nRoute::apiResource('{t}', {t}Controller::class);\n")


def test_detect_layout_infers_folders_and_names_from_the_project(tmp_path):
    _siaw_like_project(tmp_path)
    result = structure_profile.detect_layout(tmp_path)
    found = result.layout

    assert found.placement("model").directory == "app/Models/dbsiaw"
    assert found.placement("resource") == RolePlacement("app/Http/Resources/dbsiaw", "{table}Resource")
    assert found.placement("store_request") == RolePlacement("app/Http/Request/dbsiaw/{table}", "Store{table}Request")
    assert found.placement("update_request").name == "Update{table}Request"
    assert found.placement("service") == RolePlacement("app/Services", "{table}Service")
    assert found.placement("controller").directory == "app/Http/Controllers/Api/dbsiaw"
    assert found.placement("routes_module") == RolePlacement("routes", "{table}")
    assert found.placement("filters").directory == "app/Filters/dbsiaw"

    # ...y aplicado a una tabla nueva da las rutas propias del proyecto.
    assert found.path("store_request", "catalogo_nueva").as_posix() == (
        "app/Http/Request/dbsiaw/catalogo_nueva/Storecatalogo_nuevaRequest.php"
    )
    assert found.fqcn("controller", "catalogo_nueva") == "App\\Http\\Controllers\\Api\\dbsiaw\\catalogo_nuevaController"

    assert result.evidence["resource"].samples == 4 and result.evidence["resource"].confidence == 1.0
    assert found.origin("resource") == "proyecto"
    assert result.evidence["resource"].examples


def test_detect_layout_keeps_the_standard_for_roles_the_project_does_not_have(tmp_path):
    _siaw_like_project(tmp_path)
    result = structure_profile.detect_layout(tmp_path)
    # Sin traits de validación en el proyecto de ejemplo: nada que detectar ni deducir.
    assert result.evidence["trait"].placement is None
    assert result.layout.placement("trait") == STANDARD_LAYOUT.placement("trait")
    assert result.layout.origin("trait") == "estandar"
    # "detectados" son solo los que tienen archivos; los deducidos no cuentan
    assert sorted(result.detected_roles()) == sorted(
        ["model", "service", "filters", "store_request", "update_request", "resource", "controller", "routes_module"]
    )


def test_detect_layout_deduces_relation_and_tiny_resources_from_the_resource_folder(tmp_path):
    _siaw_like_project(tmp_path)  # el proyecto solo tiene Resources completos
    result = structure_profile.detect_layout(tmp_path)

    relation = result.layout.placement("relation_resource")
    tiny = result.layout.placement("tiny_resource")
    assert relation == RolePlacement("app/Http/Resources/dbsiaw", "{table}RelationResource")
    assert tiny == RolePlacement("app/Http/Resources/dbsiaw", "{table}TinyResource")
    assert result.evidence["relation_resource"].inferred_from == "resource"
    assert result.layout.origin("relation_resource") == "proyecto"
    assert result.layout.path("relation_resource", "catalogo_nueva").as_posix() == (
        "app/Http/Resources/dbsiaw/catalogo_nuevaRelationResource.php"
    )


def test_detect_layout_deduces_a_request_from_its_sibling(tmp_path):
    for t in ("catalogo_a", "catalogo_b"):
        _php(tmp_path, f"app/Models/dbsiaw/{t}.php",
             f"namespace App\\Models\\dbsiaw;\nuse Illuminate\\Database\\Eloquent\\Model;\n"
             f"class {t} extends Model {{ protected $table = '{t}'; }}\n")
        _php(tmp_path, f"app/Http/Request/dbsiaw/{t}/Store{t}Request.php",
             f"namespace App\\Http\\Request\\dbsiaw\\{t};\nclass Store{t}Request extends FormRequest {{}}\n")
    result = structure_profile.detect_layout(tmp_path)
    assert result.evidence["update_request"].inferred_from == "store_request"
    assert result.layout.placement("update_request") == RolePlacement("app/Http/Request/dbsiaw/{table}", "Update{table}Request")


def test_detect_layout_of_an_empty_project_is_the_standard(tmp_path):
    result = structure_profile.detect_layout(tmp_path)
    assert result.detected_roles() == []
    assert result.layout.is_standard()


def test_detect_layout_generalizes_a_folder_that_varies_per_prefix(tmp_path):
    # Carpeta por prefijo de tabla (como el estándar): el token gana al literal porque explica todo.
    for t in ("siaw_a", "siaw_b", "acme_c", "acme_d"):
        prefijo = t.split("_")[0]
        studly = prefijo.capitalize()
        _php(tmp_path, f"app/Models/db{prefijo}/{t}.php",
             f"namespace App\\Models\\db{prefijo};\nuse Illuminate\\Database\\Eloquent\\Model;\nclass {t} extends Model {{ protected $table = '{t}'; }}\n")
        _php(tmp_path, f"app/Http/Resources/{studly}/{t.split('_')[1].upper()}Resource.php",
             f"namespace App\\Http\\Resources\\{studly};\nclass {t.split('_')[1].upper()}Resource extends JsonResource {{}}\n")
    result = structure_profile.detect_layout(tmp_path)
    assert result.layout.placement("model").directory == "app/Models/db{prefijo}"


# -------------------------------------------------------------- generación
def _columns():
    def col(name, sql, nullable=False, key=""):
        return Column(name, sql, nullable=nullable, key=key, default=None, extra="")

    return [
        col("pkid", "int", key="PRI"),
        col("id", "char(32)", key="UNI"),
        col("nombre", "varchar(60)"),
        col("tipo_sistema_id", "int", key="MUL"),
    ]


def _project_layout() -> StructureLayout:
    result = STANDARD_LAYOUT
    for role, directory, name in (
        ("model", "app/Models/dbsiaw", "{table}"),
        ("service", "app/Services", "{table}Service"),
        ("filters", "app/Filters/dbsiaw", "{table}Filters"),
        ("store_request", "app/Http/Request/dbsiaw/{table}", "Store{table}Request"),
        ("update_request", "app/Http/Request/dbsiaw/{table}", "Update{table}Request"),
        ("trait", "app/Http/Request/dbsiaw/Traits/{table}", "Validates{Table}"),
        ("resource", "app/Http/Resources/dbsiaw", "{table}Resource"),
        ("relation_resource", "app/Http/Resources/dbsiaw", "{table}RelationResource"),
        ("tiny_resource", "app/Http/Resources/dbsiaw", "{table}TinyResource"),
        ("controller", "app/Http/Controllers/Api/dbsiaw", "{table}Controller"),
        ("routes_module", "routes", "{table}"),
    ):
        result = result.with_placement(role, RolePlacement(directory, name), layout.ORIGIN_PROJECT)
    return result


def _manifest(**kwargs):
    resolutions = {
        "tipo_sistema_id": FkResolution("tipo_sistema_id", "tipo_sistema", ["catalogo_tiposistema"], "auto", "catalogo_tiposistema")
    }
    return generator.build_manifest(
        "catalogo_parametrosistema", _columns(), fk_resolutions=resolutions, unique_indexes={},
        relation_fields={"nombre"}, tiny_fields={"nombre"}, connection_name="mysql_dbsiaw", **kwargs,
    )


def test_generation_with_the_project_layout_uses_its_folders_namespaces_and_names():
    manifest = _manifest(layout=_project_layout())
    contents = generator.render_all(manifest)
    written = paths.backend_paths(manifest)

    assert written["store_request"].as_posix() == "app/Http/Request/dbsiaw/catalogo_parametrosistema/Storecatalogo_parametrosistemaRequest.php"
    assert written["trait"].as_posix() == "app/Http/Request/dbsiaw/Traits/catalogo_parametrosistema/ValidatesCatalogo_parametrosistema.php"
    assert written["routes_module"].as_posix() == "routes/catalogo_parametrosistema.php"

    assert "namespace App\\Models\\dbsiaw;" in contents["model"]
    assert "belongsTo(catalogo_tiposistema::class" in contents["model"]  # mismo namespace: sin import
    assert "namespace App\\Http\\Request\\dbsiaw\\catalogo_parametrosistema;" in contents["store_request"]
    assert "use App\\Http\\Request\\dbsiaw\\Traits\\catalogo_parametrosistema\\ValidatesCatalogo_parametrosistema;" in contents["store_request"]
    assert "class Storecatalogo_parametrosistemaRequest extends FormRequest" in contents["store_request"]
    assert "use ValidatesCatalogo_parametrosistema;" in contents["store_request"]

    controller = contents["controller"]
    assert "namespace App\\Http\\Controllers\\Api\\dbsiaw;" in controller
    assert "use App\\Http\\Request\\dbsiaw\\catalogo_parametrosistema\\Storecatalogo_parametrosistemaRequest;" in controller
    assert "use App\\Http\\Resources\\dbsiaw\\catalogo_parametrosistemaResource;" in controller
    assert "use App\\Services\\catalogo_parametrosistemaService;" in controller
    assert "class catalogo_parametrosistemaController extends Controller" in controller
    assert "public function __construct(protected catalogo_parametrosistemaService $service)" in controller
    assert "ref=\"#/components/schemas/catalogo_parametrosistemaSchema\"" in controller

    assert "use App\\Http\\Controllers\\Api\\dbsiaw\\catalogo_parametrosistemaController;" in contents["routes_module"]
    assert "namespace App\\Services;" in contents["service"]
    assert "class catalogo_parametrosistemaService extends AbstractModuleService" in contents["service"]


def test_service_in_another_namespace_imports_the_shared_base_classes():
    custom = STANDARD_LAYOUT.with_placement("service", RolePlacement("app/Services/Siaw", "{table}Service"), layout.ORIGIN_MANUAL)
    service = generator.render_all(_manifest(layout=custom))["service"]
    assert "namespace App\\Services\\Siaw;" in service
    assert "use App\\Services\\AbstractModuleService;" in service
    assert "use App\\Services\\CrudService;" in service


def test_confirmed_relation_resource_is_the_one_imported_and_instantiated():
    targets = {
        "catalogo_tiposistema": RelationTarget(
            "catalogo_tiposistema",
            model_fqcn="App\\Models\\dbsiaw\\catalogo_tiposistema",
            resource_fqcn="App\\Http\\Resources\\dbsiaw\\catalogo_tiposistemaRelationResource",
        )
    }
    resource = generator.render_all(_manifest(relation_targets=targets))["resource"]
    assert "use App\\Http\\Resources\\dbsiaw\\catalogo_tiposistemaRelationResource;" in resource
    assert "new catalogo_tiposistemaRelationResource($this->catalogo_tiposistema)" in resource
    assert 'ref="#/components/schemas/catalogo_tiposistemaRelationSchema"' in resource
    # ya no se inventa el import de la convención (TiposistemaRelationResource)
    assert "\\Siaw\\TiposistemaRelationResource" not in resource
    assert "TiposistemaRelationResource" not in resource.replace("catalogo_tiposistemaRelationResource", "")


def test_relation_without_resource_emits_the_plain_column_and_no_import():
    targets = {"catalogo_tiposistema": RelationTarget("catalogo_tiposistema", no_resource=True)}
    resource = generator.render_all(_manifest(relation_targets=targets))["resource"]
    assert "RelationResource" not in resource
    assert "'tipo_sistema_id' => $this->tipo_sistema_id," in resource
    assert "whenLoaded('catalogo_tiposistema'" not in resource


def test_confirmed_related_model_is_imported_in_model_service_and_filters():
    targets = {
        "catalogo_tiposistema": RelationTarget("catalogo_tiposistema", model_fqcn="App\\Models\\Core\\TipoSistema")
    }
    contents = generator.render_all(_manifest(relation_targets=targets))
    assert "use App\\Models\\Core\\TipoSistema;" in contents["model"]
    assert "belongsTo(TipoSistema::class" in contents["model"]
    assert "'tipo_sistema_id' => TipoSistema::class," in contents["service"]
    assert "use App\\Models\\Core\\TipoSistema;" in contents["service"]
    assert "use App\\Models\\Core\\TipoSistema;" in contents["filters"]
    assert "$pkid = TipoSistema::where('id', $value)->value('pkid');" in contents["filters"]


def test_render_related_relation_resource_is_minimal_and_follows_the_layout():
    path, content = generator.render_related_relation_resource(
        "catalogo_tiposistema", _columns(), layout=_project_layout()
    )
    assert path.as_posix() == "app/Http/Resources/dbsiaw/catalogo_tiposistemaRelationResource.php"
    assert "namespace App\\Http\\Resources\\dbsiaw;" in content
    assert "class catalogo_tiposistemaRelationResource extends JsonResource" in content
    assert "'id' => $this->id," in content
    assert "'nombre' => $this->nombre," in content  # la columna de texto entra
    assert "tipo_sistema_id" not in content  # las FK no son datos descriptivos


def test_render_related_relation_resource_without_columns_is_just_the_id():
    _, content = generator.render_related_relation_resource("vta_pedido", [], layout=STANDARD_LAYOUT)
    assert "class PedidoRelationResource extends JsonResource" in content
    assert "'id' => $this->id," in content


def test_write_new_files_never_overwrites(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "Existe.php").write_text("original", encoding="utf-8")
    written = generator.write_new_files(
        tmp_path, {Path("app/Existe.php"): "nuevo", Path("app/Sub/Nuevo.php"): "contenido"}
    )
    assert [p.name for p in written] == ["Nuevo.php"]
    assert (tmp_path / "app" / "Existe.php").read_text(encoding="utf-8") == "original"
    assert (tmp_path / "app" / "Sub" / "Nuevo.php").read_text(encoding="utf-8") == "contenido"
