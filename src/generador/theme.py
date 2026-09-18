"""Stylesheet (QSS) para modernizar la GUI — el look por defecto de Qt Widgets
es el que el usuario describió como "de los 90". Dos temas planos (oscuro y
claro), sin depender de ningún paquete de theming externo.
"""

from __future__ import annotations

_DARK = {
    "background": "#15161c",
    "surface": "#1d1f28",
    "surface_alt": "#242732",
    "border": "#2e313d",
    "text": "#e7e8ee",
    "text_muted": "#9598ab",
    "accent": "#6d5efc",
    "accent_hover": "#7f72ff",
    "accent_pressed": "#5b4de0",
    "success": "#35c675",
    "error": "#f2555a",
    "warning": "#f2b544",
    "code_bg": "#101116",
    "code_text": "#d7d9e6",
}

_LIGHT = {
    "background": "#f4f5f9",
    "surface": "#ffffff",
    "surface_alt": "#eceef4",
    "border": "#d7dae3",
    "text": "#1c1e26",
    "text_muted": "#666a7d",
    "accent": "#5b4de0",
    "accent_hover": "#4c3fd1",
    "accent_pressed": "#4136b3",
    "success": "#1f9d5c",
    "error": "#d13b40",
    "warning": "#b8790a",
    "code_bg": "#ffffff",
    "code_text": "#1c1e26",
}

_PALETTES = {"dark": _DARK, "light": _LIGHT}


def status_colors(mode: str = "dark") -> dict[str, str]:
    p = _PALETTES.get(mode, _DARK)
    return {
        "idle": p["text_muted"],
        "busy": p["warning"],
        "ok": p["success"],
        "error": p["error"],
    }


def palette(mode: str = "dark") -> dict[str, str]:
    """Paleta completa del tema (background/surface/text/accent/code_*/...) —
    a diferencia de `status_colors()`, que solo expone los 4 colores de estado."""
    return dict(_PALETTES.get(mode, _DARK))


# Compatibilidad con el código existente que importa STATUS_COLORS a nivel de módulo
# (asume tema oscuro — el que se usa como default al arrancar).
STATUS_COLORS = status_colors("dark")


def build_stylesheet(mode: str = "dark") -> str:
    p = _PALETTES.get(mode, _DARK)
    return f"""
* {{
    font-family: "Segoe UI", "Cantarell", sans-serif;
    font-size: 10pt;
    color: {p['text']};
}}

QMainWindow, QWidget {{
    background-color: {p['background']};
}}

QGroupBox {{
    background-color: {p['surface']};
    border: 1px solid {p['border']};
    border-radius: 8px;
    margin-top: 14px;
    padding: 12px;
    font-weight: 600;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: {p['text_muted']};
}}

QLabel {{
    background: transparent;
}}

QMenuBar {{
    background-color: {p['surface']};
    border-bottom: 1px solid {p['border']};
}}

QMenuBar::item:selected {{
    background-color: {p['surface_alt']};
}}

QMenu {{
    background-color: {p['surface']};
    border: 1px solid {p['border']};
}}

QMenu::item:selected {{
    background-color: {p['accent']};
    color: white;
}}

QPushButton {{
    background-color: {p['surface_alt']};
    border: 1px solid {p['border']};
    border-radius: 6px;
    padding: 6px 14px;
}}

QPushButton:hover {{
    border-color: {p['accent']};
}}

QPushButton:pressed {{
    background-color: {p['border']};
}}

QPushButton:disabled {{
    color: {p['text_muted']};
    border-color: {p['border']};
    background-color: {p['surface']};
}}

QPushButton[accent="true"] {{
    background-color: {p['accent']};
    border: 1px solid {p['accent']};
    color: white;
    font-weight: 600;
}}

QPushButton[accent="true"]:hover {{
    background-color: {p['accent_hover']};
}}

QPushButton[accent="true"]:pressed {{
    background-color: {p['accent_pressed']};
}}

QLineEdit, QComboBox, QSpinBox {{
    background-color: {p['surface_alt']};
    border: 1px solid {p['border']};
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: {p['accent']};
}}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border: 1px solid {p['accent']};
}}

QLineEdit:disabled, QComboBox:disabled {{
    color: {p['text_muted']};
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

QCheckBox {{
    spacing: 8px;
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid {p['border']};
    background-color: {p['surface_alt']};
}}

QCheckBox::indicator:checked {{
    background-color: {p['accent']};
    border-color: {p['accent']};
}}

QTableWidget {{
    background-color: {p['surface']};
    alternate-background-color: {p['surface_alt']};
    gridline-color: {p['border']};
    border: 1px solid {p['border']};
    border-radius: 6px;
    selection-background-color: {p['accent']};
    selection-color: white;
}}

QHeaderView::section {{
    background-color: {p['surface_alt']};
    color: {p['text_muted']};
    padding: 6px;
    border: none;
    border-bottom: 1px solid {p['border']};
    font-weight: 600;
}}

QTreeWidget, QTextBrowser {{
    background-color: {p['surface']};
    border: 1px solid {p['border']};
    border-radius: 6px;
    selection-background-color: {p['accent']};
    selection-color: white;
}}

QTreeWidget::item {{
    padding: 3px 2px;
}}

QTreeWidget::item:selected {{
    background-color: {p['accent']};
    color: white;
}}

QSplitter::handle {{
    background-color: {p['border']};
}}

QSplitter::handle:hover {{
    background-color: {p['accent']};
}}

QTabWidget::pane {{
    border: 1px solid {p['border']};
    border-radius: 8px;
    top: -1px;
    background-color: {p['surface']};
}}

QTabBar::tab {{
    background: transparent;
    color: {p['text_muted']};
    padding: 8px 14px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}}

QTabBar::tab:selected {{
    color: {p['text']};
    background-color: {p['surface']};
    border-bottom: 2px solid {p['accent']};
}}

QTabBar::tab:hover {{
    color: {p['text']};
}}

QPlainTextEdit {{
    background-color: {p['code_bg']};
    color: {p['code_text']};
    border: 1px solid {p['border']};
    border-radius: 6px;
    padding: 8px;
    selection-background-color: {p['accent']};
}}

QScrollBar:vertical {{
    background: {p['surface']};
    width: 10px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: {p['border']};
    border-radius: 5px;
    min-height: 24px;
}}

QScrollBar::handle:vertical:hover {{
    background: {p['accent']};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: {p['surface']};
    height: 10px;
}}

QScrollBar::handle:horizontal {{
    background: {p['border']};
    border-radius: 5px;
    min-width: 24px;
}}

QDialog {{
    background-color: {p['background']};
}}

QMessageBox {{
    background-color: {p['surface']};
}}
"""


# Compatibilidad con el código existente (main() usaba la constante directamente).
STYLESHEET = build_stylesheet("dark")
