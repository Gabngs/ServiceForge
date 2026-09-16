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

from generador.gui import MainWindow, ProjectScanDialog, SettingsDialog  # noqa: E402
from generador.project_scan import scan_backend_project  # noqa: E402
from generador.settings import Settings  # noqa: E402


def test_main_window_constructs(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.windowTitle().startswith("Generador Front-Back")
    assert len(window.preview_widgets) == 10
    assert [a.text() for a in window.menuBar().actions()] == ["&Archivo", "&Editar", "A&yuda"]


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
