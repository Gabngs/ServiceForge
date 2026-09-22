from generador import model_resource_scan as mrs
from generador.db import Column
from generador.match_learner import MatchLearner

_COLUMNS = [
    Column(name="nombre", sql_type="varchar(255)", nullable=False, key="", default=None, extra=""),
    Column(name="monto", sql_type="decimal(10,2)", nullable=False, key="", default=None, extra=""),
]


def _write_model(backend_root, prefijo, table, *, namespace=None):
    model_dir = backend_root / "app" / "Models" / f"db{prefijo}"
    model_dir.mkdir(parents=True, exist_ok=True)
    ns = namespace or f"App\\Models\\db{prefijo}"
    (model_dir / f"{table}.php").write_text(
        f"<?php\nnamespace {ns};\nclass {table} extends Model {{\n}}\n", encoding="utf-8"
    )


def _write_resource(backend_root, prefijo, class_name, fields, *, mixin=None):
    res_dir = backend_root / "app" / "Http" / "Resources" / prefijo
    res_dir.mkdir(parents=True, exist_ok=True)
    mixin_doc = f"/**\n * @mixin {mixin}\n */\n" if mixin else ""
    array_body = "\n".join(f"            '{f}' => $this->{f}," for f in fields)
    (res_dir / f"{class_name}.php").write_text(
        f"<?php\nnamespace App\\Http\\Resources\\{prefijo};\n{mixin_doc}"
        f"class {class_name} extends JsonResource {{\n"
        f"    public function toArray($request): array\n    {{\n        return [\n{array_body}\n        ];\n    }}\n"
        f"}}\n",
        encoding="utf-8",
    )
    return res_dir / f"{class_name}.php"


def test_scan_models_reads_class_namespace_and_table_hint(tmp_path):
    backend_root = tmp_path / "backend"
    _write_model(backend_root, "catalogo", "catalogo_premiaciones")

    models = mrs.scan_models(backend_root)

    assert len(models) == 1
    assert models[0].class_name == "catalogo_premiaciones"
    assert models[0].namespace == "App\\Models\\dbcatalogo"


def test_scan_resources_extracts_role_fields_and_mixin(tmp_path):
    backend_root = tmp_path / "backend"
    _write_resource(
        backend_root,
        "catalogo",
        "PremiacionResource",
        ["uuid", "nombre", "monto"],
        mixin="App\\Models\\dbcatalogo\\catalogo_premiaciones",
    )

    resources = mrs.scan_resources(backend_root)

    assert len(resources) == 1
    resource = resources[0]
    assert resource.role == "resource"
    assert resource.base_name == "Premiacion"
    assert resource.fields == {"uuid", "nombre", "monto"}
    assert resource.mixin_target == "catalogo_premiaciones"


def test_scan_resources_distinguishes_relation_and_tiny_roles(tmp_path):
    backend_root = tmp_path / "backend"
    _write_resource(backend_root, "catalogo", "PremiacionRelationResource", ["nombre"])
    _write_resource(backend_root, "catalogo", "PremiacionTinyResource", ["nombre"])
    _write_resource(backend_root, "catalogo", "PremiacionResource", ["nombre"])

    resources = {r.class_name: r for r in mrs.scan_resources(backend_root)}

    assert resources["PremiacionRelationResource"].role == "relation_resource"
    assert resources["PremiacionTinyResource"].role == "tiny_resource"
    assert resources["PremiacionResource"].role == "resource"


def test_find_candidates_ranks_mixin_match_highest(tmp_path):
    """Caso legado real: el Resource no sigue la convención de nombre de
    esta herramienta (sería "catalogo_premiacionesResource") pero declara
    @mixin apuntando al Model -- señal suficiente para un score alto sin
    haber entrenado nada todavía (prior heurístico, ver match_learner.py)."""
    backend_root = tmp_path / "backend"
    _write_model(backend_root, "catalogo", "catalogo_premiaciones")
    _write_resource(
        backend_root,
        "catalogo",
        "PremiacionResource",
        ["uuid", "nombre", "monto"],
        mixin="catalogo_premiaciones",
    )

    match = mrs.find_candidates(
        "catalogo_premiaciones", _COLUMNS, backend_root, learner=MatchLearner(path=tmp_path / "learner.json")
    )

    assert match.model is not None
    assert match.model.class_name == "catalogo_premiaciones"
    assert match.best is not None
    assert match.best.resource.class_name == "PremiacionResource"
    assert match.best.score > 0.9


def test_find_candidates_filters_out_unrelated_resources(tmp_path):
    backend_root = tmp_path / "backend"
    _write_model(backend_root, "catalogo", "catalogo_premiaciones")
    _write_resource(backend_root, "reportes", "VentaMensualResource", ["mes", "total"])

    match = mrs.find_candidates(
        "catalogo_premiaciones", _COLUMNS, backend_root, learner=MatchLearner(path=tmp_path / "learner.json")
    )

    assert match.candidates == []


def test_find_candidates_returns_no_model_when_none_exists(tmp_path):
    backend_root = tmp_path / "backend"
    backend_root.mkdir(parents=True)

    match = mrs.find_candidates(
        "catalogo_premiaciones", _COLUMNS, backend_root, learner=MatchLearner(path=tmp_path / "learner.json")
    )

    assert match.model is None
    assert match.candidates == []


def test_relation_names_improve_field_jaccard_for_relation_resource(tmp_path):
    """Un RelationResource típico expone claves de relación ('articulo',
    'created_by'), no columnas planas -- sin sumarlas al set comparado,
    field_jaccard subestima el solapamiento justo para ese rol."""
    backend_root = tmp_path / "backend"
    _write_resource(
        backend_root,
        "catalogo",
        "PremiacionRelationResource",
        ["nombre", "articulo", "created_by"],
    )

    without_relations = mrs.find_candidates(
        "catalogo_premiaciones", _COLUMNS, backend_root, learner=MatchLearner(path=tmp_path / "a.joblib"), min_score=0.0
    )
    with_relations = mrs.find_candidates(
        "catalogo_premiaciones",
        _COLUMNS,
        backend_root,
        learner=MatchLearner(path=tmp_path / "b.joblib"),
        min_score=0.0,
        relation_names={"articulo", "created_by", "updated_by", "deleted_by"},
    )

    jaccard_without = without_relations.best.features["field_jaccard"]
    jaccard_with = with_relations.best.features["field_jaccard"]
    assert jaccard_with > jaccard_without


def test_user_confirmation_improves_future_scores_for_similar_cases(tmp_path):
    """El punto central del aprendizaje: un candidato correcto pero con
    nombre muy distinto al de la tabla (sin @mixin) arranca con score
    mediocre -- una confirmación del desarrollador sube la confianza para
    la próxima vez que aparezca ese mismo patrón de señales."""
    backend_root = tmp_path / "backend"
    _write_resource(backend_root, "catalogo", "AwardPayoutView", ["nombre", "monto"])

    learner_path = tmp_path / "learner.json"
    learner = MatchLearner(path=learner_path)
    match = mrs.find_candidates("catalogo_premiaciones", _COLUMNS, backend_root, learner=learner, min_score=0.0)
    candidate = match.best
    before = candidate.score

    learner.update(candidate.features, label=1.0)

    learner_after = MatchLearner.load(learner_path)
    match_after = mrs.find_candidates(
        "catalogo_premiaciones", _COLUMNS, backend_root, learner=learner_after, min_score=0.0
    )
    assert match_after.best.score > before
