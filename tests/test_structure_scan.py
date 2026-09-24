"""Escáner de estructura (structure_scan.py) y su integración con el modelo entrenado.

Los backends son de juguete, armados en tmp_path: tres modelos con prefijo `inv_` (el escáner
deriva el prefijo del propio repo) y un archivo de cada rol por modelo, con nombres que no siguen
la convención de esta herramienta a propósito.
"""

import re

from generador import model_resource_scan as mrs
from generador import structure_scan as ss
from generador.db import Column
from generador.match_learner import StructureLearner, bundled_structure_path

_COLUMNS = [
    Column(name="nombre", sql_type="varchar(255)", nullable=False, key="", default=None, extra=""),
    Column(name="precio", sql_type="decimal(10,2)", nullable=False, key="", default=None, extra=""),
]


def _php(root, rel, body):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("<?php\n" + body, encoding="utf-8")
    return path


def _write_module(root, table, camel, *, columns=("nombre", "precio")):
    """Un módulo completo con nombres 'legados': Model literal, Service/Resource en Camel sin prefijo."""
    fillable = ", ".join(f"'{c}'" for c in columns)
    _php(root, f"app/Models/dbinv/{table}.php",
         f"namespace App\\Models\\dbinv;\nuse App\\Filters\\dbinv\\{table}Filters;\n"
         f"class {table} extends Model\n{{\n    protected $table = '{table}';\n"
         f"    protected string $default_filters = {table}Filters::class;\n    protected $fillable = [{fillable}];\n}}\n")
    _php(root, f"app/Filters/dbinv/{table}Filters.php",
         f"namespace App\\Filters\\dbinv;\nclass {table}Filters extends QueryFilters\n{{\n    protected array $columnSearch = ['nombre'];\n}}\n")
    keys = "\n".join(f"            '{c}' => $this->{c}," for c in columns)
    for suffix in ("Resource", "RelationResource"):
        _php(root, f"app/Http/Resources/Inv/{camel}{suffix}.php",
             f"namespace App\\Http\\Resources\\Inv;\nclass {camel}{suffix} extends JsonResource\n{{\n"
             f"    public function toArray($request): array\n    {{\n        return [\n{keys}\n        ];\n    }}\n}}\n")
    for action in ("Store", "Update"):
        _php(root, f"app/Http/Requests/Inv/{table}/{action}Request.php",
             f"namespace App\\Http\\Requests\\Inv\\{table};\nclass {action}Request extends FormRequest\n{{\n"
             f"    public function rules(): array\n    {{\n        return [\n{keys.replace('$this->' + columns[0], '[]')}\n        ];\n    }}\n}}\n")
    _php(root, f"app/Services/{camel}Service.php",
         f"namespace App\\Services;\nuse App\\Models\\dbinv\\{table};\nclass {camel}Service\n{{\n}}\n")
    _php(root, f"app/Http/Controllers/Api/Inv/{camel}Controller.php",
         f"namespace App\\Http\\Controllers\\Api\\Inv;\nuse App\\Services\\{camel}Service;\nclass {camel}Controller extends Controller\n{{\n}}\n")
    _php(root, f"routes/modules/{table}.php",
         f"use App\\Http\\Controllers\\Api\\Inv\\{camel}Controller;\nRoute::apiResource('{table}', {camel}Controller::class);\n")


def _backend(tmp_path):
    root = tmp_path / "backend"
    _write_module(root, "inv_productos", "Producto")
    _write_module(root, "inv_clientes", "Cliente", columns=("razon_social", "ruc"))
    _write_module(root, "inv_pedidos", "Pedido", columns=("fecha", "total"))
    # ruido que NO debe contar: carpeta vacía, framework y una vista blade
    (root / "app/Http/Resources/Legacy").mkdir(parents=True)
    _php(root, "routes/console.php", "Artisan::command('inspire', fn () => 1);\n")
    return root


def _learner(tmp_path):
    return StructureLearner.load(tmp_path / "user.joblib")


def test_scan_repo_classifies_roles_by_path_segments_and_class_name(tmp_path):
    index = ss.scan_repo(_backend(tmp_path))

    assert {m.class_name for m in index.models} == {"inv_productos", "inv_clientes", "inv_pedidos"}
    assert len(index.files["filter"]) == 3
    assert len(index.files["resource"]) == 3
    assert len(index.files["relation_resource"]) == 3
    assert len(index.files["store_request"]) == 3 and len(index.files["update_request"]) == 3
    assert len(index.files["service"]) == 3
    assert len(index.files["controller"]) == 3
    assert len(index.files["route"]) == 3  # routes/console.php es del framework: no cuenta
    assert index.prefixes == ["inv"]  # se deriva del propio repo, no está hardcodeado


def test_scan_repo_works_with_other_layouts(tmp_path):
    """Sin carpetas fijas: la misma clasificación sirve para Request en singular y layout modular."""
    root = tmp_path / "modular"
    _php(root, "Modules/Ventas/App/Http/Request/StorePedido.php",
         "namespace Modules\\Ventas\\App\\Http\\Request;\nclass StorePedido extends FormRequest\n{\n}\n")
    _php(root, "Modules/Ventas/App/Services/PedidoManager.php",
         "namespace Modules\\Ventas\\App\\Services;\nclass PedidoManager\n{\n}\n")

    index = ss.scan_repo(root)

    assert [f.class_name for f in index.files["store_request"]] == ["StorePedido"]
    assert [f.class_name for f in index.files["service"]] == ["PedidoManager"]  # sin sufijo `Service`


