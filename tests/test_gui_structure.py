"""GUI de la estructura del proyecto y de las relaciones (gui_dialogs.py + su cableado en MainWindow)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path  # noqa: E402

from PySide6.QtWidgets import QDialog, QMessageBox  # noqa: E402

from generador import layout, relation_map, relation_resolution, structure_profile  # noqa: E402
from generador.db import Column  # noqa: E402
from generador.fk_resolver import FkResolution  # noqa: E402
from generador.gui import MainWindow  # noqa: E402
from generador.gui_dialogs import ProjectStructureDialog, RelationMapDialog, RelationsDialog  # noqa: E402
from generador.layout import STANDARD_LAYOUT  # noqa: E402
from generador.relation_map import RelationMap  # noqa: E402

TIPO_RR = "App\\Http\\Resources\\dbsiaw\\catalogo_tiposistemaRelationResource"


class FakeLearner:
    def __init__(self):
        self.updates = []

    def score(self, features):
        return features.get("name_sim_norm", 0.0)

    def update(self, features, label, save=True):
        self.updates.append((features, label))

    def save(self):
        pass


def _php(root: Path, rel: str, body: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("<?php\n" + body, encoding="utf-8")


def _siaw_like_backend(root: Path, *, with_relation_resource: bool = True) -> Path:
    for t in ("catalogo_tiposistema", "catalogo_zona", "catalogo_rol", "catalogo_cargo"):
        _php(root, f"app/Models/dbsiaw/{t}.php",
             f"namespace App\\Models\\dbsiaw;\nuse Illuminate\\Database\\Eloquent\\Model;\n"
             f"class {t} extends Model {{ protected $table = '{t}'; protected $fillable = ['id','descripcion']; }}\n")
        _php(root, f"app/Http/Resources/dbsiaw/{t}Resource.php",
             f"namespace App\\Http\\Resources\\dbsiaw;\nclass {t}Resource extends JsonResource "
             f"{{ public function toArray($r) {{ return ['id' => 1, 'descripcion' => 2]; }} }}\n")
        _php(root, f"app/Services/{t}Service.php", f"namespace App\\Services;\nclass {t}Service {{}}\n")
        _php(root, f"app/Http/Controllers/Api/dbsiaw/{t}Controller.php",
             f"namespace App\\Http\\Controllers\\Api\\dbsiaw;\nclass {t}Controller extends Controller {{}}\n")
        _php(root, f"routes/{t}.php",
             f"use App\\Http\\Controllers\\Api\\dbsiaw\\{t}Controller;\nRoute::apiResource('{t}', {t}Controller::class);\n")
    if with_relation_resource:
        _php(root, "app/Http/Resources/dbsiaw/catalogo_tiposistemaRelationResource.php",
             "namespace App\\Http\\Resources\\dbsiaw;\nclass catalogo_tiposistemaRelationResource extends JsonResource "
             "{ public function toArray($r) { return ['id' => 1, 'descripcion' => 2]; } }\n")
    return root


# ----------------------------------------------------- ProjectStructureDialog
def _structure(tmp_path):
    return structure_profile.detect_layout(_siaw_like_backend(tmp_path))


def test_structure_dialog_shows_standard_vs_detected_and_preselects_the_project(qtbot, tmp_path):
    structure = _structure(tmp_path)
    dialog = ProjectStructureDialog(structure, STANDARD_LAYOUT, first_time=True, example_table="catalogo_nueva")
    qtbot.addWidget(dialog)

    assert dialog.table.rowCount() == len(layout.ROLES)
    row = layout.ROLES.index("service")
    assert dialog.table.item(row, 1).text() == "app/Services/{Modulo}Service.php"  # el estándar
    assert dialog.table.item(row, 2).text().startswith("app/Services/{table}Service.php")  # lo detectado
    assert dialog._combos["service"].currentText() == "Proyecto"  # primera vez: lo que el proyecto ya usa
    # el rol sin archivos en el proyecto (no tiene traits de validación) no ofrece "Proyecto" y queda en el estándar
    assert dialog._combos["trait"].currentText() == "Estándar"
    assert not dialog._combos["trait"].model().item(1).isEnabled()
    assert "sin archivos" in dialog.table.item(layout.ROLES.index("trait"), 2).text()
    # "Se generaría en" usa la tabla de ejemplo
    assert dialog._examples["service"].fullText() == "app/Services/catalogo_nuevaService.php"
    assert dialog.decision() == relation_map.DECISION_PROJECT
    assert dialog.result_layout().placement("service") == structure.layout.placement("service")


def test_structure_dialog_editing_a_row_makes_it_custom(qtbot, tmp_path):
    dialog = ProjectStructureDialog(_structure(tmp_path), STANDARD_LAYOUT, first_time=True, example_table="a_b")
    qtbot.addWidget(dialog)
    dialog._dirs["service"].setText("src/Svc")
    dialog._dirs["service"].textEdited.emit("src/Svc")
    assert dialog._combos["service"].currentText() == "Personalizado"
    placement, origin = dialog._placement_for("service")
    assert placement.directory == "src/Svc" and origin == layout.ORIGIN_MANUAL
    assert dialog.decision() == relation_map.DECISION_CUSTOM
    assert dialog._examples["service"].fullText() == "src/Svc/a_bService.php"


def test_structure_dialog_use_standard_and_auto_register(qtbot, tmp_path):
    structure = _structure(tmp_path)
    dialog = ProjectStructureDialog(structure, STANDARD_LAYOUT, first_time=True, example_table="a_b")
    qtbot.addWidget(dialog)

    dialog._set_all("Estándar")
    assert dialog.decision() == relation_map.DECISION_STANDARD
    assert dialog.result_layout().is_standard()

    dialog._on_auto_register()  # lo detectado donde hay, el estándar donde no
    assert dialog.result() == QDialog.Accepted and dialog.auto_registered
    result = dialog.result_layout()
    assert result.placement("controller") == structure.layout.placement("controller")
    assert result.origin("controller") == "proyecto"
    assert result.placement("trait") == STANDARD_LAYOUT.placement("trait")
    assert result.origin("trait") == "estandar"


def test_structure_dialog_refuses_an_invalid_folder(qtbot, tmp_path):
    dialog = ProjectStructureDialog(_structure(tmp_path), STANDARD_LAYOUT, first_time=False, example_table="a_b")
    qtbot.addWidget(dialog)
    dialog._dirs["model"].setText("../fuera")
    dialog._dirs["model"].textEdited.emit("../fuera")
    dialog._on_accept()
    assert dialog.result() != QDialog.Accepted
    assert "Model" in dialog.error_label.text()

    dialog._dirs["model"].setText("app/Models")
    dialog._on_accept()
    assert dialog.result() == QDialog.Accepted


def test_structure_dialog_reopens_with_a_saved_custom_layout(qtbot, tmp_path):
    saved = STANDARD_LAYOUT.with_placement(
        "service", layout.RolePlacement("src/Svc", "{table}Svc"), layout.ORIGIN_MANUAL
    )
    dialog = ProjectStructureDialog(_structure(tmp_path), saved, first_time=False, example_table="a_b")
    qtbot.addWidget(dialog)
    assert dialog._combos["service"].currentText() == "Personalizado"
    assert dialog._dirs["service"].text() == "src/Svc" and dialog._names["service"].text() == "{table}Svc"
    assert dialog._combos["model"].currentText() == "Estándar"  # first_time=False: no se pisa lo decidido


# ------------------------------------------------------------ RelationsDialog
def _choices_for(tmp_path, related, rmap=None, learner=None):
    from generador import structure_scan

    return relation_resolution.build_choices(
        structure_scan.scan_repo(tmp_path), learner or FakeLearner(), rmap, STANDARD_LAYOUT, related
    )


def test_relations_dialog_lists_each_relation_with_the_proposal(qtbot, tmp_path):
    _siaw_like_backend(tmp_path)
    choices = _choices_for(tmp_path, {"catalogo_tiposistema": ["tipo_sistema_id"], "vta_pedido": ["pedido_id"]})
    dialog = RelationsDialog(choices, module_table="catalogo_parametrosistema")
    qtbot.addWidget(dialog)

    assert dialog.table.rowCount() == 2
    by_table = {c.table: i for i, c in enumerate(dialog.choices)}
    assert dialog._resource_combos[by_table["catalogo_tiposistema"]].currentData() == TIPO_RR
    assert "Sugerido por la red" in dialog._status[by_table["catalogo_tiposistema"]].text()
    # sin nada parecido en el proyecto: se propone generar uno y se avisa que el Model no existe
    nuevo = by_table["vta_pedido"]
    assert dialog._resource_combos[nuevo].currentData() == relation_resolution.GENERATE
    assert "Se generará un RelationResource nuevo" in dialog._status[nuevo].text()
    assert "El Model no existe" in dialog._status[nuevo].text()

    confirmations = dialog.confirmations()
    assert {c.table: c.resource for c in confirmations}["catalogo_tiposistema"] == TIPO_RR


def test_relations_dialog_status_follows_the_selection_and_is_searchable(qtbot, tmp_path):
    _siaw_like_backend(tmp_path)
    rmap = RelationMap(tmp_path / "mapa")
    rmap.remember("catalogo_tiposistema", "relation_resource", TIPO_RR)
    choices = _choices_for(tmp_path, {"catalogo_tiposistema": ["tipo_sistema_id"]}, rmap=rmap)
    dialog = RelationsDialog(choices, module_table="x_y")
    qtbot.addWidget(dialog)

    assert "Confirmado antes" in dialog._status[0].text()
    combo = dialog._resource_combos[0]
    from generador.widgets import SearchableComboBox

    assert isinstance(combo, SearchableComboBox) and isinstance(dialog._model_combos[0], SearchableComboBox)

    combo.setCurrentIndex(combo.findData(relation_resolution.NONE))
    assert "sale plana" in dialog._status[0].text()
    combo.setCurrentIndex(combo.findData(relation_resolution.GENERATE))
    assert "nuevo" in dialog._status[0].text()
    other = next(i for i in range(combo.count()) if combo.itemData(i) not in (TIPO_RR, relation_resolution.GENERATE, relation_resolution.NONE))
    combo.setCurrentIndex(other)
    assert dialog._status[0].text() == "Elegido a mano."


# ---------------------------------------------------------- RelationMapDialog
def test_relation_map_dialog_lists_and_shows_the_notes(qtbot, tmp_path):
    rmap = RelationMap(tmp_path / "mapa")
    rmap.remember("catalogo_tiposistema", "relation_resource", TIPO_RR, "app/x.php")
    rmap.save_layout(STANDARD_LAYOUT, relation_map.DECISION_STANDARD)
    dialog = RelationMapDialog(rmap)
    qtbot.addWidget(dialog)

    names = [dialog.notes.item(i).text() for i in range(dialog.notes.count())]
    assert names == ["_estructura.md", "catalogo_tiposistema"]
    dialog.notes.setCurrentRow(1)
    assert "[[catalogo_tiposistemaRelationResource]]" in dialog.preview.toPlainText()
    assert "1 tabla(s) confirmada(s)" in dialog.summary.text()


def test_relation_map_dialog_when_empty(qtbot, tmp_path):
    dialog = RelationMapDialog(RelationMap(tmp_path / "vacio"))
    qtbot.addWidget(dialog)
    assert "Todavía no hay nada confirmado" in dialog.preview.toPlainText()


# ---------------------------------------------------------- MainWindow: flujo
def _window(qtbot, monkeypatch, tmp_path, *, with_relation_resource=True):
    backend = _siaw_like_backend(tmp_path / "siaw-laravel-backend", with_relation_resource=with_relation_resource)
    (tmp_path / "front").mkdir()
    window = MainWindow()
    qtbot.addWidget(window)
    window.match_learner = FakeLearner()  # no tocar el modelo aprendido del usuario (%APPDATA%)
    window.backend_root = backend
    window.frontend_root = tmp_path / "front"
    window.relation_map = RelationMap(tmp_path / "mapa")
    window.structure_layout = structure_profile.detect_layout(backend).layout
    window.layout_decision = relation_map.DECISION_PROJECT

    window.config = None
    window.tables = ["catalogo_tiposistema", "vta_pedido"]
    window.current_table = "catalogo_parametrosistema"
    window.current_columns = [
        Column("nombre", "varchar(60)", nullable=False, key="", default=None, extra=""),
        Column("tipo_sistema_id", "int", nullable=False, key="MUL", default=None, extra=""),
    ]
    window.current_resolutions = {
        "tipo_sistema_id": FkResolution("tipo_sistema_id", "tipo_sistema", ["catalogo_tiposistema"], "auto", "catalogo_tiposistema")
    }
    window._populate_grid()
    window._on_update_preview()

    # los diálogos modales se responden solos
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.Ok))
    return window


def test_generate_asks_for_relations_and_uses_the_confirmed_relation_resource(qtbot, monkeypatch, tmp_path):
    window = _window(qtbot, monkeypatch, tmp_path)
    asked = []
    monkeypatch.setattr(RelationsDialog, "exec", lambda self: asked.append(self.choices) or QDialog.Accepted)

    window._on_generate()

    assert len(asked) == 1 and asked[0][0].table == "catalogo_tiposistema"  # preguntó antes de generar
    backend = window.backend_root
    resource = (backend / "app/Http/Resources/dbsiaw/catalogo_parametrosistemaResource.php").read_text(encoding="utf-8")
    # usa el RelationResource que EXISTE en el proyecto, no uno inventado a partir del nombre de la tabla
    assert "use App\\Http\\Resources\\dbsiaw\\catalogo_tiposistemaRelationResource;" in resource
    assert "new catalogo_tiposistemaRelationResource(" in resource
    assert "TiposistemaRelationResource" not in resource.replace("catalogo_tiposistemaRelationResource", "")
    # y escribió en la estructura del proyecto
    assert (backend / "app/Http/Controllers/Api/dbsiaw/catalogo_parametrosistemaController.php").exists()
    assert (backend / "routes/catalogo_parametrosistema.php").exists()
    assert not (backend / "app/Http/Resources/Siaw").exists()  # nada de la estructura estándar

    # lo confirmado quedó guardado, y también lo que se generó de este módulo
    rmap = window.relation_map
    assert rmap.file_for("catalogo_tiposistema", "relation_resource").fqcn == TIPO_RR
    assert rmap.file_for("catalogo_parametrosistema", "resource").short == "catalogo_parametrosistemaResource"
    assert rmap.get("catalogo_parametrosistema").relations == {"tipo_sistema_id": "catalogo_tiposistema"}
    assert window.match_learner.updates  # la red aprendió de la confirmación


def test_generate_writes_nothing_when_the_relations_dialog_is_cancelled(qtbot, monkeypatch, tmp_path):
    window = _window(qtbot, monkeypatch, tmp_path)
    monkeypatch.setattr(RelationsDialog, "exec", lambda self: QDialog.Rejected)
    window._on_generate()
    assert not (window.backend_root / "app/Http/Controllers/Api/dbsiaw/catalogo_parametrosistemaController.php").exists()
    assert window.relation_map.tables() == []  # sin confirmar no se guarda nada
    assert window.match_learner.updates == []


def test_generate_creates_the_missing_relation_resource_and_remembers_it(qtbot, monkeypatch, tmp_path):
    window = _window(qtbot, monkeypatch, tmp_path, with_relation_resource=False)
    window.current_resolutions = {
        "tipo_sistema_id": FkResolution("tipo_sistema_id", "pedido", ["vta_pedido"], "auto", "vta_pedido")
    }
    window._populate_grid()
    window._on_update_preview()
    monkeypatch.setattr(RelationsDialog, "exec", lambda self: QDialog.Accepted)  # acepta la propuesta

    window._on_generate()

    generated = window.backend_root / "app/Http/Resources/dbsiaw/vta_pedidoRelationResource.php"
    assert generated.exists()  # el proyecto no tenía nada parecido: se generó uno mínimo, con la estructura del proyecto
    assert "class vta_pedidoRelationResource extends JsonResource" in generated.read_text(encoding="utf-8")
    resource = (window.backend_root / "app/Http/Resources/dbsiaw/catalogo_parametrosistemaResource.php").read_text(encoding="utf-8")
    assert "new vta_pedidoRelationResource(" in resource
    # recién ahora, que el archivo existe, se recuerda
    assert window.relation_map.file_for("vta_pedido", "relation_resource").short == "vta_pedidoRelationResource"


def test_relation_targets_reset_on_a_new_analysis_and_module_without_fks_skips_the_dialog(qtbot, monkeypatch, tmp_path):
    window = _window(qtbot, monkeypatch, tmp_path)
    window.current_resolutions = {}
    window._populate_grid()
    window._on_update_preview()
    called = []
    monkeypatch.setattr(RelationsDialog, "exec", lambda self: called.append(1) or QDialog.Accepted)
    window._on_generate()
    assert called == []  # sin FKs no hay nada que confirmar
    assert (window.backend_root / "routes/catalogo_parametrosistema.php").exists()


def test_edited_preview_tabs_are_not_overwritten_without_asking(qtbot, monkeypatch, tmp_path):
    window = _window(qtbot, monkeypatch, tmp_path)
    window.preview_widgets["resource"].setPlainText("// editado a mano\n")

    def choose_no_resource(self):
        combo = self._resource_combos[0]
        combo.setCurrentIndex(combo.findData(relation_resolution.NONE))  # cambia el Resource generado
        return QDialog.Accepted

    monkeypatch.setattr(RelationsDialog, "exec", choose_no_resource)
    asked = []
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: asked.append(a[2]) or QMessageBox.No))

    assert window._confirm_relations()
    assert window.preview_widgets["resource"].toPlainText() == "// editado a mano\n"  # dijo que No: se conserva
    assert len(asked) == 1 and "los editaste a mano" in asked[0]


def test_choosing_the_backend_loads_the_saved_structure(qtbot, monkeypatch, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    backend = _siaw_like_backend(tmp_path / "mi-backend")
    base = tmp_path / "mapas"
    saved = RelationMap(base / "mi-backend")
    saved.save_layout(STANDARD_LAYOUT.with_placement("service", layout.RolePlacement("x", "{table}S"), layout.ORIGIN_MANUAL), "personalizado")
    monkeypatch.setattr(relation_map, "default_maps_dir", lambda: base)

    window.backend_root = backend
    window._load_project_state()
    assert window.layout_decision == "personalizado"
    assert window.structure_layout.placement("service").directory == "x"
    assert window.relation_map.folder == base / "mi-backend"


def test_first_analysis_asks_for_the_structure_once_and_does_not_nag_after_cancel(qtbot, monkeypatch, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.backend_root = _siaw_like_backend(tmp_path / "b")
    window.relation_map = RelationMap(tmp_path / "mapa")
    opened = []
    monkeypatch.setattr(ProjectStructureDialog, "exec", lambda self: opened.append(1) or QDialog.Rejected)

    window._ensure_structure_decided(example_table="a_b")
    window._ensure_structure_decided(example_table="c_d")
    assert opened == [1]  # canceló: no vuelve a preguntar en la sesión
    assert window.layout_decision is None and window.structure_layout.is_standard()

    monkeypatch.setattr(ProjectStructureDialog, "exec", lambda self: QDialog.Accepted)
    window._open_structure_dialog(example_table="a_b")  # desde el botón "Estructura…": siempre se puede
    assert window.layout_decision == relation_map.DECISION_PROJECT
    assert window.relation_map.load_layout()[1] == "proyecto"  # se guardó en el mapa
    assert window.structure_layout.placement("service").directory == "app/Services"


def test_map_menu_and_structure_button_exist(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    menu = next(a for a in window.menuBar().actions() if a.text() == "&Mapa").menu()
    assert [a.text() for a in menu.actions() if not a.isSeparator()] == [
        "Mapa del proyecto…", "Estructura del proyecto…", "Exportar mapa…", "Importar mapa…",
    ]
