"""Smoke tests de la GUI — construcción offscreen, sin abrir una ventana real.

Usa `pytest-qt` (fixture `qtbot`) en vez de instanciar `QApplication` a mano:
maneja el ciclo de vida de la QApplication y el orden de destrucción de los
widgets Qt/C++ al terminar cada test — sin esto, PySide6 en Windows puede
crashear el intérprete al cerrar el proceso (visto en CI: "71 passed" seguido
de un access violation) aunque todos los tests hayan pasado.

No cubre interacción de usuario (eso se prueba a mano), pero atrapa en CI lo
que los tests del generador no pueden: errores de import/construcción en
gui.py (PySide6 nunca se ejercita si solo se testea generador.py).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QPushButton  # noqa: E402

from generador import scaffold  # noqa: E402
from generador.db import Column, ConnectionConfig  # noqa: E402
from generador.fk_resolver import FkResolution  # noqa: E402
from generador.gui import (  # noqa: E402
    _PHP_LARAVEL_COMPLETIONS,
    _CodeEditor,
    ConnectionOutcome,
    GenerationLogDialog,
    MainWindow,
    ModelResourceMatchDialog,
    ProjectScanDialog,
    SettingsDialog,
)
from generador.logs import GenerationLogEntry  # noqa: E402
from generador.match_learner import MatchLearner  # noqa: E402
from generador import match_learner as match_learner_module  # noqa: E402
from generador.project_scan import scan_backend_project  # noqa: E402
from generador.settings import Settings  # noqa: E402


def test_main_window_constructs(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.windowTitle().startswith("Service-Forge")
    assert len(window.preview_widgets) == 13
    assert [a.text() for a in window.menuBar().actions()] == [
        "&Archivo",
        "&Editar",
        "&Logs",
        "&Estándar",
        "A&yuda",
    ]


def test_generation_config_checkboxes_are_grouped(qtbot):
    # Antes estaban sueltos por la ventana (paginación en su propia fila,
    # audit/salida separada mezclados con "Proyectos destino") -- ahora viven
    # juntos en su propio QGroupBox.
    window = MainWindow()
    qtbot.addWidget(window)
    box = window.pagination_checkbox.parentWidget()
    assert box.title() == "Conf. de generación"
    assert window.add_comments_checkbox.parentWidget() is box
    assert window.write_audit_checkbox.parentWidget() is box
    assert window.separate_output_checkbox.parentWidget() is box
    assert window.add_comments_checkbox.isChecked()


def test_connection_lives_in_a_separate_dialog_not_the_main_window(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    # La ventana principal no tiene ningún QGroupBox/form de conexión propio
    # — solo el resumen compacto y el botón que abre el diálogo.
    assert not window.connection_dialog.isVisible()
    assert window.connection_summary_label.text() == "● Sin conexión"
    assert window.connection_dialog_btn.text() == "Conexión…"


def test_connection_dialog_closes_on_successful_connect(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    config = ConnectionConfig(host="127.0.0.1", port=3306, user="root", password="", database="db_test")
    outcome = ConnectionOutcome(tables=["siaw_usuarios"], connection=object())

    window.connection_dialog.show()
    window._on_connection_succeeded(config, "connect", outcome)

    assert not window.connection_dialog.isVisible()
    assert "db_test" in window.connection_summary_label.text()
    assert window.analyze_btn.isEnabled()


def test_connection_dialog_stays_open_on_test_mode(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    config = ConnectionConfig(host="127.0.0.1", port=3306, user="root", password="", database="db_test")
    outcome = ConnectionOutcome(tables=[], connection=None)

    window.connection_dialog.show()
    window._on_connection_succeeded(config, "test", outcome)

    assert window.connection_dialog.isVisible()


def test_theme_toggle_applies(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.settings.theme = "light"
    window._apply_theme()
    assert window.colors["idle"]


def test_settings_dialog_theme_selection(qtbot):
    dialog = SettingsDialog(Settings(theme="dark"))
    qtbot.addWidget(dialog)
    assert dialog.selected_theme() == "dark"
    dialog.theme_combo.setCurrentIndex(1)
    assert dialog.selected_theme() == "light"


def test_project_scan_dialog_constructs(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    result = scan_backend_project(tmp_path)
    dialog = ProjectScanDialog(result, window.colors, window)
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == "Análisis del proyecto backend"


def test_project_scan_dialog_shows_scaffold_section_and_generates_missing_pieces(qtbot, tmp_path, monkeypatch):
    # QMessageBox.information(...) bloquea esperando un clic humano -- en un
    # test offscreen eso cuelga el proceso para siempre. Se reemplaza por un
    # no-op: lo que importa acá es el efecto en disco, no el aviso al usuario.
    from generador import gui as gui_module

    monkeypatch.setattr(gui_module.QMessageBox, "information", lambda *a, **k: None)

    status = scaffold.detect_scaffold_status(tmp_path)
    result = scan_backend_project(tmp_path)

    dialog = ProjectScanDialog(
        result,
        status_colors_for_test(),
        None,
        scaffold_status=status,
        prefijo="siaw",
        project_name="MiProyecto",
    )
    qtbot.addWidget(dialog)

    generate_base_btn = _find_button(dialog, "Generar piezas base faltantes…")
    generate_crud_btn = _find_button(dialog, "Generar CrudService + auditoría…")
    assert generate_base_btn is not None and generate_base_btn.isEnabled()
    assert generate_crud_btn is not None and generate_crud_btn.isEnabled()

    generate_base_btn.click()
    qtbot.wait(50)  # deja que deleteLater() de los widgets viejos se procese
    assert (tmp_path / "app" / "Services" / "AbstractModuleService.php").exists()
    assert (tmp_path / "app" / "Providers" / "RouteServiceProvider.php").exists()
    assert (tmp_path / "app" / "Http" / "Controllers" / "Controller.php").exists()

    generate_crud_btn2 = _find_button(dialog, "Generar CrudService + auditoría…")
    assert generate_crud_btn2 is not None and generate_crud_btn2.isEnabled()
    generate_crud_btn2.click()
    qtbot.wait(50)
    crud_service_path = tmp_path / "app" / "Services" / "CrudService.php"
    assert crud_service_path.exists()
    assert "Auth::user()" in crud_service_path.read_text(encoding="utf-8")

    # Botones ya no habilitados -- todo lo generable ya se generó.
    assert not _find_button(dialog, "Generar piezas base faltantes…").isEnabled()
    assert not _find_button(dialog, "Generar CrudService + auditoría…").isEnabled()


def _find_button(dialog, text):
    for btn in dialog.findChildren(QPushButton):
        if btn.text() == text:
            return btn
    return None


def status_colors_for_test():
    from generador.theme import status_colors

    return status_colors("dark")


def test_fk_combo_allows_manual_relation_on_any_column(qtbot):
    """El combo 'FK -> tabla' permite asignar una relación a CUALQUIER
    columna, no solo a las que terminan en '_id' -- fk_resolver solo detecta
    automáticamente ese sufijo, pero la relación puede vivir en una columna
    con otro nombre (ver generator.relation_method)."""
    from generador.db import Column

    window = MainWindow()
    qtbot.addWidget(window)

    window.config = ConnectionConfig(host="127.0.0.1", port=3306, user="root", password="", database="db_test")
    window.tables = ["siaw_usuarios", "catalogo_tienda", "siaw_roles"]
    window.current_table = "siaw_productos"
    window.current_columns = [
        Column("nombre", "varchar(100)", nullable=False, key="", default=None, extra=""),
        Column("tienda", "int", nullable=False, key="", default=None, extra=""),  # sin sufijo _id
    ]
    window.current_resolutions = {}
    window._populate_grid()

    fk_combo = window.grid.cellWidget(1, 6)
    from PySide6.QtWidgets import QComboBox

    assert isinstance(fk_combo, QComboBox)
    assert fk_combo.currentText() == "(ninguna)"
    assert "tienda" not in window.current_resolutions

    fk_combo.setCurrentText("catalogo_tienda")
    assert window.current_resolutions["tienda"].table == "catalogo_tienda"
    assert window.current_resolutions["tienda"].status == "manual"
    assert window.session_resolved_fks["tienda"] == "catalogo_tienda"

    fk_combo.setCurrentText("(ninguna)")
    assert "tienda" not in window.current_resolutions


def test_fk_combo_preselects_auto_detected_resolution(qtbot):
    from generador.db import Column

    window = MainWindow()
    qtbot.addWidget(window)

    window.config = ConnectionConfig(host="127.0.0.1", port=3306, user="root", password="", database="db_test")
    window.tables = ["siaw_usuarios", "siaw_roles"]
    window.current_table = "siaw_usuarios"
    window.current_columns = [
        Column("rol_id", "int", nullable=False, key="MUL", default=None, extra=""),
    ]
    window.current_resolutions = {
        "rol_id": FkResolution(column="rol_id", base_name="rol", candidates=["siaw_roles"], status="auto", table="siaw_roles")
    }
    window._populate_grid()

    fk_combo = window.grid.cellWidget(0, 6)
    assert fk_combo.currentText() == "siaw_roles"


def test_generation_log_dialog_constructs_empty(qtbot):
    dialog = GenerationLogDialog([])
    qtbot.addWidget(dialog)
    assert dialog.table.rowCount() == 0
    assert not dialog.export_btn.isEnabled()


def _write_legacy_model_and_resource(backend_root):
    model_dir = backend_root / "app" / "Models" / "dbcatalogo"
    model_dir.mkdir(parents=True)
    (model_dir / "catalogo_premiaciones.php").write_text(
        "<?php\nnamespace App\\Models\\dbcatalogo;\nclass catalogo_premiaciones extends Model {}\n",
        encoding="utf-8",
    )
    resource_dir = backend_root / "app" / "Http" / "Resources" / "catalogo"
    resource_dir.mkdir(parents=True)
    resource_path = resource_dir / "PremiacionResource.php"
    resource_path.write_text(
        "<?php\nnamespace App\\Http\\Resources\\catalogo;\n"
        "/**\n * @mixin App\\Models\\dbcatalogo\\catalogo_premiaciones\n */\n"
        "class PremiacionResource extends JsonResource {\n"
        "    public function toArray($request): array\n    {\n        return ['nombre' => $this->nombre];\n    }\n}\n",
        encoding="utf-8",
    )
    return resource_path


def test_model_resource_scan_finds_existing_legacy_resource_after_analyze(qtbot, tmp_path):
    backend_root = tmp_path / "backend"
    resource_path = _write_legacy_model_and_resource(backend_root)

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    window.match_learner = MatchLearner(path=tmp_path / "learner.joblib")
    window.backend_root = backend_root
    window.current_table = "catalogo_premiaciones"
    window.current_columns = [Column("nombre", "varchar(100)", nullable=False, key="", default=None, extra="")]

    window._run_model_resource_scan()

    match = window.current_model_resource_match
    assert match is not None
    assert match.model is not None and match.model.class_name == "catalogo_premiaciones"
    assert match.best is not None and match.best.resource.path == resource_path
    assert "PremiacionResource" in window.model_resource_status_label.text()
    assert window.model_resource_confirm_btn.isVisible()


def test_model_resource_scan_noop_without_backend_root(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.current_table = "catalogo_premiaciones"

    window._run_model_resource_scan()

    assert window.current_model_resource_match is None
    assert window.model_resource_status_label.text() == ""
    assert not window.model_resource_confirm_btn.isVisible()


def test_confirming_resource_match_trains_learner_and_caches_path(qtbot, tmp_path, monkeypatch):
    """El punto central del flujo: confirmar un candidato en el diálogo
    entrena el matcher persistente (sube su score futuro) y cachea la ruta
    del Resource legado para que _on_generate avise antes de pisarlo."""
    # Modelo de fábrica sintético y determinístico, aislado del dataset real
    # (scripts/build_match_dataset.py) -- ese dataset no tiene NINGÚN ejemplo
    # con mixin_match=1 (los proyectos reales usados no declaran @mixin), así
    # que no es representativo para este caso puntual y acoplaría este test
    # de wiring de la GUI a datos que pueden cambiar con el dataset.
    bundled_path = tmp_path / "bundled.joblib"
    X = [[0.9, 0.7, 1.0, 1.0], [0.9, 0.6, 1.0, 1.0]] * 10 + [[0.1, 0.0, 0.0, 0.0], [0.05, 0.0, 0.0, 0.0]] * 10
    y = [1] * 20 + [0] * 20
    factory_learner = MatchLearner(path=bundled_path)
    factory_learner.fit_batch(X, y)
    factory_learner.save()
    monkeypatch.setattr(match_learner_module, "bundled_pretrained_path", lambda: bundled_path)

    backend_root = tmp_path / "backend"
    resource_path = _write_legacy_model_and_resource(backend_root)

    window = MainWindow()
    qtbot.addWidget(window)
    learner_path = tmp_path / "learner.joblib"
    # Vía load(), no el constructor pelado: en la app real, MainWindow.__init__
    # siempre carga por acá -- arranca del modelo de fábrica en vez de una
    # red recién inicializada, que es justo el escenario "un solo ejemplo
    # mueve la predicción al azar" que se quiere evitar (ver match_learner.py).
    window.match_learner = MatchLearner.load(learner_path)
    window.backend_root = backend_root
    window.current_table = "catalogo_premiaciones"
    window.current_columns = [Column("nombre", "varchar(100)", nullable=False, key="", default=None, extra="")]
    window._run_model_resource_scan()

    match = window.current_model_resource_match
    assert match.best is not None
    score_before = match.best.score

    dialog = ModelResourceMatchDialog(match, window)
    qtbot.addWidget(dialog)
    assert dialog._checkboxes[0].isChecked()  # score alto (mixin) -> preseleccionado

    window._apply_model_resource_confirmation(match, dialog.confirmed_indexes())

    assert window.confirmed_resources[("catalogo_premiaciones", "resource")] == resource_path
    assert "confirmado" in window.model_resource_status_label.text().lower()

    reloaded_learner = MatchLearner.load(learner_path)
    assert reloaded_learner.example_count == len(X) + 1  # los del modelo de fábrica + esta confirmación
    rescored = reloaded_learner.score(match.best.features)
    assert rescored >= score_before


def test_generation_log_dialog_constructs_with_entries(qtbot):
    entry = GenerationLogEntry(
        timestamp="2026-01-01T00:00:00+00:00",
        table="siaw_usuarios",
        fk_count=1,
        field_count=4,
        elapsed_seconds=90.0,
        file_count=11,
        line_count=250,
        files=["model", "controller"],
    )
    dialog = GenerationLogDialog([entry])
    qtbot.addWidget(dialog)
    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 1).text() == "siaw_usuarios"
    assert dialog.export_btn.isEnabled()


def test_code_editor_completion_replaces_prefix_without_duplicating_it(qtbot):
    """Reproduce el bug reportado: tipear "dele", elegir "deleted" del
    popup -- antes insertaba el sufijo calculado a mano ("ted") en la
    posición equivocada y terminaba en "deledeleted" en vez de "deleted"."""
    editor = _CodeEditor(_PHP_LARAVEL_COMPLETIONS)
    qtbot.addWidget(editor)
    editor.setPlainText("dele")
    cursor = editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    editor.setTextCursor(cursor)

    editor._insert_completion("deleted")

    assert editor.toPlainText() == "deleted"


def test_code_editor_completion_replaces_prefix_mid_word(qtbot):
    editor = _CodeEditor(_PHP_LARAVEL_COMPLETIONS)
    qtbot.addWidget(editor)
    editor.setPlainText("return dele;")
    cursor = editor.textCursor()
    cursor.setPosition(11)  # justo después de "dele", antes de ";"
    editor.setTextCursor(cursor)

    editor._insert_completion("deleted")

    assert editor.toPlainText() == "return deleted;"


def test_model_resource_dialog_lists_other_existing_files_as_information(qtbot, tmp_path):
    """El modelo de estructura también reconoce Filter/Requests/Service/Controller/rutas: el diálogo los
    muestra para que el desarrollador vea qué ya existe, pero no son confirmables (solo hay checkboxes de Resources)."""
    from generador import model_resource_scan
    from generador.gui import ModelResourceMatchDialog
    from generador.match_learner import StructureLearner

    from test_structure_scan import _COLUMNS, _backend

    match = model_resource_scan.find_candidates(
        "inv_productos", _COLUMNS, _backend(tmp_path), learner=StructureLearner.load(tmp_path / "u.joblib")
    )
    dialog = ModelResourceMatchDialog(match)
    qtbot.addWidget(dialog)

    from PySide6.QtWidgets import QLabel

    text = " | ".join(label.text() for label in dialog.findChildren(QLabel))
    assert "solo informativo" in text
    assert "ProductoService" in text and "ProductoController" in text
    assert len(dialog.confirmed_indexes()) <= len(match.candidates)  # solo los Resources son confirmables


def test_model_resource_dialog_without_other_files_shows_no_info_section(qtbot):
    from generador import model_resource_scan
    from generador.gui import ModelResourceMatchDialog

    dialog = ModelResourceMatchDialog(model_resource_scan.ModelResourceMatch(table="x", model=None))
    qtbot.addWidget(dialog)

    from PySide6.QtWidgets import QLabel

    assert not any("solo informativo" in label.text() for label in dialog.findChildren(QLabel))


def test_connection_dialog_has_no_eloquent_connection_field(qtbot):
    # `$connection` es del proyecto backend (config/database.php), no de la BD
    # conectada: ya no se pide en el diálogo de conexión.
    from PySide6.QtWidgets import QLabel

    window = MainWindow()
    qtbot.addWidget(window)
    labels = [w.text() for w in window.connection_dialog.findChildren(QLabel)]
    assert not any("$connection" in text for text in labels)
    assert not hasattr(window, "connection_name_input")
    # ...y sí está entre los "Proyectos destino".
    assert window.connection_name_combo.parentWidget().title() == "Proyectos destino"


def test_eloquent_connections_are_filled_from_the_backend_project(qtbot, tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "database.php").write_text(
        "<?php return ['connections' => ['mysql' => [], 'mysql_dbsiaw' => [], 'mysql_dbsip' => []]];",
        encoding="utf-8",
    )
    window = MainWindow()
    qtbot.addWidget(window)
    window.backend_root = tmp_path
    window.database_input.setText("dbsiaw")

    window._refresh_eloquent_connections()

    combo = window.connection_name_combo
    assert [combo.itemText(i) for i in range(combo.count())] == ["mysql", "mysql_dbsiaw", "mysql_dbsip"]
    assert combo.currentText() == "mysql_dbsiaw"  # sugerida por la BD conectada
    assert window._eloquent_connection_name() == "mysql_dbsiaw"

    # Refrescar de nuevo no pisa lo que el desarrollador ya eligió.
    combo.setCurrentText("mysql_dbsip")
    window._refresh_eloquent_connections()
    assert combo.currentText() == "mysql_dbsip"


def test_eloquent_connection_falls_back_to_database_name_without_backend(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.database_input.setText("dbsiaw")
    assert window._eloquent_connection_name() == "dbsiaw"
    window.database_input.setText("")
    assert window._eloquent_connection_name() == "mysql"


def test_eloquent_connection_allows_free_text(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.connection_name_combo.setEditText("mysql_otra")
    window.connection_name_combo.lineEdit().editingFinished.emit()
    assert window._eloquent_connection_name() == "mysql_otra"


def _searchable(qtbot, items):
    from generador.gui import SearchableComboBox

    combo = SearchableComboBox()
    qtbot.addWidget(combo)
    combo.addItems(items)
    return combo


def test_searchable_combo_completer_filters_by_substring_ignoring_case(qtbot):
    combo = _searchable(qtbot, ["catalogo_tienda", "catalogo_usuario", "sip_personal", "auth_user"])
    completer = combo.completer()
    completer.setCompletionPrefix("USU")
    shown = [completer.completionModel().index(i, 0).data() for i in range(completer.completionCount())]
    assert shown == ["catalogo_usuario"]  # coincide en el medio del nombre, sin distinguir mayúsculas

    completer.setCompletionPrefix("catalogo")
    assert completer.completionCount() == 2


def test_searchable_combo_commits_a_valid_or_unique_match(qtbot):
    combo = _searchable(qtbot, ["catalogo_tienda", "catalogo_usuario", "sip_personal"])

    combo.lineEdit().setText("SIP_PERSONAL")  # exacto sin distinguir mayúsculas
    combo.lineEdit().editingFinished.emit()
    assert combo.currentText() == "sip_personal"

    combo.lineEdit().setText("usuar")  # fragmento que solo está en un ítem
    combo.lineEdit().editingFinished.emit()
    assert combo.currentText() == "catalogo_usuario"


def test_searchable_combo_reverts_invalid_or_ambiguous_text(qtbot):
    combo = _searchable(qtbot, ["catalogo_tienda", "catalogo_usuario", "sip_personal"])
    combo.setCurrentText("sip_personal")

    combo.lineEdit().setText("catalogo")  # dos candidatas: ambiguo
    combo.lineEdit().editingFinished.emit()
    assert combo.currentText() == "sip_personal"

    combo.lineEdit().setText("no_existe")
    combo.lineEdit().editingFinished.emit()
    assert combo.currentText() == "sip_personal"

    combo.lineEdit().setText("")
    combo.lineEdit().editingFinished.emit()
    assert combo.currentText() == "sip_personal"


def test_searchable_combo_typing_does_not_change_index_until_committed(qtbot):
    combo = _searchable(qtbot, ["a_uno", "b_dos", "c_tres"])
    changes = []
    combo.currentIndexChanged.connect(changes.append)

    for partial in ("b", "b_", "b_d"):
        combo.lineEdit().setText(partial)
    assert changes == []  # escribir para filtrar no dispara nada

    combo.lineEdit().editingFinished.emit()
    assert combo.currentText() == "b_dos"
    assert changes == [1]


def test_fk_combo_ignores_partial_text_while_typing(qtbot):
    from generador.db import Column

    window = MainWindow()
    qtbot.addWidget(window)
    window.config = ConnectionConfig(host="127.0.0.1", port=3306, user="root", password="", database="db_test")
    window.tables = ["auth_group", "auth_group_permissions", "catalogo_tienda"]
    window.current_table = "productos"
    window.current_columns = [Column("tienda", "int", nullable=False, key="", default=None, extra="")]
    window.current_resolutions = {}
    window._populate_grid()

    fk_combo = window.grid.cellWidget(0, 6)
    # Se escribe "auth_group_permissions" pasando por "auth_group", que también
    # es una tabla válida: mientras se escribe no se debe aplicar ninguna.
    for partial in ("a", "auth_group", "auth_group_perm"):
        fk_combo.lineEdit().setText(partial)
    assert "tienda" not in window.current_resolutions

    fk_combo.lineEdit().setText("auth_group_permissions")
    fk_combo.lineEdit().editingFinished.emit()
    assert window.current_resolutions["tienda"].table == "auth_group_permissions"


def test_main_table_selector_is_searchable(qtbot):
    from generador.gui import SearchableComboBox

    window = MainWindow()
    qtbot.addWidget(window)
    assert isinstance(window.table_combo, SearchableComboBox)
    assert window.table_combo.isEditable()


def test_searchable_combo_typing_replaces_current_value_and_selects_from_popup(qtbot):
    """Flujo real: el combo muestra el valor actual, se empieza a escribir sin
    borrarlo antes, el popup queda filtrado y con flecha + Enter se elige."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    combo = _searchable(qtbot, ["actualizacion_archivos", "auth_group", "catalogo_tienda", "catalogo_usuario"])
    combo.show()
    combo.activateWindow()
    qtbot.waitUntil(combo.isActiveWindow)
    combo.lineEdit().setFocus()
    qtbot.wait(20)  # deja correr el selectAll diferido de la entrada al campo

    QTest.keyClicks(combo.lineEdit(), "usu")
    assert combo.lineEdit().text() == "usu"  # reemplazó "actualizacion_archivos", no se agregó al final

    popup = combo.completer().popup()
    assert popup.isVisible()
    assert popup.model().rowCount() == 1  # solo catalogo_usuario

    QTest.keyClick(popup, Qt.Key_Down)
    QTest.keyClick(popup, Qt.Key_Return)
    assert combo.currentText() == "catalogo_usuario"
    assert combo.currentIndex() == 3