def test_assign_owners_prefers_exact_name_and_records_the_criterion(tmp_path):
    index = ss.scan_repo(_backend(tmp_path))
    owners = ss.assign_owners(index)["inv_productos"]

    assert [p for p, _ in owners["filter"]] == ["app/Filters/dbinv/inv_productosFilters.php"]
    assert owners["filter"][0][1] == "declared"  # el modelo lo declara con $default_filters
    # `ProductoService` <-> `inv_productos`: sin el prefijo `inv_` y salvo singular/plural
    assert owners["service"] == [("app/Services/ProductoService.php", "name_stem")]
    assert any(via == "route_controller" or via.startswith("name") for _, via in owners["route"])
    # el Service de otro modelo nunca se le asigna
    assert all("Cliente" not in p for roles in owners.values() for p, _ in roles)


def test_helpers_copied_from_model_resource_scan_stay_identical():
    """structure_scan no importa model_resource_scan (import circular): sus copias no pueden derivar."""
    php = "class X {\n public function toArray($request): array {\n return ['a' => 1, 'b' => [1], 'c' => 2];\n }\n public function other() { return ['z' => 1]; }\n}"
    assert ss._extract_fields(php) == mrs._extract_fields(php) == {"a", "b", "c"}
    assert ss._normalize("catalogo_Premiaciones") == mrs._normalize("catalogo_Premiaciones")
    assert ss._MIXIN_RE.pattern == mrs._MIXIN_RE.pattern
    assert ss._TOARRAY_SIG_RE.pattern == mrs._TOARRAY_SIG_RE.pattern


def test_find_model_and_synth_model(tmp_path):
    index = ss.scan_repo(_backend(tmp_path))

    assert ss.find_model(index, "inv_productos", "inv_productos").class_name == "inv_productos"
    assert ss.find_model(index, "inv_nada", "inv_nada") is None

    virtual = ss.synth_model(index, "inv_marcas", "inv_marcas", {"nombre"})
    assert virtual.table == "inv_marcas" and virtual.columns == {"nombre"}
    assert virtual.norms == {"marcas"}  # el prefijo `inv` del repo se descuenta


def test_rank_candidates_puts_the_right_file_first_for_every_role(tmp_path):
    index = ss.scan_repo(_backend(tmp_path))
    model = ss.find_model(index, "inv_productos", "inv_productos")

    ranked = ss.rank_candidates(index, model, _learner(tmp_path))

    expected = {
        "filter": "inv_productosFilters",
        "resource": "ProductoResource",
        "relation_resource": "ProductoRelationResource",
        "service": "ProductoService",
        "controller": "ProductoController",
    }
    for role, class_name in expected.items():
        assert ranked[role], f"sin candidatos de {role}"
        assert ranked[role][0].file.class_name == class_name, role
    assert ranked["store_request"][0].file.path == "app/Http/Requests/Inv/inv_productos/StoreRequest.php"
    assert ranked["route"][0].file.path == "routes/modules/inv_productos.php"


def test_find_candidates_returns_resources_in_the_legacy_shape_plus_other_roles(tmp_path):
    match = mrs.find_candidates("inv_productos", _COLUMNS, _backend(tmp_path), learner=_learner(tmp_path))

    assert match.model.class_name == "inv_productos"
    # el Resource completo y el de relación del módulo son ambos candidatos válidos (en este backend de
    # juguete tienen las mismas keys): los dos van arriba, con la forma de siempre
    top_two = {c.resource.class_name: c.resource for c in match.candidates[:2]}
    assert set(top_two) == {"ProductoResource", "ProductoRelationResource"}
    assert top_two["ProductoResource"].role == "resource"
    assert top_two["ProductoRelationResource"].role == "relation_resource"
    assert match.best.resource.path.is_file()  # ruta absoluta, como antes
    assert match.best.score >= 0.65
    assert match.others["service"][0].file.class_name == "ProductoService"
    assert "resource" not in match.others  # los Resources van en `candidates`, no en `others`


def test_find_candidates_for_a_table_without_model_uses_a_virtual_one(tmp_path):
    """El caso más común: generar por primera vez. No hay Model, pero igual se detecta lo que ya exista."""
    root = _backend(tmp_path)
    _php(root, "app/Http/Resources/Inv/MarcaResource.php",
         "namespace App\\Http\\Resources\\Inv;\nclass MarcaResource extends JsonResource\n{\n"
         "    public function toArray($request): array\n    {\n        return ['nombre' => 1];\n    }\n}\n")

    match = mrs.find_candidates("inv_marcas", _COLUMNS[:1], root, learner=_learner(tmp_path))

    assert match.model is None
    assert match.best is not None and match.best.resource.class_name == "MarcaResource"


def test_find_candidates_ignores_files_of_other_models(tmp_path):
    match = mrs.find_candidates("inv_productos", _COLUMNS, _backend(tmp_path), learner=_learner(tmp_path))

    names = [c.resource.class_name for c in match.candidates if c.score >= 0.65]
    assert not any(n.startswith(("Cliente", "Pedido")) for n in names)


def test_bundled_structure_model_is_packaged_and_matches_the_current_features():
    assert bundled_structure_path().is_file()
    learner = StructureLearner.load()
    assert learner.is_fitted
    assert learner.scaler is not None
    assert list(learner.feature_names) == list(ss.FEATURES)
    assert re.fullmatch(r"structure_matcher_pretrained\.joblib", bundled_structure_path().name)
