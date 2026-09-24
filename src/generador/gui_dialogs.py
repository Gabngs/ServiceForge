"""Diálogos de la estructura del proyecto y de las relaciones (parte de la GUI, ver gui.py).

  - `ProjectStructureDialog`: compara la estructura del estándar con la que el modelo detectó en el
    proyecto y deja decidir, rol por rol, cuál usar (o escribir otra a mano).
  - `RelationsDialog`: antes de generar, para cada tabla relacionada (FK), qué Model y qué
    RelationResource usa el código. La red propone con su confianza; el desarrollador decide.
  - `RelationMapDialog`: las notas del mapa del proyecto (lo confirmado antes), con exportar/importar.
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import layout as layout_module
from . import relation_map, relation_resolution
from .layout import ORIGIN_MANUAL, ORIGIN_PROJECT, ORIGIN_STANDARD, RolePlacement, StructureLayout
from .relation_map import RelationMap
from .relation_resolution import Confirmation, RelationChoice
from .structure_profile import ProjectStructure
from .widgets import SearchableComboBox

USE_STANDARD = "Estándar"
USE_PROJECT = "Proyecto"
USE_CUSTOM = "Personalizado"

_DIR_RE = re.compile(r"^[\w{}./\-]*$")
_NAME_RE = re.compile(r"^[\w{}.\-]+$")


def _valid_placement(directory: str, name: str) -> str | None:
    """Mensaje de error si la carpeta o el nombre no sirven; None si están bien."""
    directory = directory.strip().replace("\\", "/")
    if directory.startswith("/") or ":" in directory or ".." in directory.split("/"):
        return "La carpeta tiene que ser relativa a la raíz del backend (sin '/' inicial, ':' ni '..')."
    if not _DIR_RE.match(directory):
        return "La carpeta tiene caracteres no válidos."
    if not _NAME_RE.match(name.strip()):
        return "El nombre tiene que tener letras, números, '_' o tokens como {table}."
    return None


class _ElidedLabel(QLabel):
    """Etiqueta que recorta por la IZQUIERDA lo que no entra (`…/dbsiaw/{table}Resource.php`): en una
    ruta lo que importa es el final. El texto completo queda en `fullText()` y en el tooltip."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._full = ""
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def setFullText(self, text: str) -> None:  # noqa: N802 — estilo Qt
        self._full = text
        self.setToolTip(text)
        self._elide()

    def fullText(self) -> str:  # noqa: N802
        return self._full

    def resizeEvent(self, event) -> None:  # noqa: N802 — override Qt
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        width = self.width()
        super().setText(self.fontMetrics().elidedText(self._full, Qt.ElideLeft, width - 6) if width > 20 else self._full)


