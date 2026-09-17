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
from generador.db import ConnectionConfig  # noqa: E402
from generador.fk_resolver import FkResolution  # noqa: E402
from generador.gui import ConnectionOutcome, GenerationLogDialog, MainWindow, ProjectScanDialog, SettingsDialog  # noqa: E402
from generador.logs import GenerationLogEntry  # noqa: E402
from generador.project_scan import scan_backend_project  # noqa: E402
from generador.settings import Settings  # noqa: E402


def test_main_window_constructs(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.windowTitle().startswith("Service-Forge")
    assert len(window.preview_widgets) == 13
    assert [a.text() for a in window.menuBar().actions()] == ["&Archivo", "&Editar", "&Logs", "A&yuda"]


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
