"""Propuesta y confirmación de los archivos de las tablas relacionadas (relation_resolution.py)."""

from pathlib import Path

from generador import relation_resolution as rr
from generador import structure_scan
from generador.layout import STANDARD_LAYOUT, RolePlacement
from generador.layout import ORIGIN_PROJECT
from generador.relation_map import RelationMap

TIPO_RR = "App\\Http\\Resources\\dbsiaw\\catalogo_tiposistemaRelationResource"
TIPO_R = "App\\Http\\Resources\\dbsiaw\\catalogo_tiposistemaResource"
TIPO_MODEL = "App\\Models\\dbsiaw\\catalogo_tiposistema"


class FakeLearner:
    """Puntúa por la similitud de nombres normalizada y registra lo que se le enseña."""

    def __init__(self):
        self.updates = []
        self.saved = 0

    def score(self, features):
        return features.get("name_sim_norm", 0.0)

    def update(self, features, label, save=True):
        self.updates.append((features, label))

    def save(self):
        self.saved += 1


def _php(root: Path, rel: str, body: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("<?php\n" + body, encoding="utf-8")


def _project(tmp_path: Path, *, with_relation_resource: bool = True) -> Path:
    for t in ("catalogo_tiposistema", "catalogo_otra"):
        _php(tmp_path, f"app/Models/dbsiaw/{t}.php",
             f"namespace App\\Models\\dbsiaw;\nuse Illuminate\\Database\\Eloquent\\Model;\n"
             f"class {t} extends Model {{ protected $table = '{t}'; protected $fillable = ['id','descripcion']; }}\n")
        _php(tmp_path, f"app/Http/Resources/dbsiaw/{t}Resource.php",
             f"namespace App\\Http\\Resources\\dbsiaw;\nclass {t}Resource extends JsonResource "
             f"{{ public function toArray($r) {{ return ['id' => 1, 'descripcion' => 2]; }} }}\n")
    if with_relation_resource:
        _php(tmp_path, "app/Http/Resources/dbsiaw/catalogo_tiposistemaRelationResource.php",
             "namespace App\\Http\\Resources\\dbsiaw;\nclass catalogo_tiposistemaRelationResource extends JsonResource "
             "{ public function toArray($r) { return ['id' => 1, 'descripcion' => 2]; } }\n")
    return tmp_path


def _choices(tmp_path, rmap=None, related=None, learner=None, layout=STANDARD_LAYOUT):
    index = structure_scan.scan_repo(tmp_path)
    return rr.build_choices(
        index, learner or FakeLearner(), rmap, layout, related or {"catalogo_tiposistema": ["tipo_sistema_id"]}
    ), index


def test_proposes_the_existing_relation_resource_with_its_confidence(tmp_path):
    (choice,), _ = _choices(_project(tmp_path))

    assert choice.table == "catalogo_tiposistema" and choice.columns == ["tipo_sistema_id"]
    assert choice.model_selected == TIPO_MODEL and choice.model_exists
    assert choice.resource_selected == TIPO_RR  # el de relación, no el Resource completo
    assert choice.confidence is not None and choice.confidence >= rr.PROPOSE_MIN_SCORE
    assert not choice.remembered
    # las dos opciones especiales van primero y el archivo propuesto está entre las opciones
    assert [o.fqcn for o in choice.resource_options[:2]] == [rr.GENERATE, rr.NONE]
    assert TIPO_RR in [o.fqcn for o in choice.resource_options]
    assert TIPO_R in [o.fqcn for o in choice.resource_options]  # el completo también se puede elegir


def test_proposes_generating_a_new_one_when_the_project_has_nothing_similar(tmp_path):
    _project(tmp_path, with_relation_resource=False)
    (choice,), _ = _choices(tmp_path, related={"vta_pedido": ["x_id"]})
    assert choice.resource_selected == rr.GENERATE
    assert not choice.model_exists  # no hay Model: se usa la convención
    assert choice.model_selected == "App\\Models\\dbvta\\vta_pedido"  # la convención del layout estándar
    assert choice.resource_options[0].label == "(generar nuevo: PedidoRelationResource)"  # nombre del layout estándar


def test_the_layout_convention_is_used_for_the_generated_name(tmp_path):
    custom = STANDARD_LAYOUT.with_placement(
        "relation_resource", RolePlacement("app/Http/Resources/dbsiaw", "{table}RelationResource"), ORIGIN_PROJECT
    )
    (choice,), _ = _choices(_project(tmp_path, with_relation_resource=False), related={"catalogo_nueva": ["x_id"]}, layout=custom)
    assert choice.resource_options[0].label == "(generar nuevo: catalogo_nuevaRelationResource)"


def test_a_remembered_confirmation_comes_preselected_and_wins_over_the_network(tmp_path):
    _project(tmp_path)
    rmap = RelationMap(tmp_path / "mapa")
    rmap.remember("catalogo_tiposistema", "relation_resource", TIPO_R, "app/Http/Resources/dbsiaw/catalogo_tiposistemaResource.php")
    rmap.remember("catalogo_tiposistema", "model", TIPO_MODEL)

    (choice,), _ = _choices(tmp_path, rmap=rmap)
    assert choice.remembered
    assert choice.resource_selected == TIPO_R  # lo confirmado antes, aunque la red prefiera otro


def test_a_remembered_class_missing_from_the_scan_is_still_offered(tmp_path):
    _project(tmp_path)
    rmap = RelationMap(tmp_path / "mapa")
    rmap.remember("catalogo_tiposistema", "relation_resource", "App\\Otro\\Fuera")
    (choice,), _ = _choices(tmp_path, rmap=rmap)
    assert choice.resource_selected == "App\\Otro\\Fuera"
    assert "App\\Otro\\Fuera" in [o.fqcn for o in choice.resource_options]


def test_confirming_saves_to_the_map_and_teaches_the_network(tmp_path):
    _project(tmp_path)
    rmap = RelationMap(tmp_path / "mapa")
    learner = FakeLearner()
    choices, _ = _choices(tmp_path, rmap=rmap, learner=learner)
    choice = choices[0]

    learned = rr.apply_confirmation(
        rmap, learner, choices, [rr.Confirmation("catalogo_tiposistema", TIPO_MODEL, TIPO_RR)],
        module_table="catalogo_parametrosistema", module_relations={"tipo_sistema_id": "catalogo_tiposistema"},
    )

    # se recuerda para CUALQUIER módulo que use esa tabla
    assert rmap.file_for("catalogo_tiposistema", "relation_resource").fqcn == TIPO_RR
    assert rmap.file_for("catalogo_tiposistema", "relation_resource").path.endswith("catalogo_tiposistemaRelationResource.php")
    assert rmap.file_for("catalogo_tiposistema", "model").fqcn == TIPO_MODEL
    assert rmap.get("catalogo_parametrosistema").relations == {"tipo_sistema_id": "catalogo_tiposistema"}

    # la red: 1 positivo (lo elegido) y negativos (lo demás que se le mostró)
    labels = [label for _, label in learner.updates]
    assert labels.count(1.0) == 1 and labels.count(0.0) >= 1
    assert learned == len(learner.updates) and learner.saved == 1

    # el siguiente módulo con una FK a esa tabla la trae confirmada
    (again,), _ = _choices(tmp_path, rmap=rmap)
    assert again.remembered and again.resource_selected == TIPO_RR
    assert choice.resource_selected == TIPO_RR


def test_confirming_what_was_already_remembered_teaches_nothing_new(tmp_path):
    _project(tmp_path)
    rmap = RelationMap(tmp_path / "mapa")
    rmap.remember("catalogo_tiposistema", "relation_resource", TIPO_RR)
    learner = FakeLearner()
    choices, _ = _choices(tmp_path, rmap=rmap, learner=learner)
    assert rr.apply_confirmation(rmap, learner, choices, [rr.Confirmation("catalogo_tiposistema", TIPO_MODEL, TIPO_RR)]) == 0
    assert learner.updates == []


def test_changing_a_remembered_choice_replaces_it_and_teaches(tmp_path):
    _project(tmp_path)
    rmap = RelationMap(tmp_path / "mapa")
    rmap.remember("catalogo_tiposistema", "relation_resource", TIPO_RR)
    learner = FakeLearner()
    choices, _ = _choices(tmp_path, rmap=rmap, learner=learner)
    rr.apply_confirmation(rmap, learner, choices, [rr.Confirmation("catalogo_tiposistema", TIPO_MODEL, TIPO_R)])
    assert rmap.file_for("catalogo_tiposistema", "relation_resource").fqcn == TIPO_R
    assert learner.updates  # corrigir a la red es justo lo que más le enseña


def test_generate_is_not_remembered_until_the_file_exists(tmp_path):
    _project(tmp_path, with_relation_resource=False)
    rmap = RelationMap(tmp_path / "mapa")
    choices, _ = _choices(tmp_path, rmap=rmap, related={"catalogo_nueva": ["x_id"]})
    rr.apply_confirmation(rmap, FakeLearner(), choices, [rr.Confirmation("catalogo_nueva", "App\\Models\\dbsiaw\\catalogo_nueva", rr.GENERATE)])
    assert rmap.file_for("catalogo_nueva", "relation_resource") is None

    rr.remember_generated(rmap, "catalogo_nueva", "App\\Http\\Resources\\dbsiaw\\catalogo_nuevaRelationResource", "app/x.php")
    assert rmap.file_for("catalogo_nueva", "relation_resource").short == "catalogo_nuevaRelationResource"


def test_choosing_no_resource_forgets_a_previous_one(tmp_path):
    _project(tmp_path)
    rmap = RelationMap(tmp_path / "mapa")
    rmap.remember("catalogo_tiposistema", "relation_resource", TIPO_RR)
    choices, _ = _choices(tmp_path, rmap=rmap)
    rr.apply_confirmation(rmap, FakeLearner(), choices, [rr.Confirmation("catalogo_tiposistema", TIPO_MODEL, rr.NONE)])
    assert rmap.file_for("catalogo_tiposistema", "relation_resource") is None


def test_to_targets_translates_the_choices_for_the_generator(tmp_path):
    targets = rr.to_targets(
        [
            rr.Confirmation("a", "M\\A", "R\\ARel"),
            rr.Confirmation("b", "M\\B", rr.NONE),
            rr.Confirmation("c", "M\\C", rr.GENERATE),
        ],
        STANDARD_LAYOUT,
    )
    assert targets["a"].resource_fqcn == "R\\ARel" and not targets["a"].no_resource
    assert targets["b"].no_resource and targets["b"].resource_fqcn is None
    assert targets["c"].resource_fqcn == STANDARD_LAYOUT.fqcn("relation_resource", "c")  # la convención
    assert targets["a"].model_fqcn == "M\\A"