# ================================================================ estructura
class ProjectStructureDialog(QDialog):
    """Estructura del estándar vs. la detectada en el proyecto, rol por rol.

    El generador nunca impone una estructura de carpetas: si el proyecto ya tiene la suya, se puede
    generar dentro de ella; si no tiene ejemplos de un tipo de archivo, el estándar es el punto de partida.
    Nada se aplica hasta que se guarda."""

    _COLUMNS = ["Archivo", "Estándar", "Detectado en el proyecto", "Usar", "Se generaría en", "Carpeta", "Nombre"]

    def __init__(
        self,
        structure: ProjectStructure,
        current: StructureLayout,
        *,
        first_time: bool,
        example_table: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Estructura del proyecto")
        self.setMinimumSize(1100, 520)
        self.structure = structure
        self.example_table = example_table
        self.auto_registered = False
        self._combos: dict[str, QComboBox] = {}
        self._dirs: dict[str, QLineEdit] = {}
        self._names: dict[str, QLineEdit] = {}
        self._examples: dict[str, _ElidedLabel] = {}

        layout = QVBoxLayout(self)
        detected = structure.detected_roles()
        intro = QLabel(
            f"Se analizó el proyecto ({structure.models} Models). Se detectó dónde guarda "
            f"{len(detected)} de {len(layout_module.ROLES)} tipos de archivo. Compará con el estándar y elegí "
            "cuál usar para cada uno, o escribí otra carpeta/nombre. Los tokens son {table}, {Table}, "
            "{prefijo}, {Prefijo}, {modulo} y {Modulo}. \"Se generaría en\" usa "
            f"la tabla de ejemplo «{example_table}»."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.table = QTableWidget(len(layout_module.ROLES), len(self._COLUMNS))
        self.table.setHorizontalHeaderLabels(self._COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setTextElideMode(Qt.ElideLeft)  # en una ruta importa el final
        layout.addWidget(self.table, stretch=1)

        for row, role in enumerate(layout_module.ROLES):
            self._build_row(row, role, current, first_time)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        # Anchos fijos: las rutas largas se recortan por la izquierda (el texto completo está en el
        # tooltip) para que "Usar" y "Se generaría en" queden a la vista; las cajas de edición al final.
        for column, width in ((0, 125), (1, 300), (2, 330), (3, 105), (4, 330), (5, 230)):
            self.table.setColumnWidth(column, width)
        header.setStretchLastSection(True)
        for row in range(self.table.rowCount()):
            # el texto completo (la columna recorta por la izquierda), antes de los ejemplos si los hay
            for column in (1, 2):
                item = self.table.item(row, column)
                examples = item.toolTip()
                item.setToolTip(item.text() + (f"\n\n{examples}" if examples else ""))

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #e5534b;")
        layout.addWidget(self.error_label)

        buttons = QHBoxLayout()
        self.auto_btn = QPushButton("Auto-registrar (usar lo detectado)")
        self.auto_btn.setToolTip(
            "Usa la estructura del proyecto en cada tipo de archivo que ya tiene, y el estándar en los que "
            "todavía no tiene ninguno. Aplica y guarda."
        )
        self.auto_btn.clicked.connect(self._on_auto_register)
        self.auto_btn.setEnabled(bool(detected))
        self.standard_btn = QPushButton("Usar todo el estándar")
        self.standard_btn.clicked.connect(lambda: self._set_all(USE_STANDARD))
        buttons.addWidget(self.auto_btn)
        buttons.addWidget(self.standard_btn)
        buttons.addStretch()
        box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        box.button(QDialogButtonBox.Save).setText("Guardar")
        box.button(QDialogButtonBox.Cancel).setText("Cancelar")
        box.accepted.connect(self._on_accept)
        box.rejected.connect(self.reject)
        buttons.addWidget(box)
        layout.addLayout(buttons)

    # ------------------------------------------------------------- filas
    def _standard(self, role: str) -> RolePlacement:
        return layout_module.STANDARD_LAYOUT.placement(role)

    def _detected(self, role: str) -> RolePlacement | None:
        return self.structure.evidence[role].placement

    def _build_row(self, row: int, role: str, current: StructureLayout, first_time: bool) -> None:
        standard = self._standard(role)
        detected = self._detected(role)
        evidence = self.structure.evidence[role]

        self.table.setItem(row, 0, QTableWidgetItem(layout_module.ROLE_LABELS[role]))
        self.table.setItem(row, 1, QTableWidgetItem(standard.describe()))
        if detected is None:
            text = "— sin archivos —" if evidence.samples == 0 else f"— sin patrón claro ({evidence.samples} archivos) —"
        elif evidence.inferred_from is not None:
            text = f"{detected.describe()}   (deducido de {layout_module.ROLE_LABELS[evidence.inferred_from]})"
        else:
            text = f"{detected.describe()}   ({evidence.matching} de {evidence.samples})"
            if evidence.approximate:
                text += "  ~"
        item = QTableWidgetItem(text)
        if evidence.examples:
            item.setToolTip("Ejemplos:\n" + "\n".join(evidence.examples))
        self.table.setItem(row, 2, item)

        combo = QComboBox()
        combo.addItems([USE_STANDARD, USE_PROJECT, USE_CUSTOM])
        if detected is None:
            combo.model().item(1).setEnabled(False)
        origin = current.origin(role)
        if origin == ORIGIN_MANUAL:
            initial = USE_CUSTOM
        elif origin == ORIGIN_PROJECT and detected is not None:
            initial = USE_PROJECT
        elif first_time and detected is not None:
            initial = USE_PROJECT  # primera vez: lo que el proyecto ya usa es la mejor propuesta
        else:
            initial = USE_STANDARD
        self._combos[role] = combo
        self.table.setCellWidget(row, 3, combo)

        directory = QLineEdit()
        name = QLineEdit()
        self._dirs[role] = directory
        self._names[role] = name
        self.table.setCellWidget(row, 5, directory)
        self.table.setCellWidget(row, 6, name)

        example = _ElidedLabel()
        self._examples[role] = example
        self.table.setCellWidget(row, 4, example)

        if initial == USE_CUSTOM:
            placement = current.placement(role)
            combo.setCurrentText(USE_CUSTOM)
            directory.setText(placement.directory)
            name.setText(placement.name)
            self._refresh_example(role)
        else:
            combo.setCurrentText(initial)
            self._fill_from_choice(role)

        combo.currentTextChanged.connect(lambda _text, r=role: self._on_combo_changed(r))
        directory.textEdited.connect(lambda _text, r=role: self._on_text_edited(r))
        name.textEdited.connect(lambda _text, r=role: self._on_text_edited(r))

    def _fill_from_choice(self, role: str) -> None:
        choice = self._combos[role].currentText()
        placement = self._detected(role) if choice == USE_PROJECT else self._standard(role)
        if choice == USE_CUSTOM or placement is None:
            self._refresh_example(role)
            return
        self._dirs[role].setText(placement.directory)
        self._names[role].setText(placement.name)
        self._refresh_example(role)

    def _on_combo_changed(self, role: str) -> None:
        self._fill_from_choice(role)

    def _on_text_edited(self, role: str) -> None:
        combo = self._combos[role]
        if combo.currentText() != USE_CUSTOM:
            combo.blockSignals(True)
            combo.setCurrentText(USE_CUSTOM)
            combo.blockSignals(False)
        self._refresh_example(role)

    def _refresh_example(self, role: str) -> None:
        directory = self._dirs[role].text().strip()
        name = self._names[role].text().strip()
        if not name:
            self._examples[role].setFullText("")
            return
        path = f"{layout_module.expand(directory, self.example_table).strip('/')}/" if directory else ""
        self._examples[role].setFullText(f"{path}{layout_module.expand(name, self.example_table)}.php")

    def _set_all(self, choice: str) -> None:
        for role in layout_module.ROLES:
            self._combos[role].setCurrentText(choice)

    def _on_auto_register(self) -> None:
        for role in layout_module.ROLES:
            self._combos[role].setCurrentText(USE_PROJECT if self._detected(role) is not None else USE_STANDARD)
        self.auto_registered = True
        self._on_accept()

    # ------------------------------------------------------------ resultado
    def _placement_for(self, role: str) -> tuple[RolePlacement, str]:
        choice = self._combos[role].currentText()
        if choice == USE_PROJECT and self._detected(role) is not None:
            return self._detected(role), ORIGIN_PROJECT
        if choice == USE_STANDARD:
            return self._standard(role), ORIGIN_STANDARD
        return RolePlacement(self._dirs[role].text().strip().replace("\\", "/"), self._names[role].text().strip()), ORIGIN_MANUAL

    def result_layout(self) -> StructureLayout:
        result = StructureLayout(origins={})
        for role in layout_module.ROLES:
            placement, origin = self._placement_for(role)
            result = result.with_placement(role, placement, origin)
        return result

    def decision(self) -> str:
        origins = [self._placement_for(role)[1] for role in layout_module.ROLES]
        if all(o == ORIGIN_STANDARD for o in origins):
            return relation_map.DECISION_STANDARD
        if ORIGIN_MANUAL in origins:
            return relation_map.DECISION_CUSTOM
        return relation_map.DECISION_PROJECT

    def _on_accept(self) -> None:
        for role in layout_module.ROLES:
            problem = _valid_placement(self._dirs[role].text(), self._names[role].text())
            if problem:
                self.error_label.setText(f"{layout_module.ROLE_LABELS[role]}: {problem}")
                return
        self.error_label.setText("")
        self.accept()


# ============================================================== relaciones
class RelationsDialog(QDialog):
    """Antes de generar: qué Model y qué RelationResource usa el código para cada tabla relacionada.

    La red propone (con su confianza) y el desarrollador decide: lo que confirma acá se guarda en el
    mapa del proyecto y le enseña a la red; una sugerencia sin confirmar no se guarda nunca."""

    _COLUMNS = ["Relación", "Model", "RelationResource", "Estado"]

    def __init__(self, choices: list[RelationChoice], *, module_table: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Relaciones de {module_table}")
        self.setMinimumSize(1180, 320)
        self.choices = choices
        self._model_combos: list[SearchableComboBox] = []
        self._resource_combos: list[SearchableComboBox] = []
        self._status: list[QLabel] = []

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Antes de generar, confirmá qué archivos usa el código para cada relación. El generador ya no "
            "supone un RelationResource por el nombre de la tabla: propone el que existe en el proyecto y vos "
            "decidís. Lo que confirmes se guarda y vale para cualquier módulo con una FK a esa tabla."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.table = QTableWidget(len(choices), len(self._COLUMNS))
        self.table.setHorizontalHeaderLabels(self._COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table, stretch=1)

        for row, choice in enumerate(choices):
            self._build_row(row, choice)
        # Anchos fijos para que "Estado" (lo que hay que leer para confirmar) quede a la vista: los
        # combos recortan los nombres largos, el texto completo está en el desplegable.
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        for column, width in ((0, 170), (1, 290), (2, 430)):
            self.table.setColumnWidth(column, width)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        for row in range(len(choices)):
            self.table.setRowHeight(row, 50)

        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.button(QDialogButtonBox.Ok).setText("Confirmar y generar")
        box.button(QDialogButtonBox.Cancel).setText("Cancelar")
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    @staticmethod
    def _option_text(option: relation_resolution.ClassOption) -> str:
        parts = [option.label]
        if option.score is not None:
            parts.append(f"{option.score:.0%}")
        if option.path:
            parts.append(option.path)
        return "  ·  ".join(parts)

    def _fill_combo(self, combo: SearchableComboBox, options: list[relation_resolution.ClassOption], selected: str) -> None:
        for option in options:
            combo.addItem(self._option_text(option), option.fqcn)
        index = combo.findData(selected)
        if index >= 0:
            combo.setCurrentIndex(index)
        combo.lineEdit().setCursorPosition(0)  # que se vea el nombre de la clase, no el final de la ruta

    def _build_row(self, row: int, choice: RelationChoice) -> None:
        name = QTableWidgetItem(f"{choice.table}\n({', '.join(choice.columns)})")
        self.table.setItem(row, 0, name)

        model_combo = SearchableComboBox()
        self._fill_combo(model_combo, choice.model_options, choice.model_selected)
        self.table.setCellWidget(row, 1, model_combo)
        self._model_combos.append(model_combo)

        resource_combo = SearchableComboBox()
        self._fill_combo(resource_combo, choice.resource_options, choice.resource_selected)
        self.table.setCellWidget(row, 2, resource_combo)
        self._resource_combos.append(resource_combo)

        status = QLabel("")
        status.setWordWrap(True)
        self.table.setCellWidget(row, 3, status)
        self._status.append(status)
        for combo in (model_combo, resource_combo):
            combo.currentIndexChanged.connect(lambda _i, c=combo: c.lineEdit().setCursorPosition(0))
        resource_combo.currentIndexChanged.connect(lambda _i, r=row: self._refresh_status(r))
        model_combo.currentIndexChanged.connect(lambda _i, r=row: self._refresh_status(r))
        self._refresh_status(row)

    def _refresh_status(self, row: int) -> None:
        choice = self.choices[row]
        selected = self._resource_combos[row].currentData()
        option = next((o for o in choice.resource_options if o.fqcn == selected), None)
        if selected == relation_resolution.GENERATE:
            text = "Se generará un RelationResource nuevo para esta tabla."
        elif selected == relation_resolution.NONE:
            text = "Sin Resource: la columna sale plana, sin whenLoaded()."
        elif choice.remembered and selected == choice.resource_selected:
            text = "✓ Confirmado antes. ¿Sigue siendo el correcto?"
        elif option is not None and option.score is not None and selected == choice.resource_selected:
            text = f"Sugerido por la red ({option.score:.0%}). ¿Es el correcto?"
        else:
            text = "Elegido a mano."
        if not choice.model_exists and self._model_combos[row].currentData() == choice.model_selected:
            text += " El Model no existe: se usa la convención."
        self._status[row].setText(text)

    def confirmations(self) -> list[Confirmation]:
        return [
            Confirmation(
                table=choice.table,
                model_fqcn=str(self._model_combos[row].currentData() or choice.model_selected),
                resource=str(self._resource_combos[row].currentData() or relation_resolution.GENERATE),
            )
            for row, choice in enumerate(self.choices)
        ]


# ==================================================================== mapa
class RelationMapDialog(QDialog):
    """Las notas del mapa del proyecto (lo confirmado antes). Solo lectura: se confirma desde
    el diálogo de relaciones; acá se ve, se exporta a otra carpeta/PC y se importa."""

    def __init__(self, rmap: RelationMap, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Mapa del proyecto")
        self.setMinimumSize(880, 520)
        self.rmap = rmap

        layout = QVBoxLayout(self)
        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        body = QHBoxLayout()
        self.notes = QListWidget()
        self.notes.setMaximumWidth(280)
        self.notes.currentTextChanged.connect(self._show_note)
        body.addWidget(self.notes)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        font = self.preview.font()
        font.setFamily("Consolas")
        self.preview.setFont(font)
        body.addWidget(self.preview, stretch=1)
        layout.addLayout(body, stretch=1)

        row = QHBoxLayout()
        self.export_btn = QPushButton("Exportar mapa…")
        self.import_btn = QPushButton("Importar mapa…")
        self.open_btn = QPushButton("Abrir carpeta")
        row.addWidget(self.export_btn)
        row.addWidget(self.import_btn)
        row.addWidget(self.open_btn)
        row.addStretch()
        close = QPushButton("Cerrar")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        layout.addLayout(row)
        self.reload()

    def reload(self) -> None:
        names = self.rmap.tables()
        has_layout = (self.rmap.folder / relation_map.LAYOUT_NOTE).exists()
        self.notes.clear()
        if has_layout:
            self.notes.addItem(relation_map.LAYOUT_NOTE)
        self.notes.addItems(names)
        self.summary.setText(
            f"{len(names)} tabla(s) confirmada(s) en el mapa · carpeta: {self.rmap.folder}\n"
            "Cada nota es un .md con [[wikilinks]]: se puede abrir en Obsidian y editar a mano. "
            "Se llena sola con lo que confirmás al generar."
        )
        if self.notes.count():
            self.notes.setCurrentRow(0)
        else:
            self.preview.setPlainText("Todavía no hay nada confirmado. Se guarda al confirmar las relaciones antes de generar.")

    def _show_note(self, name: str) -> None:
        if not name:
            return
        path = self.rmap.folder / (name if name.endswith(".md") else f"{name}.md")
        try:
            self.preview.setPlainText(path.read_text(encoding="utf-8"))
        except OSError:
            self.preview.setPlainText("")


def confirm_overwrite_edits(parent: QWidget, titles: list[str]) -> bool:
    """Las pestañas del preview que el desarrollador editó a mano y que cambian por lo que se acaba de confirmar."""
    answer = QMessageBox.question(
        parent,
        "Editaste estas pestañas a mano",
        "Lo que confirmaste en las relaciones cambia estos archivos, pero los editaste a mano:\n\n"
        + "\n".join(f"- {t}" for t in titles)
        + "\n\n¿Reemplazarlos por la versión con las relaciones confirmadas? Si elegís No se conserva "
        "tu texto (puede quedar con imports de una clase que no confirmaste).",
    )
    return answer == QMessageBox.Yes


def default_export_dir() -> Path:
    return Path.home() / "Documents"
