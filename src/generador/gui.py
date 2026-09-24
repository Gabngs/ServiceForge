"""Prototipo de interfaz gráfica — PySide6.

Flujo (ver "Interfaz gráfica" en Script Generador Backend.md):
  conexión -> analizar tabla -> resolver FKs ambiguas -> mapear columnas
  (incluir / tiny) -> preview EDITABLE -> confirmar -> generar archivos
  dentro de la estructura real de los proyectos backend/frontend elegidos.

Ningún archivo se escribe hasta que el usuario aprieta "Generar archivos" —
y lo que se escribe es el contenido de cada pestaña de preview en ese momento
(el desarrollador puede corregir el código generado antes de confirmar).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QStringListModel, QThread, Signal
from PySide6.QtGui import QAction, QColor, QSyntaxHighlighter, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSplitter,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import (
    __version__,
    backup,
    db,
    fk_resolver,
    generator,
    logs,
    mapping,
    match_learner,
    migration_import,
    model_resource_scan,
    naming,
    project_scan,
    scaffold,
    standard_docs,
    table_mapping,
)
from .settings import Settings
from .theme import build_stylesheet, palette, status_colors

_GRID_COLUMNS = ["Campo", "Tipo SQL", "Nullable", "Incluir", "Relación", "Tiny", "FK -> tabla"]

_FK_STATUS_LABELS = {
    "auto": "auto",
    "resolved_from_cache": "caché local",
    "from_mapping_file": "mapeo importado",
    "manual": "manual",
}

# Detección automática de FK exige que la columna termine en "_id" (ver
# fk_resolver.find_fk_candidates) — pero una relación puede vivir en una
# columna con otro nombre (ej. legado, o una convención distinta). El combo
# de "FK -> tabla" permite asignar manualmente CUALQUIER columna a una
# tabla, sin esa restricción — no es una opción, es el mismo mecanismo que
# ya resuelve columnas ambiguas, solo que a mano y para cualquier columna.
_FK_NONE_LABEL = "(ninguna)"

_PREVIEW_TABS: list[tuple[str, str]] = [
    ("model", "Model.php"),
    ("service", "{Modulo}Service.php"),
    ("filters", "{table}Filters.php"),
    ("store_request", "Store{Modulo}Request.php"),
    ("update_request", "Update{Modulo}Request.php"),
    ("trait", "Validates{Modulo}.php"),
    ("resource", "{Modulo}Resource.php"),
    ("relation_resource", "{Modulo}RelationResource.php"),
    ("tiny_resource", "{Modulo}TinyResource.php"),
    ("controller", "{table}Controller.php"),
    ("routes_module", "routes/modules/{modulo}.php"),
    ("interfaces", "{modulo}.interface.ts"),
    ("audit_user", "audit-user.interface.ts"),
]

# Autocompletado "por palabras" del preview (sin IA/Copilot): combina esta
# lista curada de PHP/Laravel/Eloquent con las palabras que ya aparecen en
# el propio documento — ver _CodeEditor más abajo.
_PHP_LARAVEL_COMPLETIONS = [
    "abstract", "class", "extends", "implements", "interface", "trait", "use",
    "namespace", "public", "protected", "private", "static", "final", "const",
    "function", "return", "void", "array", "string", "int", "float", "bool",
    "null", "true", "false", "self", "parent", "new", "instanceof", "throw",
    "try", "catch", "finally", "if", "else", "elseif", "foreach", "as", "while",
    "match", "fn", "readonly", "enum", "yield", "clone",
    "Model", "SoftDeletes", "HasFactory",
    "Illuminate\\Database\\Eloquent\\Model",
    "Illuminate\\Database\\Eloquent\\Builder",
    "Illuminate\\Database\\Eloquent\\SoftDeletes",
    "Illuminate\\Database\\Eloquent\\Relations\\BelongsTo",
    "Illuminate\\Database\\Eloquent\\Relations\\HasMany",
    "Illuminate\\Database\\Eloquent\\Relations\\HasOne",
    "Illuminate\\Database\\Eloquent\\Relations\\BelongsToMany",
    "Illuminate\\Http\\Request",
    "Illuminate\\Http\\JsonResponse",
    "Illuminate\\Support\\Facades\\DB",
    "Illuminate\\Support\\Facades\\Auth",
    "Illuminate\\Support\\Facades\\Route",
    "Illuminate\\Support\\Str",
    "Illuminate\\Validation\\Rule",
    "belongsTo", "hasMany", "hasOne", "belongsToMany", "morphTo", "morphMany",
    "fillable", "guarded", "casts", "hidden", "appends", "with", "withCount",
    "where", "whereIn", "whereNotIn", "whereNull", "whereHas", "orderBy",
    "orderByDesc", "paginate", "simplePaginate", "findOrFail", "firstOrFail",
    "firstOrCreate", "updateOrCreate", "create", "update", "delete", "save",
    "all", "get", "first", "pluck", "count", "exists", "toArray", "toJson",
    "validate", "validated", "rules", "messages", "authorize", "input", "only",
    "except", "json", "response", "now", "Carbon", "collect", "compact",
    "dd", "dump", "abort", "abort_if", "abort_unless", "auth", "request",
]

_TS_INTERFACE_COMPLETIONS = [
    "export", "interface", "extends", "type", "readonly", "string", "number",
    "boolean", "null", "undefined", "Array", "Record", "Partial", "Omit",
    "Pick", "Date", "IAuditUser", "created_by", "updated_by", "deleted_by",
]


@dataclass
class ConnectionOutcome:
    tables: list[str]
    connection: object | None  # conexión pymysql abierta, solo en modo "connect"


class ConnectionWorker(QThread):
    """Corre `db.connect()` (y opcionalmente `SHOW TABLES`) fuera del hilo de la UI
    para que la ventana no se congele mientras espera el `connect_timeout`."""

    succeeded = Signal(object)  # ConnectionOutcome
    failed = Signal(str)

    def __init__(self, config: db.ConnectionConfig, mode: str, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.mode = mode  # "connect" | "test"

    def run(self) -> None:
        try:
            conn = db.connect(self.config)
        except Exception as exc:  # noqa: BLE001 — se muestra al usuario tal cual
            self.failed.emit(str(exc))
            return

        try:
            if self.mode == "test":
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                conn.close()
                self.succeeded.emit(ConnectionOutcome(tables=[], connection=None))
            else:
                tables = db.list_tables(conn)
                self.succeeded.emit(ConnectionOutcome(tables=tables, connection=conn))
        except Exception as exc:  # noqa: BLE001
            conn.close()
            self.failed.emit(str(exc))


class BackupWorker(QThread):
    """Corre `backup.run_backup()` fuera del hilo de la UI y reenvía cada línea
    de progreso de mysqldump (`--verbose`) para que la ventana no se congele ni
    parezca colgada durante un dump largo."""

    progress = Signal(str)
    succeeded = Signal(Path)
    failed = Signal(str, str)  # message, stderr (stderr vacío si fue MysqldumpNotFoundError)

    def __init__(
        self,
        config: db.ConnectionConfig,
        output_path: Path,
        scope: backup.BackupScope,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.output_path = output_path
        self.scope = scope

    def run(self) -> None:
        try:
            path = backup.run_backup(
                self.config, self.output_path, scope=self.scope, on_output=self.progress.emit
            )
        except backup.MysqldumpNotFoundError as exc:
            self.failed.emit(str(exc), "")
        except backup.BackupFailedError as exc:
            self.failed.emit(str(exc), exc.stderr)
        else:
            self.succeeded.emit(path)


class BackupOptionsDialog(QDialog):
    """Elegir qué volcar antes de arrancar: estructura+datos, solo estructura o
    solo datos — y si se quiere ver el detalle tipo consola durante el proceso."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Opciones de backup")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)

        scope_group = QGroupBox("Contenido")
        scope_layout = QVBoxLayout(scope_group)
        self.full_radio = QRadioButton("Estructura y datos (backup completo)")
        self.schema_radio = QRadioButton("Solo estructura (sin datos)")
        self.data_radio = QRadioButton("Solo datos (sin estructura)")
        self.full_radio.setChecked(True)
        self._scope_buttons = QButtonGroup(self)
        for btn in (self.full_radio, self.schema_radio, self.data_radio):
            self._scope_buttons.addButton(btn)
            scope_layout.addWidget(btn)
        layout.addWidget(scope_group)

        self.show_log_checkbox = QCheckBox("Mostrar el detalle del proceso (consola) mientras corre")
        self.show_log_checkbox.setChecked(False)
        layout.addWidget(self.show_log_checkbox)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Iniciar backup")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def scope(self) -> backup.BackupScope:
        if self.schema_radio.isChecked():
            return "schema"
        if self.data_radio.isChecked():
            return "data"
        return "full"

    def show_log(self) -> bool:
        return self.show_log_checkbox.isChecked()


class BackupProgressDialog(QDialog):
    """Diálogo no bloqueante para la UI: barra de progreso (por tabla procesada,
    si se conoce el total) con un log tipo consola opcional/plegable debajo, y el
    error completo mostrado ahí mismo si el backup falla en vez de una ventana
    aparte que tapa el detalle."""

    _TABLE_RE = r"-- (?:Retrieving table structure for table|Dumping data for table) `(.+?)`"

    def __init__(self, total_tables: int, show_log: bool, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Backup en curso…")
        self.setMinimumWidth(560)
        self.setModal(True)

        self._table_re = re.compile(self._TABLE_RE)
        self._seen_tables: set[str] = set()
        self._total_tables = total_tables

        layout = QVBoxLayout(self)

        self.status_label = QLabel("Conectando…")
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        if total_tables > 0:
            self.progress_bar.setRange(0, total_tables)
        else:
            self.progress_bar.setRange(0, 0)  # indeterminado: no sabemos cuántas tablas hay
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.toggle_log_btn = QPushButton("Ver detalle ▾" if not show_log else "Ocultar detalle ▴")
        self.toggle_log_btn.clicked.connect(self._toggle_log)
        layout.addWidget(self.toggle_log_btn)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setVisible(show_log)
        self.log.setMinimumHeight(220)
        layout.addWidget(self.log)

        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #ff6b6b;")
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        self.close_btn = QPushButton("Cerrar")
        self.close_btn.setEnabled(False)
        self.close_btn.clicked.connect(self.accept)
        layout.addWidget(self.close_btn)

        self.resize(620, 260 if show_log else 160)

    def _toggle_log(self) -> None:
        visible = not self.log.isVisible()
        self.log.setVisible(visible)
        self.toggle_log_btn.setText("Ocultar detalle ▴" if visible else "Ver detalle ▾")
        self.resize(self.width(), 260 if visible else 160)

    def append_line(self, line: str) -> None:
        self.log.appendPlainText(line)
        match = self._table_re.search(line)
        if match:
            table = match.group(1)
            if table not in self._seen_tables:
                self._seen_tables.add(table)
                if self._total_tables > 0:
                    self.progress_bar.setValue(len(self._seen_tables))
            self.status_label.setText(f"Procesando tabla: {table}")

    def show_error(self, message: str, stderr: str) -> None:
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.status_label.setText("Backup falló.")
        self.error_label.setText(f"{message}\n\n{stderr}" if stderr else message)
        self.error_label.setVisible(True)
        self.log.setVisible(True)
        self.toggle_log_btn.setVisible(False)
        self.close_btn.setEnabled(True)
        self.resize(self.width(), 420)

    def show_success(self, path: Path) -> None:
        if self._total_tables > 0:
            self.progress_bar.setValue(self._total_tables)
        else:
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(1)
        self.status_label.setText(f"Backup completo: {path}")
        self.close_btn.setEnabled(True)

    def closeEvent(self, event) -> None:  # noqa: N802 — override Qt
        # mysqldump no es cancelable desde acá (quedaría corriendo huérfano si se
        # cierra el diálogo a mitad de camino): se ignora el cierre manual mientras
        # el worker sigue corriendo (close_btn deshabilitado hasta que termine).
        if not self.close_btn.isEnabled():
            event.ignore()
        else:
            event.accept()


class FkResolutionDialog(QDialog):
    """Bloqueante: el desarrollador elige la tabla para cada FK ambigua o sin candidatos."""

    def __init__(self, ambiguous: list[fk_resolver.FkResolution], tables: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Resolución manual de FKs ambiguas")
        self.setMinimumWidth(480)
        self._tables = tables
        self._combos: dict[str, QComboBox] = {}
        self._manual: dict[str, QLineEdit] = {}

        layout = QVBoxLayout(self)
        for res in ambiguous:
            group = QGroupBox(f"Campo: {res.column}")
            form = QFormLayout(group)

            if res.candidates:
                hint = QLabel(f"{len(res.candidates)} tablas candidatas: {', '.join(res.candidates)}")
            else:
                hint = QLabel("No se encontró ninguna tabla candidata.")
            hint.setWordWrap(True)
            form.addRow(hint)

            combo = QComboBox()
            combo.addItem("(elegir)")
            combo.addItems(res.candidates or tables)
            self._combos[res.column] = combo
            form.addRow("Elegir tabla:", combo)

            manual = QLineEdit()
            manual.setPlaceholderText("o escribir manualmente el nombre de la tabla")
            self._manual[res.column] = manual
            form.addRow("Manual:", manual)

            layout.addWidget(group)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def resolutions(self) -> dict[str, str]:
        """column -> tabla elegida (solo columnas efectivamente resueltas)."""
        result: dict[str, str] = {}
        for column, manual in self._manual.items():
            manual_value = manual.text().strip()
            if manual_value:
                result[column] = manual_value
                continue
            combo = self._combos[column]
            if combo.currentIndex() > 0:
                result[column] = combo.currentText()
        return result


class ModelResourceMatchDialog(QDialog):
    """Confirmar o corregir qué Resource(s) ya existentes en el proyecto
    corresponden al Model de la tabla analizada — ver model_resource_scan.py.
    Cada elección acá es un ejemplo de entrenamiento para el matcher
    persistente (match_learner.py): lo tildado refuerza ese candidato, lo
    mostrado y NO tildado lo penaliza, así el próximo parecido puntúa mejor.

    Son checkboxes, no radio: un proyecto legado puede tener Resources con
    roles distintos (completo/relación/tiny) bajo nombres que no siguen la
    convención de esta herramienta — más de uno puede ser correcto a la vez.
    """

    def __init__(self, match: "model_resource_scan.ModelResourceMatch", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Model/Resource existentes — {match.table}")
        self.setMinimumWidth(560)
        self.match = match
        self._checkboxes: list[QCheckBox] = []

        layout = QVBoxLayout(self)

        if match.model is not None:
            layout.addWidget(QLabel(f"Model detectado: {match.model.class_name}  ({match.model.path})"))
        else:
            layout.addWidget(QLabel("No se encontró ningún Model existente para esta tabla — se generará uno nuevo."))

        if match.candidates:
            layout.addWidget(QLabel(
                "Tildá los Resources que realmente correspondan a este Model (puede ser más de uno — "
                "completo / de relación / tiny — o ninguno si no hay ningún Resource existente):"
            ))
            for candidate in match.candidates:
                resource = candidate.resource
                checkbox = QCheckBox(
                    f"{resource.class_name}  [{resource.role}]  —  confianza {candidate.score:.0%}  —  {resource.path}"
                )
                checkbox.setChecked(candidate.score >= 0.65)
                self._checkboxes.append(checkbox)
                layout.addWidget(checkbox)
        else:
            layout.addWidget(QLabel("No se encontró ningún Resource candidato — se generará uno nuevo."))

        # Los demás roles (Filter, Requests, Service, Controller, rutas...): el modelo de
        # estructura también los reconoce, pero la generación todavía no los usa -- se muestran
        # solo para que el desarrollador vea qué ya existe en su proyecto antes de generar.
        others = {role: found[0] for role, found in match.others.items() if found and found[0].score >= 0.5}
        if others:
            info = QLabel("Otros archivos ya existentes que parecen de este Model (solo informativo, no se confirman):")
            info.setWordWrap(True)
            layout.addWidget(info)
            for role, best in others.items():
                layout.addWidget(QLabel(f"  {role}: {best.file.class_name}  —  confianza {best.score:.0%}  —  {best.file.path}"))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def confirmed_indexes(self) -> set[int]:
        """Índices (en `match.candidates`) de los Resources tildados por el usuario."""
        return {i for i, cb in enumerate(self._checkboxes) if cb.isChecked()}


class MigrationImportDialog(QDialog):
    """Fuente alternativa a la conexión a BD: parsea una migración Laravel de
    `Schema::create(...)` (ver migration_import.py) — el desarrollador elige
    entre un archivo del proyecto o texto pegado a mano (ej. copiado del editor
    sin tener el proyecto abierto en esta misma máquina)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Importar desde migración")
        self.setMinimumWidth(560)
        self.parsed: migration_import.ParsedMigration | None = None

        layout = QVBoxLayout(self)

        source_row = QHBoxLayout()
        self.file_radio = QRadioButton("Archivo de migración (.php)")
        self.paste_radio = QRadioButton("Pegar texto de la migración")
        self.file_radio.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.file_radio)
        group.addButton(self.paste_radio)
        source_row.addWidget(self.file_radio)
        source_row.addWidget(self.paste_radio)
        source_row.addStretch()
        layout.addLayout(source_row)

        file_row = QHBoxLayout()
        self.file_path_input = QLineEdit()
        self.file_path_input.setPlaceholderText(r"C:\proyecto\database\migrations\...\create_x_table.php")
        browse_btn = QPushButton("Elegir…")
        browse_btn.clicked.connect(self._on_browse)
        file_row.addWidget(self.file_path_input)
        file_row.addWidget(browse_btn)
        layout.addLayout(file_row)

        self.paste_text = QPlainTextEdit()
        self.paste_text.setPlaceholderText(
            "Pegar acá el contenido completo del archivo de migración "
            "(o al menos el bloque Schema::create(...) { ... });)"
        )
        self.paste_text.setMinimumHeight(220)
        layout.addWidget(self.paste_text)

        self.file_radio.toggled.connect(self._on_source_toggled)
        self._on_source_toggled()

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        button_row = QHBoxLayout()
        parse_btn = QPushButton("Analizar migración")
        parse_btn.clicked.connect(self._on_parse)
        button_row.addWidget(parse_btn)
        button_row.addStretch()
        layout.addLayout(button_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_source_toggled(self) -> None:
        is_file = self.file_radio.isChecked()
        self.file_path_input.setEnabled(is_file)
        self.paste_text.setEnabled(not is_file)

    def _on_browse(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Elegir migración", "", "Migración PHP (*.php)"
        )
        if path_str:
            self.file_path_input.setText(path_str)

    def _read_source_text(self) -> str | None:
        if self.file_radio.isChecked():
            path_str = self.file_path_input.text().strip()
            if not path_str:
                QMessageBox.warning(self, "Falta el archivo", "Elegí el archivo de migración.")
                return None
            try:
                return Path(path_str).read_text(encoding="utf-8", errors="ignore")
            except OSError as exc:
                QMessageBox.critical(self, "No se pudo leer el archivo", str(exc))
                return None

        text = self.paste_text.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Falta el texto", "Pegá el contenido de la migración.")
            return None
        return text

    def _on_parse(self) -> None:
        text = self._read_source_text()
        if text is None:
            return
        try:
            self.parsed = migration_import.parse_migration(text)
        except migration_import.MigrationParseError as exc:
            self.parsed = None
            self.status_label.setText(f"❌ {exc}")
            return

        detail = f"✅ Tabla '{self.parsed.table}' — {len(self.parsed.columns)} columnas."
        if self.parsed.warnings:
            detail += " Avisos: " + "; ".join(self.parsed.warnings)
        self.status_label.setText(detail)

    def _on_accept(self) -> None:
        if self.parsed is None:
            self._on_parse()
        if self.parsed is None:
            return
        self.accept()


class ProjectScanDialog(QDialog):
    """Muestra el resultado de analizar el proyecto backend — de solo lectura
    salvo por las piezas de scaffolding que el desarrollador pida generar
    explícitamente (ver scaffold.py): nunca edita RouteServiceProvider/
    bootstrap/app.php/config existentes, y nunca sobrescribe un archivo que
    ya esté ahí."""

    def __init__(
        self,
        result: project_scan.ProjectScanResult,
        colors: dict[str, str],
        parent=None,
        *,
        scaffold_status: "scaffold.ScaffoldStatus | None" = None,
        prefijo: str | None = None,
        project_name: str = "Proyecto",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Análisis del proyecto backend")
        self.setMinimumWidth(560)
        self.colors = colors
        self.scaffold_status = scaffold_status
        self.prefijo = prefijo
        self.project_name = project_name
        layout = QVBoxLayout(self)
        self._layout = layout

        summary_lines = [
            f"Raíz analizada: {result.backend_root}",
            f"Versión Laravel detectada: {result.laravel_version_hint}",
            f"routes/modules/ existe: {'sí' if result.routes_modules_dir_exists else 'no'}",
            f"Loader de routes/modules/*.php detectado automáticamente: {'sí' if result.modules_loader_registered else 'no'}",
        ]
        if result.existing_module_routes:
            summary_lines.append("Rutas de módulo ya generadas: " + ", ".join(result.existing_module_routes))
        summary = QLabel("\n".join(summary_lines))
        summary.setWordWrap(True)
        layout.addWidget(summary)

        if result.warnings:
            # Amarillo, no rojo — es un aviso informativo (heurística de texto,
            # puede dar falso negativo), no necesariamente un problema real.
            warnings_label = QLabel("\n".join(f"ⓘ {w}" for w in result.warnings))
            warnings_label.setWordWrap(True)
            warnings_label.setStyleSheet(f"color: {colors['busy']};")
            layout.addWidget(warnings_label)

        if not result.modules_loader_registered:
            layout.addWidget(QLabel("Snippet sugerido, por si hace falta (pegar a mano — no se edita el proyecto automático):"))
            snippet = QPlainTextEdit(project_scan.suggested_loader_snippet(result.laravel_version_hint))
            snippet.setReadOnly(True)
            font = snippet.font()
            font.setFamily("Consolas")
            snippet.setFont(font)
            snippet.setMaximumHeight(120)
            layout.addWidget(snippet)

        self._scaffold_section_index = layout.count()
        if self.scaffold_status is not None:
            self._build_scaffold_section()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
        self._buttons = buttons

    # ------------------------------------------------------- scaffolding
    def _build_scaffold_section(self) -> None:
        """(Re)construye la sección de piezas de base del estándar — se
        vuelve a llamar después de generar algo, para reflejar el estado
        actualizado sin tener que cerrar y reabrir el diálogo."""
        status = self.scaffold_status
        assert status is not None

        # Saca los widgets viejos de esta sección (si es una reconstrucción).
        while self._layout.count() > self._scaffold_section_index and self._layout.itemAt(self._scaffold_section_index) is not self._layout.itemAt(self._layout.count() - 1):
            item = self._layout.takeAt(self._scaffold_section_index)
            if item.widget():
                item.widget().deleteLater()

        box = QGroupBox("Piezas de base del estándar (AbstractModuleService, CrudService, Controller, RouteServiceProvider)")
        box_layout = QVBoxLayout(box)

        checklist = [
            ("AbstractModuleService.php", status.abstract_module_service_exists),
            ("CrudService.php", status.crud_service_exists),
            ("Controller base con anotaciones Swagger", status.base_controller_exists and status.base_controller_has_swagger),
            ("RouteServiceProvider.php", status.route_service_provider_exists),
            ("Clase Token propia (para el usuario autenticado)", status.token_class_found),
            ("Migración de auditoría ({prefijo}_procesosaudit)", status.procesosaudit_migration_found),
        ]
        lines = [f"{'✅' if ok else '⬜'} {label}" for label, ok in checklist]
        checklist_label = QLabel("\n".join(lines))
        checklist_label.setWordWrap(True)
        box_layout.addWidget(checklist_label)

        if not status.token_class_found:
            note = QLabel(
                "ⓘ No se encontró una clase Token propia — si se genera CrudService, va a usar "
                "Auth::user() nativo de Laravel en su lugar (funcionalmente equivalente bajo Sanctum)."
            )
            note.setWordWrap(True)
            note.setStyleSheet(f"color: {self.colors['busy']};")
            box_layout.addWidget(note)

        if status.base_controller_needs_swagger_snippet:
            box_layout.addWidget(QLabel(
                "El Controller base ya existe pero sin las anotaciones Swagger — no se edita solo "
                "(mismo criterio que el loader de rutas). Snippet sugerido para agregar a mano:"
            ))
            snippet = QPlainTextEdit(
                '/**\n'
                ' * @OA\\Info(title="{Proyecto} API", version="1.0.0")\n'
                ' * @OA\\Server(url=L5_SWAGGER_CONST_HOST, description="Servidor Principal")\n'
                ' * @OA\\SecurityScheme(\n'
                '*      securityScheme="bearerAuth", type="http", scheme="bearer"\n'
                ' * )\n'
                ' */\n'
                'abstract class Controller\n'
                '{\n'
                '}\n'
            )
            snippet.setReadOnly(True)
            font = snippet.font()
            font.setFamily("Consolas")
            snippet.setFont(font)
            snippet.setMaximumHeight(120)
            box_layout.addWidget(snippet)

        buttons_row = QHBoxLayout()
        generate_base_btn = QPushButton("Generar piezas base faltantes…")
        generate_base_btn.setEnabled(bool(status.missing_base_pieces))
        generate_base_btn.clicked.connect(self._on_generate_base_pieces)
        buttons_row.addWidget(generate_base_btn)

        generate_crud_btn = QPushButton("Generar CrudService + auditoría…")
        generate_crud_btn.setEnabled(not status.crud_service_exists and self.prefijo is not None)
        if self.prefijo is None:
            generate_crud_btn.setToolTip(
                "Analizá una tabla primero — CrudService necesita el prefijo de negocio del proyecto."
            )
        generate_crud_btn.clicked.connect(self._on_generate_crud_service)
        buttons_row.addWidget(generate_crud_btn)
        buttons_row.addStretch()
        box_layout.addLayout(buttons_row)

        self._layout.insertWidget(self._scaffold_section_index, box)

    def _refresh_scaffold_section(self, backend_root: Path) -> None:
        self.scaffold_status = scaffold.detect_scaffold_status(backend_root)
        self._build_scaffold_section()

    def _on_generate_base_pieces(self) -> None:
        status = self.scaffold_status
        if status is None:
            return
        written = scaffold.write_missing_base_pieces(status, project_name=self.project_name)
        self._refresh_scaffold_section(status.backend_root)
        if written:
            listing = "\n".join(f"- {p}" for p in written.values())
            QMessageBox.information(self, "Piezas generadas", f"Se generaron:\n{listing}")
        else:
            QMessageBox.information(self, "Nada para generar", "No faltaba ninguna pieza de base.")

    def _on_generate_crud_service(self) -> None:
        status = self.scaffold_status
        if status is None or self.prefijo is None:
            return
        written = scaffold.write_crud_service_with_audit(status, self.prefijo)
        self._refresh_scaffold_section(status.backend_root)
        if written:
            listing = "\n".join(f"- {p}" for p in written.values())
            QMessageBox.information(self, "CrudService generado", f"Se generaron:\n{listing}")
        else:
            QMessageBox.information(self, "Nada para generar", "CrudService.php ya existía.")


class SettingsDialog(QDialog):
    """Preferencias: tema, idioma (placeholder) y mapeo de relaciones (.md).

    Los botones de importar/exportar mapeo se conectan desde MainWindow —
    este diálogo no toca la BD ni el filesystem por sí mismo, solo expone
    los controles.
    """

    def __init__(self, current_settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preferencias")
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Oscuro", "Claro"])
        self.theme_combo.setCurrentIndex(0 if current_settings.theme == "dark" else 1)
        form.addRow("Tema:", self.theme_combo)

        self.language_combo = QComboBox()
        self.language_combo.addItem("Español")
        self.language_combo.setEnabled(False)
        self.language_combo.setToolTip("Por ahora el programa solo está en español.")
        form.addRow("Idioma:", self.language_combo)
        layout.addLayout(form)

        mapping_box = QGroupBox("Mapeo de relaciones (.md)")
        mapping_layout = QVBoxLayout(mapping_box)
        hint = QLabel(
            "Importá un .md con columnas FK ya conocidas (columna → tabla) para no "
            "repreguntarlas, o exportá las que se resolvieron en esta sesión para "
            "compartirlas con el equipo — ver Script Generador Backend.md."
        )
        hint.setWordWrap(True)
        mapping_layout.addWidget(hint)

        mapping_buttons = QHBoxLayout()
        self.import_mapping_btn = QPushButton("Importar mapeo…")
        self.export_mapping_btn = QPushButton("Exportar mapeo actual…")
        mapping_buttons.addWidget(self.import_mapping_btn)
        mapping_buttons.addWidget(self.export_mapping_btn)
        mapping_layout.addLayout(mapping_buttons)
        layout.addWidget(mapping_box)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_theme(self) -> str:
        return "dark" if self.theme_combo.currentIndex() == 0 else "light"


_LOG_COLUMNS = ["Fecha (UTC)", "Módulo", "# FK", "# campos", "Tiempo (min)", "Archivos", "Líneas"]


class GenerationLogDialog(QDialog):
    """Historial de generaciones — ver logs.py. Cada fila es un módulo generado:
    lo que la herramienta puede medir objetivamente (tiempo desde "Analizar"
    hasta "Generar archivos", cantidad de archivos y líneas). Pensado como
    insumo directo de la tabla de 3.2.5 del informe (falta agregar a mano el
    tiempo manual y el % de reducción, que la herramienta no puede medir)."""

    def __init__(self, entries: list[logs.GenerationLogEntry], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Historial de generación")
        self.setMinimumSize(720, 420)
        self._entries = list(reversed(entries))  # más reciente primero

        layout = QVBoxLayout(self)

        hint = QLabel(
            "Un módulo por fila. El tiempo es el transcurrido en esta sesión entre "
            "\"Analizar\" y confirmar \"Generar archivos\" — el tiempo del proceso "
            "manual se sigue cronometrando aparte."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.table = QTableWidget(len(self._entries), len(_LOG_COLUMNS))
        self.table.setHorizontalHeaderLabels(_LOG_COLUMNS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        for row, entry in enumerate(self._entries):
            values = [
                entry.timestamp,
                entry.table,
                str(entry.fk_count),
                str(entry.field_count),
                str(entry.elapsed_minutes),
                str(entry.file_count),
                str(entry.line_count),
            ]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()
        layout.addWidget(self.table, stretch=1)

        if not self._entries:
            empty = QLabel("Todavía no se generó ningún módulo en esta instalación.")
            layout.addWidget(empty)

        buttons_row = QHBoxLayout()
        self.export_btn = QPushButton("Exportar CSV…")
        self.export_btn.setEnabled(bool(self._entries))
        buttons_row.addWidget(self.export_btn)
        buttons_row.addStretch()
        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(self.accept)
        buttons_row.addWidget(close_btn)
        layout.addLayout(buttons_row)


class StandardDocsDialog(QDialog):
    """Visor del estándar del proyecto — ver standard_docs.py. Solo lectura:
    el estándar se edita en el vault de Obsidian (o cualquier editor de texto)
    y se trae acá con "Actualizar estándar…", nunca al revés — así queda un
    solo lugar donde se edita de verdad, y acá siempre se ve lo último."""

    def __init__(self, mode: str, colors: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Estándar del proyecto")
        self.resize(1100, 720)
        self._mode = mode
        self._theme = colors
        self._history: list[Path] = []
        self._history_pos = -1
        self._title_index: dict[str, Path] = {}

        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()
        self.source_label = QLabel()
        self.source_label.setWordWrap(True)
        top_row.addWidget(self.source_label, stretch=1)
        self.update_btn = QPushButton("Actualizar estándar…")
        self.update_btn.clicked.connect(self._on_update_docs)
        top_row.addWidget(self.update_btn)
        self.restore_btn = QPushButton("Restaurar original")
        self.restore_btn.clicked.connect(self._on_restore_docs)
        top_row.addWidget(self.restore_btn)
        layout.addLayout(top_row)

        nav_row = QHBoxLayout()
        self.back_btn = QPushButton("◀")
        self.back_btn.setFixedWidth(36)
        self.back_btn.clicked.connect(self._on_back)
        nav_row.addWidget(self.back_btn)
        self.forward_btn = QPushButton("▶")
        self.forward_btn.setFixedWidth(36)
        self.forward_btn.clicked.connect(self._on_forward)
        nav_row.addWidget(self.forward_btn)
        self.breadcrumb = QLabel()
        self.breadcrumb.setStyleSheet("font-weight: 600;")
        nav_row.addWidget(self.breadcrumb, stretch=1)
        layout.addLayout(nav_row)

        splitter = QSplitter(Qt.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(260)
        self.tree.setMaximumWidth(420)
        self.tree.itemClicked.connect(self._on_tree_item_clicked)
        splitter.addWidget(self.tree)

        self.viewer = QTextBrowser()
        self.viewer.setOpenLinks(False)
        self.viewer.setOpenExternalLinks(False)
        self.viewer.anchorClicked.connect(self._on_anchor_clicked)
        splitter.addWidget(self.viewer)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, stretch=1)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

        self._reload()

    # ---------------------------------------------------------------- data
    def _reload(self) -> None:
        root = standard_docs.active_docs_dir()
        self._title_index = standard_docs.index_by_title(root)
        using_override = standard_docs.is_using_override()
        self.source_label.setText(
            f"Estándar actualizado manualmente ({len(self._title_index)} notas) — {standard_docs.override_docs_dir()}"
            if using_override
            else f"Estándar de fábrica, empaquetado con la app ({len(self._title_index)} notas)."
        )
        self.restore_btn.setEnabled(using_override)

        self.tree.clear()
        tree_root = standard_docs.build_tree(root)
        for child in tree_root.children:
            self._add_tree_node(self.tree.invisibleRootItem(), child)
        self.tree.expandToDepth(1)

        self._history = []
        self._history_pos = -1
        first = self._first_note(tree_root)
        if first is not None:
            self._navigate_to(first, record_history=True)
        else:
            self.viewer.setHtml("<i>No hay notas del estándar cargadas.</i>")
            self.breadcrumb.setText("")
            self.back_btn.setEnabled(False)
            self.forward_btn.setEnabled(False)

    def _first_note(self, node: standard_docs.DocNode) -> Path | None:
        for child in node.children:
            if child.is_dir:
                found = self._first_note(child)
                if found is not None:
                    return found
            else:
                return child.path
        return None

    def _add_tree_node(self, parent_item: QTreeWidgetItem, node: standard_docs.DocNode) -> None:
        item = QTreeWidgetItem([node.name])
        parent_item.addChild(item)
        if node.is_dir:
            for child in node.children:
                self._add_tree_node(item, child)
        else:
            item.setData(0, Qt.UserRole, str(node.path))

    # ---------------------------------------------------------- navegación
    def _on_tree_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        path_str = item.data(0, Qt.UserRole)
        if path_str:
            self._navigate_to(Path(path_str), record_history=True)

    def _on_anchor_clicked(self, url) -> None:
        target = standard_docs.wikilink_target(url.toString())
        if target is None:
            return
        path = self._title_index.get(target.lower())
        if path is None:
            QMessageBox.information(
                self, "Nota no encontrada", f'No se encontró la nota "{target}" en el estándar cargado.'
            )
            return
        self._navigate_to(path, record_history=True)

    def _on_back(self) -> None:
        if self._history_pos > 0:
            self._history_pos -= 1
            self._navigate_to(self._history[self._history_pos], record_history=False)

    def _on_forward(self) -> None:
        if self._history_pos < len(self._history) - 1:
            self._history_pos += 1
            self._navigate_to(self._history[self._history_pos], record_history=False)

    def _navigate_to(self, path: Path, *, record_history: bool) -> None:
        html = standard_docs.render_note_html(path, self._theme, self._mode)
        self.viewer.setHtml(html)
        self.breadcrumb.setText(path.stem)
        self._select_in_tree(path)
        if record_history:
            self._history = self._history[: self._history_pos + 1]
            self._history.append(path)
            self._history_pos = len(self._history) - 1
        self.back_btn.setEnabled(self._history_pos > 0)
        self.forward_btn.setEnabled(self._history_pos < len(self._history) - 1)

    def _select_in_tree(self, path: Path) -> None:
        def _walk(item: QTreeWidgetItem) -> bool:
            for i in range(item.childCount()):
                child = item.child(i)
                if child.data(0, Qt.UserRole) == str(path):
                    self.tree.setCurrentItem(child)
                    return True
                if _walk(child):
                    return True
            return False

        _walk(self.tree.invisibleRootItem())

    # --------------------------------------------------------- actualizar
    def _on_update_docs(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Carpeta con el estándar actualizado (.md)")
        if not folder:
            return
        source = Path(folder)
        if not any(source.rglob("*.md")):
            QMessageBox.warning(self, "Carpeta vacía", "Esa carpeta no tiene archivos .md — no hay nada para actualizar.")
            return
        if (
            QMessageBox.question(
                self,
                "Actualizar estándar",
                "Esto reemplaza el estándar cargado actualmente en la app por el contenido de:\n\n"
                f"{source}\n\n¿Continuar?",
            )
            != QMessageBox.Yes
        ):
            return
        try:
            count = standard_docs.replace_docs(source)
        except OSError as exc:
            QMessageBox.critical(self, "Error al actualizar", str(exc))
            return
        QMessageBox.information(self, "Estándar actualizado", f"Se cargaron {count} notas.")
        self._reload()

    def _on_restore_docs(self) -> None:
        if (
            QMessageBox.question(
                self,
                "Restaurar estándar original",
                "Esto descarta el estándar actualizado manualmente y vuelve al que viene empaquetado con la app. "
                "¿Continuar?",
            )
            != QMessageBox.Yes
        ):
            return
        standard_docs.restore_bundled_docs()
        self._reload()


class _PhpTsHighlighter(QSyntaxHighlighter):
    """Resalta PHP/TS en el preview editable con la misma paleta que el visor
    de estándar (ver standard_docs.SYNTAX_COLORS) — antes el preview era todo
    un solo color, y entre tantos comentarios explicativos del estándar
    (ver useFilters.md, etc.) costaba distinguir a simple vista qué era
    código real y qué era comentario."""

    _TOKEN_RE = re.compile(
        r"(?P<comment>//[^\n]*|#[^\n]*)"
        r"|(?P<string>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')"
        r"|(?P<variable>\$[A-Za-z_][A-Za-z0-9_]*)"
        r"|(?P<number>\b\d+(?:\.\d+)?\b)"
        r"|(?P<word>[A-Za-z_][A-Za-z0-9_]*)"
    )

    def __init__(self, document, is_typescript: bool, mode: str) -> None:
        super().__init__(document)
        self._keywords = standard_docs.TS_KEYWORDS if is_typescript else standard_docs.PHP_KEYWORDS
        self._formats: dict[str, QTextCharFormat] = {}
        self.set_mode(mode)

    def set_mode(self, mode: str) -> None:
        palette = standard_docs.SYNTAX_COLORS.get(mode, standard_docs.SYNTAX_COLORS["dark"])
        self._formats = {name: self._make_format(color) for name, color in palette.items()}
        self.rehighlight()

    @staticmethod
    def _make_format(color: str) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        return fmt

    def highlightBlock(self, text: str) -> None:
        comment_ranges = self._highlight_block_comments(text)

        for m in self._TOKEN_RE.finditer(text):
            start, end = m.start(), m.end()
            if any(start < cstart + clen and end > cstart for cstart, clen in comment_ranges):
                continue  # ya coloreado por el bloque /* ... */

            kind = m.lastgroup
            if kind in ("comment", "string", "variable", "number"):
                self.setFormat(start, end - start, self._formats[kind])
            elif kind == "word":
                token = m.group()
                if token in self._keywords:
                    self.setFormat(start, end - start, self._formats["keyword"])
                elif text[end:].lstrip(" \t")[:1] == "(":
                    self.setFormat(start, end - start, self._formats["function"])
                elif token[:1].isupper():
                    self.setFormat(start, end - start, self._formats["type"])

    def _highlight_block_comments(self, text: str) -> list[tuple[int, int]]:
        # /** ... */ (PHPDoc, anotaciones @OA de Swagger) puede abarcar varias
        # líneas — QSyntaxHighlighter llama a highlightBlock() una línea a la
        # vez, así que el estado "sigo dentro de un comentario" se guarda en
        # el block state (patrón estándar de Qt para comentarios multilínea).
        self.setCurrentBlockState(0)
        ranges: list[tuple[int, int]] = []
        start_index = 0 if self.previousBlockState() == 1 else text.find("/*")

        while start_index != -1:
            end_index = text.find("*/", start_index)
            if end_index == -1:
                self.setCurrentBlockState(1)
                length = len(text) - start_index
            else:
                length = end_index - start_index + 2
            self.setFormat(start_index, length, self._formats["comment"])
            ranges.append((start_index, length))
            if end_index == -1:
                break
            start_index = text.find("/*", end_index + 2)

        return ranges


class _CodeEditor(QPlainTextEdit):
    """QPlainTextEdit con autocompletado "por palabras" (sin IA / sin Copilot):
    combina una lista curada de keywords de PHP/Laravel (o TS) con las
    palabras que ya aparecen en el propio documento — el mismo patrón que el
    ejemplo "Custom Completer" de Qt. Se dispara solo al escribir 2+
    caracteres, o a mano con Ctrl+Espacio."""

    def __init__(
        self, keywords: list[str], is_typescript: bool = False, theme_mode: str = "dark", parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._static_words = set(keywords)
        self.highlighter = _PhpTsHighlighter(self.document(), is_typescript, theme_mode)

        self.completer = QCompleter(self)
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.activated.connect(self._insert_completion)

        self._refresh_completion_model()
        self.textChanged.connect(self._refresh_completion_model)

    def set_theme_mode(self, mode: str) -> None:
        self.highlighter.set_mode(mode)

    def _refresh_completion_model(self) -> None:
        doc_words = set(re.findall(r"[A-Za-z_\\][A-Za-z0-9_\\]{2,}", self.toPlainText()))
        model = QStringListModel(sorted(self._static_words | doc_words), self.completer)
        self.completer.setModel(model)

    _IDENTIFIER_CHAR_RE = re.compile(r"[A-Za-z0-9_\\]")

    def _identifier_before_cursor(self) -> tuple[int, str]:
        """Posición donde empieza el identificador que termina justo en el
        cursor, y ese texto — a mano escaneando para atrás en vez de
        `QTextCursor.WordUnderCursor`, que no es confiable acá: si el cursor
        queda justo antes de un carácter que no es de identificador (ej.
        ';', '(' — típico al autocompletar en medio de una línea, no solo al
        final), Qt a veces asocia la selección con ESE carácter en vez de
        con la palabra ya tipeada a la izquierda, y terminaba duplicando el
        prefijo al confirmar (ej. "dele" + Tab -> "deledeleted" en vez de
        "deleted")."""
        text = self.toPlainText()
        pos = self.textCursor().position()
        start = pos
        while start > 0 and self._IDENTIFIER_CHAR_RE.match(text[start - 1]):
            start -= 1
        return start, text[start:pos]

    def _text_under_cursor(self) -> str:
        return self._identifier_before_cursor()[1]

    def _insert_completion(self, completion: str) -> None:
        start, _ = self._identifier_before_cursor()
        cursor = self.textCursor()
        end = cursor.position()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        cursor.insertText(completion)
        self.setTextCursor(cursor)

    def keyPressEvent(self, event) -> None:
        if self.completer.popup().isVisible() and event.key() in (
            Qt.Key_Enter,
            Qt.Key_Return,
            Qt.Key_Escape,
            Qt.Key_Tab,
            Qt.Key_Backtab,
        ):
            event.ignore()
            return

        is_shortcut = event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_Space
        if not is_shortcut:
            super().keyPressEvent(event)

        prefix = self._text_under_cursor()
        if not is_shortcut and (len(prefix) < 2 or not event.text()):
            self.completer.popup().hide()
            return

        if prefix != self.completer.completionPrefix():
            self.completer.setCompletionPrefix(prefix)
            self.completer.popup().setCurrentIndex(self.completer.completionModel().index(0, 0))

        rect = self.cursorRect()
        rect.setWidth(
            self.completer.popup().sizeHintForColumn(0)
            + self.completer.popup().verticalScrollBar().sizeHint().width()
        )
        self.completer.complete(rect)


class _PreviewPopout(QDialog):
    """Ventana aparte para el preview — reusa el mismo QTabWidget del panel
    principal (no una copia) moviéndolo temporalmente, así no hay que
    sincronizar contenido entre dos widgets distintos."""

    def __init__(self, preview_tabs: QTabWidget, on_close, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preview — vista ampliada")
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.resize(1400, 900)
        self._on_close = on_close

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(preview_tabs)

    def closeEvent(self, event) -> None:
        self._on_close()
        super().closeEvent(event)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Service-Forge — prototipo")
        self.resize(1300, 860)

        self.settings = Settings.load()
        self.colors = status_colors(self.settings.theme)

        self.conn: db.pymysql.connections.Connection | None = None
        self.config: db.ConnectionConfig | None = None
        self.tables: list[str] = []
        self.fk_cache = fk_resolver.FkResolutionCache()
        self.imported_mapping: dict[str, str] = {}
        self.session_resolved_fks: dict[str, str] = {}
        self._connection_worker: ConnectionWorker | None = None

        # Modelo persistente de estructura (Model ↔ Resource y los demás roles de un
        # backend Laravel) -- ver match_learner.StructureLearner y datasets/structure/.
        # Se carga una sola vez por sesión y cada confirmación/corrección del usuario
        # (ver _apply_model_resource_confirmation) lo actualiza y lo guarda al toque.
        self.match_learner = match_learner.StructureLearner.load()
        self.current_model_resource_match: model_resource_scan.ModelResourceMatch | None = None
        # tabla -> ruta del Resource ya existente que el desarrollador
        # confirmó (aunque no siga la convención de esta herramienta) -- se
        # usa en _on_generate para avisar antes de escribirle un Resource
        # nuevo encima del que ya hay.
        self.confirmed_resources: dict[str, Path] = {}

        self.backend_root: Path | None = None
        self.frontend_root: Path | None = None

        self._analysis_started_at: float | None = None

        self.current_table: str | None = None
        self.current_columns: list[db.Column] = []
        self.current_resolutions: dict[str, fk_resolver.FkResolution] = {}
        self.current_unique_indexes: dict[str, list[str]] = {}
        self.current_manifest: generator.ModuleManifest | None = None

        self._build_menu_bar()
        self._build_ui()
        self._apply_theme()

    # ------------------------------------------------------------------ UI
    def _build_menu_bar(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&Archivo")
        connection_action = QAction("Conexión…", self)
        connection_action.triggered.connect(self._on_open_connection_dialog)
        file_menu.addAction(connection_action)
        file_menu.addSeparator()
        exit_action = QAction("Salir", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        edit_menu = menu_bar.addMenu("&Editar")
        settings_action = QAction("Preferencias…", self)
        settings_action.triggered.connect(self._on_open_settings)
        edit_menu.addAction(settings_action)

        logs_menu = menu_bar.addMenu("&Logs")
        logs_action = QAction("Historial de generación…", self)
        logs_action.triggered.connect(self._on_open_logs)
        logs_menu.addAction(logs_action)

        standard_menu = menu_bar.addMenu("&Estándar")
        standard_action = QAction("Ver estándar del proyecto…", self)
        standard_action.triggered.connect(self._on_open_standard_docs)
        standard_menu.addAction(standard_action)

        help_menu = menu_bar.addMenu("A&yuda")
        about_action = QAction("Acerca de", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # La conexión a BD y la "Conf. de generación" se configuran una vez
        # por sesión (o rara vez) — viven en diálogos aparte (mismo patrón
        # que Logs/Preferencias) en vez de ocupar espacio fijo en la ventana
        # principal. Acá solo queda una fila de estado/accesos compacta.
        self.connection_dialog = self._build_connection_dialog()
        self.generation_config_dialog = self._build_generation_config_dialog()
        root.addWidget(self._build_connection_status_row())

        # "Proyectos destino" sí se deja visible: a diferencia de la conexión,
        # conviene tener la raíz backend/frontend siempre a la vista mientras
        # se genera, para no escribir en la carpeta equivocada.
        root.addWidget(self._build_project_box())

        table_row = QHBoxLayout()
        self.table_combo = QComboBox()
        self.table_combo.setMinimumWidth(240)
        self.analyze_btn = QPushButton("→ Analizar")
        self.analyze_btn.clicked.connect(self._on_analyze)
        self.analyze_btn.setEnabled(False)
        self.import_migration_btn = QPushButton("Importar migración…")
        self.import_migration_btn.clicked.connect(self._on_import_migration)
        table_row.addWidget(QLabel("Tabla:"))
        table_row.addWidget(self.table_combo)
        table_row.addWidget(self.analyze_btn)
        table_row.addWidget(self.import_migration_btn)
        table_row.addStretch()
        root.addLayout(table_row)

        # Estado del matching Modelo↔Resource para la tabla recién analizada
        # (ver model_resource_scan.py / match_learner.py) -- soporte de
        # análisis, no bloquea nada: se llena después de "Analizar" y el
        # desarrollador confirma o corrige desde acá antes de generar.
        match_row = QHBoxLayout()
        self.model_resource_status_label = QLabel("")
        self.model_resource_status_label.setWordWrap(True)
        self.model_resource_confirm_btn = QPushButton("Revisar Model/Resource detectado…")
        self.model_resource_confirm_btn.clicked.connect(self._on_review_model_resource_match)
        self.model_resource_confirm_btn.setVisible(False)
        match_row.addWidget(self.model_resource_status_label, stretch=1)
        match_row.addWidget(self.model_resource_confirm_btn)
        root.addLayout(match_row)

        # Grid (mapeo de columnas) y preview en un splitter — el preview es
        # donde se edita el código antes de generar, necesita poder crecer.
        splitter = QSplitter(Qt.Vertical)

        grid_container = QWidget()
        grid_layout = QVBoxLayout(grid_container)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.addWidget(QLabel("Mapeo de columnas"))
        self.grid = QTableWidget(0, len(_GRID_COLUMNS))
        self.grid.setHorizontalHeaderLabels(_GRID_COLUMNS)
        self.grid.setAlternatingRowColors(True)
        self.grid.setMinimumHeight(100)
        grid_layout.addWidget(self.grid)
        splitter.addWidget(grid_container)

        preview_container = QWidget()
        self.preview_layout = QVBoxLayout(preview_container)
        self.preview_layout.setContentsMargins(0, 0, 0, 0)

        actions_row = QHBoxLayout()
        self.preview_btn = QPushButton("Actualizar preview")
        self.preview_btn.clicked.connect(self._on_update_preview)
        self.preview_btn.setEnabled(False)
        self.generate_btn = QPushButton("Generar archivos")
        self.generate_btn.setProperty("accent", "true")
        self.generate_btn.clicked.connect(self._on_generate)
        self.generate_btn.setEnabled(False)
        self.preview_popout_btn = QPushButton("Ampliar preview ↗")
        self.preview_popout_btn.clicked.connect(self._on_toggle_preview_popout)
        self.backup_btn = QPushButton("Backup de la BD…")
        self.backup_btn.clicked.connect(self._on_backup)
        self.backup_btn.setEnabled(False)
        actions_row.addWidget(self.preview_btn)
        actions_row.addWidget(self.generate_btn)
        actions_row.addWidget(self.preview_popout_btn)
        actions_row.addStretch()
        actions_row.addWidget(self.backup_btn)
        self.preview_layout.addLayout(actions_row)

        self.preview_note = QLabel(
            "El preview es editable — lo que esté en cada pestaña al generar es lo que se escribe. "
            "Autocompletado: escribí 2+ letras o Ctrl+Espacio."
        )
        self.preview_layout.addWidget(self.preview_note)

        self.preview_tabs = QTabWidget()
        self.preview_widgets: dict[str, _CodeEditor] = {}
        for key, title in _PREVIEW_TABS:
            is_ts = title.endswith(".ts")
            keywords = _TS_INTERFACE_COMPLETIONS if is_ts else _PHP_LARAVEL_COMPLETIONS
            editor = _CodeEditor(keywords, is_typescript=is_ts, theme_mode=self.settings.theme)
            font = editor.font()
            font.setFamily("Consolas")
            editor.setFont(font)
            self.preview_widgets[key] = editor
            self.preview_tabs.addTab(editor, title)
        self.preview_layout.addWidget(self.preview_tabs, stretch=1)

        self._preview_popout: _PreviewPopout | None = None

        splitter.addWidget(preview_container)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([200, 600])
        self.splitter = splitter
        root.addWidget(splitter, stretch=1)

        self.status_label = QLabel("Sin conexión.")
        root.addWidget(self.status_label)

    def _build_connection_status_row(self) -> QWidget:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        self.connection_summary_label = QLabel("● Sin conexión")
        self.generation_config_btn = QPushButton("Configuración de generación…")
        self.generation_config_btn.clicked.connect(self._on_open_generation_config)
        self.connection_dialog_btn = QPushButton("Conexión…")
        self.connection_dialog_btn.clicked.connect(self._on_open_connection_dialog)
        row.addWidget(self.connection_summary_label)
        row.addStretch()
        row.addWidget(self.generation_config_btn)
        row.addWidget(self.connection_dialog_btn)
        return container

    def _build_connection_dialog(self) -> QDialog:
        # Vive en un diálogo aparte (mismo patrón que Preferencias/Logs): la
        # conexión se configura una vez por sesión, no debe competir por
        # espacio con el grid/preview que es lo que se usa todo el tiempo.
        dialog = QDialog(self)
        dialog.setWindowTitle("Conexión — BD objetivo")
        dialog.setMinimumWidth(440)
        layout = QVBoxLayout(dialog)

        form = QFormLayout()
        self.host_input = QLineEdit("127.0.0.1")
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(3306)
        self.user_input = QLineEdit("root")
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.database_input = QLineEdit()
        self.connection_name_input = QLineEdit()
        self.connection_name_input.setPlaceholderText("nombre de la conexión Eloquent, ej. mysql_dbmdt_siaw")

        form.addRow("Host:", self.host_input)
        form.addRow("Puerto:", self.port_input)
        form.addRow("Usuario:", self.user_input)
        form.addRow("Contraseña:", self.password_input)
        form.addRow("Base de datos:", self.database_input)
        form.addRow("Conexión Eloquent ($connection):", self.connection_name_input)
        layout.addLayout(form)

        connect_row = QHBoxLayout()
        self.connect_btn = QPushButton("Conectar")
        self.connect_btn.clicked.connect(lambda: self._start_connection("connect"))
        self.test_connection_btn = QPushButton("Probar conexión")
        self.test_connection_btn.clicked.connect(lambda: self._start_connection("test"))
        self.connection_status = QLabel("● Desconectado")
        connect_row.addWidget(self.connect_btn)
        connect_row.addWidget(self.test_connection_btn)
        connect_row.addWidget(self.connection_status)
        connect_row.addStretch()
        layout.addLayout(connect_row)

        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)

        return dialog

    def _on_open_connection_dialog(self) -> None:
        self.connection_dialog.exec()

    def _on_open_generation_config(self) -> None:
        self.generation_config_dialog.exec()

    def _build_project_box(self) -> QGroupBox:
        box = QGroupBox("Proyectos destino")
        box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        form = QFormLayout(box)

        self.backend_root_input = QLineEdit()
        self.backend_root_input.setReadOnly(True)
        backend_row = QHBoxLayout()
        backend_browse = QPushButton("Elegir…")
        backend_browse.clicked.connect(self._on_choose_backend_root)
        scan_btn = QPushButton("Analizar proyecto")
        scan_btn.clicked.connect(self._on_scan_backend_project)
        backend_row.addWidget(self.backend_root_input)
        backend_row.addWidget(backend_browse)
        backend_row.addWidget(scan_btn)
        form.addRow("Backend (raíz):", backend_row)

        self.frontend_root_input = QLineEdit()
        self.frontend_root_input.setReadOnly(True)
        frontend_row = QHBoxLayout()
        frontend_browse = QPushButton("Elegir…")
        frontend_browse.clicked.connect(self._on_choose_frontend_root)
        frontend_row.addWidget(self.frontend_root_input)
        frontend_row.addWidget(frontend_browse)
        form.addRow("Frontend (raíz):", frontend_row)

        self.user_model_input = QLineEdit(generator.DEFAULT_USER_MODEL_CLASS)
        form.addRow("Modelo de usuario (created_by/updated_by/deleted_by):", self.user_model_input)

        return box

    def _build_generation_config_dialog(self) -> QDialog:
        # La config de generación (checkboxes de CÓMO se genera + carpeta de
        # salida separada) se abre desde un botón en vez de ocupar espacio
        # fijo en la ventana principal — se toca poco, y le sacaba lugar al
        # grid/preview (que sí se usan todo el tiempo) dejando la ventana
        # "chata". Mismo patrón que Conexión/Preferencias/Logs.
        dialog = QDialog(self)
        dialog.setWindowTitle("Configuración de generación")
        dialog.setMinimumWidth(480)
        layout = QVBoxLayout(dialog)
        layout.addWidget(self._build_generation_config_box())
        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
        return dialog

    def _build_generation_config_box(self) -> QGroupBox:
        # Agrupa los checkboxes que controlan CÓMO se genera (a diferencia de
        # "Proyectos destino", que define DÓNDE) — antes estaban repartidos
        # sueltos por la ventana (uno en su propia fila, dos mezclados con
        # los campos de "Proyectos destino"), sin relación visual entre sí.
        box = QGroupBox("Conf. de generación")
        layout = QVBoxLayout(box)

        self.pagination_checkbox = QCheckBox(
            "El Controller admite ?paginate=true (agrega meta de paginación — ver Controller.md)"
        )
        self.pagination_checkbox.setChecked(True)
        layout.addWidget(self.pagination_checkbox)

        # Desmarcado, se omiten los comentarios "//" explicativos (el porqué
        # de cada decisión, referencias a .md, notas de la sección) en los
        # archivos generados por módulo — quedan los bloques /** */ (PHPDoc,
        # anotaciones @OA de Swagger), que son funcionales, no ruido. Pensado
        # para cuando ya se conoce el estándar y esos comentarios sobran.
        self.add_comments_checkbox = QCheckBox(
            "Añadir comentarios explicativos en el código generado"
        )
        self.add_comments_checkbox.setChecked(True)
        layout.addWidget(self.add_comments_checkbox)

        self.write_audit_checkbox = QCheckBox(
            "Generar audit-user.interface.ts compartido (desmarcar si el proyecto ya lo tiene)"
        )
        self.write_audit_checkbox.setChecked(False)
        layout.addWidget(self.write_audit_checkbox)

        # Carpeta de salida separada — para cuando no se quiere escribir
        # directo en el proyecto real (ej. revisar el resultado antes de
        # copiarlo a mano, o generar sin tener el proyecto clonado acá). El
        # backend/frontend de "Proyectos destino" siguen siendo la raíz que
        # se ANALIZA/escanea (tablas, migraciones, resources existentes);
        # esta carpeta es solo dónde se ESCRIBEN los archivos generados — ver
        # _on_generate. write_files ya crea toda la subestructura de carpetas
        # (mkdir parents=True) así que cualquier carpeta vacía sirve como
        # destino.
        self.separate_output_checkbox = QCheckBox(
            "Generar en una carpeta de salida separada (no escribir directo en el proyecto)"
        )
        self.separate_output_checkbox.toggled.connect(self._on_separate_output_toggled)
        layout.addWidget(self.separate_output_checkbox)

        # Cada fila vive en su propio QWidget contenedor (no un QFormLayout
        # compartido) para poder ocultarla entera con setVisible() — antes
        # solo se deshabilitaba (setEnabled), y la fila (label + input +
        # botón "Elegir…") se seguía viendo siempre, aun sin sentido cuando
        # "carpeta de salida separada" está desmarcado.
        self.output_backend_root: Path | None = None
        self.output_backend_row_widget = QWidget()
        output_backend_row = QHBoxLayout(self.output_backend_row_widget)
        output_backend_row.setContentsMargins(0, 0, 0, 0)
        self.output_backend_input = QLineEdit()
        self.output_backend_input.setReadOnly(True)
        output_backend_browse = QPushButton("Elegir…")
        output_backend_browse.clicked.connect(self._on_choose_output_backend_root)
        output_backend_row.addWidget(QLabel("Salida backend:"))
        output_backend_row.addWidget(self.output_backend_input)
        output_backend_row.addWidget(output_backend_browse)
        layout.addWidget(self.output_backend_row_widget)

        self.output_frontend_root: Path | None = None
        self.output_frontend_row_widget = QWidget()
        output_frontend_row = QHBoxLayout(self.output_frontend_row_widget)
        output_frontend_row.setContentsMargins(0, 0, 0, 0)
        self.output_frontend_input = QLineEdit()
        self.output_frontend_input.setReadOnly(True)
        output_frontend_browse = QPushButton("Elegir…")
        output_frontend_browse.clicked.connect(self._on_choose_output_frontend_root)
        output_frontend_row.addWidget(QLabel("Salida frontend:"))
        output_frontend_row.addWidget(self.output_frontend_input)
        output_frontend_row.addWidget(output_frontend_browse)
        layout.addWidget(self.output_frontend_row_widget)

        self._on_separate_output_toggled(False)

        return box

    def _on_separate_output_toggled(self, checked: bool) -> None:
        self.output_backend_row_widget.setVisible(checked)
        self.output_frontend_row_widget.setVisible(checked)

    def _on_choose_output_backend_root(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Carpeta de salida — backend")
        if chosen:
            self.output_backend_root = Path(chosen)
            self.output_backend_input.setText(chosen)

    def _on_choose_output_frontend_root(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Carpeta de salida — frontend")
        if chosen:
            self.output_frontend_root = Path(chosen)
            self.output_frontend_input.setText(chosen)

    # --------------------------------------------------------- preferencias
    def _apply_theme(self) -> None:
        self.colors = status_colors(self.settings.theme)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_stylesheet(self.settings.theme))
        self.preview_note.setStyleSheet(f"color: {self.colors['idle']};")
        self.status_label.setStyleSheet(f"color: {self.colors['idle']};")
        if not self.conn:
            self.connection_status.setStyleSheet(f"color: {self.colors['idle']};")
            self.connection_summary_label.setStyleSheet(f"color: {self.colors['idle']};")
        for editor in self.preview_widgets.values():
            editor.set_theme_mode(self.settings.theme)

    def _on_open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        dialog.import_mapping_btn.clicked.connect(self._on_import_mapping)
        dialog.export_mapping_btn.clicked.connect(self._on_export_mapping)
        if dialog.exec() == QDialog.Accepted:
            new_theme = dialog.selected_theme()
            if new_theme != self.settings.theme:
                self.settings.theme = new_theme
                self.settings.save()
                self._apply_theme()

    def _on_open_logs(self) -> None:
        entries = logs.load_log()
        dialog = GenerationLogDialog(entries, self)
        dialog.export_btn.clicked.connect(lambda: self._on_export_logs(dialog._entries))
        dialog.exec()

    def _on_export_logs(self, entries: list[logs.GenerationLogEntry]) -> None:
        path_str, _ = QFileDialog.getSaveFileName(self, "Exportar historial de generación", "servicforge-log.csv", "CSV (*.csv)")
        if not path_str:
            return
        try:
            logs.export_csv(entries, Path(path_str))
        except OSError as exc:
            QMessageBox.critical(self, "Error al exportar", str(exc))
            return
        QMessageBox.information(self, "Exportado", f"Historial exportado a:\n{path_str}")

    def _on_open_standard_docs(self) -> None:
        dialog = StandardDocsDialog(self.settings.theme, palette(self.settings.theme), self)
        dialog.exec()

    def _on_about(self) -> None:
        QMessageBox.information(
            self,
            "Acerca de",
            f"Service-Forge — v{__version__}\n\n"
            "Genera el patrón de servicio Laravel + interfaces del frontend "
            "a partir del análisis de una tabla de base de datos.\n\n"
            "github.com/Gabngs/ServiceForge",
        )

    def _on_import_mapping(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(self, "Importar mapeo de relaciones", "", "Markdown (*.md)")
        if not path_str:
            return
        try:
            loaded = table_mapping.load_mapping_md(Path(path_str))
        except OSError as exc:
            QMessageBox.critical(self, "Error al importar", str(exc))
            return
        self.imported_mapping.update(loaded)
        QMessageBox.information(
            self, "Mapeo importado", f"Se cargaron {len(loaded)} columnas mapeadas desde:\n{path_str}"
        )

    def _on_export_mapping(self) -> None:
        if not self.session_resolved_fks:
            QMessageBox.information(
                self,
                "Nada para exportar",
                "Todavía no se resolvió ninguna FK en esta sesión — analizá al menos una tabla primero.",
            )
            return
        default_name = f"mapeo-relaciones-{self.config.database if self.config else 'bd'}.md"
        path_str, _ = QFileDialog.getSaveFileName(self, "Exportar mapeo de relaciones", default_name, "Markdown (*.md)")
        if not path_str:
            return
        title = f"Mapeo de relaciones — {self.config.database if self.config else ''}"
        table_mapping.save_mapping_md(self.session_resolved_fks, Path(path_str), title=title)
        QMessageBox.information(
            self,
            "Mapeo exportado",
            f"Se exportaron {len(self.session_resolved_fks)} columnas a:\n{path_str}",
        )

    # ------------------------------------------------------------- conexión
    def _set_connection_status(self, state: str, text: str) -> None:
        color = self.colors.get(state, self.colors["idle"])
        self.connection_status.setStyleSheet(f"color: {color};")
        self.connection_status.setText(f"● {text}")
        # El diálogo de conexión puede estar cerrado — la fila de estado
        # compacta de la ventana principal repite el mismo texto siempre.
        self.connection_summary_label.setStyleSheet(f"color: {color};")
        self.connection_summary_label.setText(f"● {text}")

    def _start_connection(self, mode: str) -> None:
        if self._connection_worker is not None and self._connection_worker.isRunning():
            return

        config = db.ConnectionConfig(
            host=self.host_input.text().strip(),
            port=self.port_input.value(),
            user=self.user_input.text().strip(),
            password=self.password_input.text(),
            database=self.database_input.text().strip(),
        )

        self.connect_btn.setEnabled(False)
        self.test_connection_btn.setEnabled(False)
        self._set_connection_status("busy", "Conectando…")

        worker = ConnectionWorker(config, mode, parent=self)
        worker.succeeded.connect(lambda outcome: self._on_connection_succeeded(config, mode, outcome))
        worker.failed.connect(lambda message: self._on_connection_failed(mode, message))
        worker.finished.connect(lambda: self._reset_connection_buttons())
        self._connection_worker = worker
        worker.start()

    def _reset_connection_buttons(self) -> None:
        self.connect_btn.setEnabled(True)
        self.test_connection_btn.setEnabled(True)

    def _on_connection_succeeded(self, config: db.ConnectionConfig, mode: str, outcome: ConnectionOutcome) -> None:
        if mode == "test":
            self._set_connection_status("ok", "Conexión OK")
            return

        self.config = config
        self.conn = outcome.connection
        self.tables = outcome.tables
        if not self.connection_name_input.text().strip():
            self.connection_name_input.setText(config.database)

        self.table_combo.clear()
        self.table_combo.addItems(self.tables)
        self.analyze_btn.setEnabled(bool(self.tables))
        self.backup_btn.setEnabled(True)
        self._set_connection_status("ok", f"Conectado — {config.database}@{config.host} · {len(self.tables)} tablas")

        # Ya conectado — cerrar el diálogo solo, no hace falta que el
        # desarrollador lo cierre a mano para seguir con "Analizar".
        self.connection_dialog.accept()

    def _on_connection_failed(self, mode: str, message: str) -> None:
        self._set_connection_status("error", "Error de conexión")
        title = "No se pudo probar la conexión" if mode == "test" else "Error de conexión"
        QMessageBox.critical(self, title, message)

    # --------------------------------------------------------- proyectos
    def _on_choose_backend_root(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Raíz del proyecto backend")
        if chosen:
            self.backend_root = Path(chosen)
            self.backend_root_input.setText(chosen)

    def _on_choose_frontend_root(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Raíz del proyecto frontend")
        if chosen:
            self.frontend_root = Path(chosen)
            self.frontend_root_input.setText(chosen)

    def _on_scan_backend_project(self) -> None:
        if not self.backend_root:
            QMessageBox.warning(self, "Falta la raíz del backend", "Elegí primero la carpeta del proyecto backend.")
            return
        result = project_scan.scan_backend_project(self.backend_root)
        scaffold_status = scaffold.detect_scaffold_status(self.backend_root)
        prefijo = self.current_manifest.prefijo if self.current_manifest else None
        project_name = self.database_input.text().strip() or self.backend_root.name
        ProjectScanDialog(
            result,
            self.colors,
            self,
            scaffold_status=scaffold_status,
            prefijo=prefijo,
            project_name=project_name,
        ).exec()

    # ------------------------------------------------------------- análisis
    def _on_analyze(self) -> None:
        if not self.conn or not self.config:
            return
        table = self.table_combo.currentText()
        if not table:
            return

        try:
            columns = db.describe_table(self.conn, table)
            unique_idx = db.unique_indexes(self.conn, table)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error al analizar la tabla", str(exc))
            return

        self._finish_analysis(
            table,
            columns,
            unique_idx,
            tables_for_fk=self.tables,
            connection_id=self.config.connection_id,
        )

    def _on_import_migration(self) -> None:
        """Fuente alternativa a la conexión a BD: una migración Laravel ya
        escrita (archivo elegido o texto pegado) — ver migration_import.py.
        Reproduce exactamente el mismo flujo de análisis (resolución de FK,
        grid, preview) que `_on_analyze`, solo que sin conexión real."""
        dialog = MigrationImportDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return

        parsed = dialog.parsed
        if parsed is None:
            return

        if parsed.warnings:
            QMessageBox.warning(self, "Migración importada con avisos", "\n".join(parsed.warnings))

        # Sin conexión a BD no hay SHOW TABLES -- se completa la lista de
        # tablas (necesaria para reconocer candidatas de FK, ver
        # fk_resolver.find_fk_candidates) escaneando las migraciones del
        # propio proyecto backend, si ya se eligió una raíz.
        tables_for_fk = set(self.tables)
        if self.backend_root:
            tables_for_fk.update(migration_import.scan_migration_tables(self.backend_root))
        tables_for_fk.add(parsed.table)
        self.tables = sorted(tables_for_fk)

        # Los hints de FK explícitos de la migración (->constrained()/->references()
        # ->on()) tienen la misma prioridad que un mapeo .md importado — ver
        # fk_resolver.resolve_fk.
        self.imported_mapping.update(parsed.fk_hints)

        self._finish_analysis(
            parsed.table,
            parsed.columns,
            parsed.unique_indexes,
            tables_for_fk=self.tables,
            connection_id=f"migration::{self.backend_root or 'sin-proyecto'}",
        )

    def _finish_analysis(
        self,
        table: str,
        columns: list[db.Column],
        unique_idx: dict[str, list[str]],
        *,
        tables_for_fk: list[str],
        connection_id: str,
    ) -> None:
        # Arranca acá el cronómetro del lead time con la herramienta para este
        # módulo (ver logs.py / 3.2.5 del informe) — se cierra al confirmar
        # "Generar archivos".
        self._analysis_started_at = time.monotonic()

        prefijo, _ = naming.split_prefijo_modulo(table)
        business_columns = mapping.business_columns(columns)

        resolutions: dict[str, fk_resolver.FkResolution] = {}
        ambiguous: list[fk_resolver.FkResolution] = []
        for column in business_columns:
            resolution = fk_resolver.resolve_fk(
                column.name,
                prefijo,
                tables_for_fk,
                connection_id=connection_id,
                cache=self.fk_cache,
                imported_mapping=self.imported_mapping,
            )
            if resolution is None:
                continue
            resolutions[column.name] = resolution
            if resolution.status == "ambiguous":
                ambiguous.append(resolution)

        if ambiguous:
            dialog = FkResolutionDialog(ambiguous, tables_for_fk, self)
            if dialog.exec() == QDialog.Accepted:
                chosen = dialog.resolutions()
                for column, table_name in chosen.items():
                    self.fk_cache.set(connection_id, column, table_name)
                    base = resolutions[column].base_name
                    candidates = resolutions[column].candidates
                    resolutions[column] = fk_resolver.FkResolution(
                        column, base, candidates, "resolved_from_cache", table_name
                    )

        self.current_table = table
        self.current_columns = business_columns
        self.current_resolutions = resolutions
        self.current_unique_indexes = unique_idx
        self.session_resolved_fks.update(
            {name: res.table for name, res in resolutions.items() if res.table}
        )

        self._populate_grid()
        self.preview_btn.setEnabled(True)
        self.generate_btn.setEnabled(True)
        self.status_label.setText(f"Tabla '{table}' analizada — {len(business_columns)} columnas de negocio.")
        self._on_update_preview()

        # Preview no vacío desde el primer momento — antes había que acordarse
        # de apretar "Actualizar preview" para ver algo en las pestañas.
        self._on_update_preview()

        self._run_model_resource_scan()

    def _run_model_resource_scan(self) -> None:
        """Busca, en el proyecto backend elegido, si ya existe un Model y/o
        Resource para la tabla recién analizada — aunque no sigan la
        convención de esta herramienta (ver model_resource_scan.py). Es un
        soporte de análisis, no decide solo: el desarrollador confirma o
        corrige desde "Revisar Model/Resource detectado…" antes de generar."""
        self.current_model_resource_match = None
        if not self.backend_root or not self.current_table:
            self.model_resource_status_label.setText("")
            self.model_resource_confirm_btn.setVisible(False)
            return

        # Reusa la resolución de FK ya cacheada/importada/exportada (ver
        # fk_resolver / "Mapeo de relaciones (.md)" en Preferencias) para
        # saber qué claves de relación puede exponer un RelationResource de
        # esta tabla ('articulo', 'created_by', ...) además de sus columnas
        # planas — ver find_candidates.
        relation_names = {"created_by", "updated_by", "deleted_by"}
        for resolution in self.current_resolutions.values():
            if resolution.table:
                _, related_modulo = naming.split_prefijo_modulo(resolution.table)
                relation_names.add(related_modulo)

        match = model_resource_scan.find_candidates(
            self.current_table,
            self.current_columns,
            self.backend_root,
            learner=self.match_learner,
            relation_names=relation_names,
        )
        self.current_model_resource_match = match

        model_text = f"Model existente: {match.model.class_name}" if match.model else "No se encontró Model existente"
        best = match.best
        if best is not None:
            resource_text = f"Resource candidato: {best.resource.class_name} ({best.score:.0%})"
        elif match.candidates:
            resource_text = f"{len(match.candidates)} candidato(s) con baja confianza"
        else:
            resource_text = "No se encontró Resource existente"

        self.model_resource_status_label.setText(f"{model_text} · {resource_text}")
        self.model_resource_confirm_btn.setVisible(True)

    def _on_review_model_resource_match(self) -> None:
        match = self.current_model_resource_match
        if match is None:
            return

        dialog = ModelResourceMatchDialog(match, self)
        if dialog.exec() != QDialog.Accepted:
            return

        self._apply_model_resource_confirmation(match, dialog.confirmed_indexes())

    def _apply_model_resource_confirmation(
        self, match: "model_resource_scan.ModelResourceMatch", confirmed: set[int]
    ) -> None:
        """Separado de `_on_review_model_resource_match` (que abre el diálogo
        modal) para poder ejercitar el efecto de una confirmación sin pasar
        por `QDialog.exec()` — ver tests. `confirmed` son índices en
        `match.candidates`."""
        # Cada candidato mostrado es un ejemplo: tildado = confirmado
        # (label 1), mostrado y no tildado = descartado (label 0) — así el
        # matcher persistente mejora con cada revisión, no solo cuando hay
        # un match perfecto (ver match_learner.py).
        for i, candidate in enumerate(match.candidates):
            self.match_learner.update(candidate.features, 1.0 if i in confirmed else 0.0)

        self.confirmed_resources = {
            key: path for key, path in self.confirmed_resources.items() if key[0] != match.table
        }
        for i in confirmed:
            resource = match.candidates[i].resource
            self.confirmed_resources[(match.table, resource.role)] = resource.path

        if confirmed:
            names = ", ".join(match.candidates[i].resource.class_name for i in confirmed)
            self.model_resource_status_label.setText(f"Resource(s) confirmado(s): {names}")
        else:
            self.model_resource_status_label.setText(
                "Confirmado: no hay Resource existente para este Model — se genera uno nuevo."
            )

    def _populate_grid(self) -> None:
        self.grid.setRowCount(len(self.current_columns))
        for row, column in enumerate(self.current_columns):
            resolution = self.current_resolutions.get(column.name)

            self.grid.setItem(row, 0, QTableWidgetItem(column.name))
            self.grid.setItem(row, 1, QTableWidgetItem(column.sql_type))
            self.grid.setItem(row, 2, QTableWidgetItem("sí" if column.nullable else "no"))

            include_cb = QCheckBox()
            include_cb.setChecked(True)
            self.grid.setCellWidget(row, 3, include_cb)

            # "Relación" es un checkbox propio, independiente de "Tiny" — el
            # mismo campo puede necesitar mostrarse en {Modulo}RelationResource
            # (lo carga OTRO módulo con whenLoaded()) sin necesariamente ir en
            # {Modulo}TinyResource (?tiny=true del propio módulo), o viceversa.
            # Ver ApiResponse.md#Resource triple. Va antes que "Tiny" en la
            # grilla: es la que más se usa en la práctica (casi toda FK la
            # necesita), "Tiny" es la excepción.
            relation_cb = QCheckBox()
            relation_cb.setChecked(row < 2)  # sugerencia inicial, editable
            self.grid.setCellWidget(row, 4, relation_cb)

            tiny_cb = QCheckBox()
            tiny_cb.setChecked(row < 2)  # misma sugerencia inicial que Relación, editable
            self.grid.setCellWidget(row, 5, tiny_cb)

            fk_combo = QComboBox()
            fk_combo.addItem(_FK_NONE_LABEL)
            fk_combo.addItems(sorted(self.tables))
            if resolution and resolution.table:
                fk_combo.setCurrentText(resolution.table)
                status_label = _FK_STATUS_LABELS.get(resolution.status, resolution.status)
                fk_combo.setToolTip(f"Detectado: {status_label}")
            elif resolution and resolution.status == "ambiguous":
                fk_combo.setCurrentText(_FK_NONE_LABEL)
                fk_combo.setToolTip(
                    "Ambiguo — el desarrollador canceló la resolución asistida. Elegí la tabla a mano."
                )
            else:
                fk_combo.setCurrentText(_FK_NONE_LABEL)
                fk_combo.setToolTip(
                    "Sin relación detectada automáticamente — se puede asignar igual a mano "
                    "(no hace falta que el nombre de la columna termine en \"_id\")."
                )
            fk_combo.currentTextChanged.connect(
                lambda text, name=column.name: self._on_fk_combo_changed(name, text)
            )
            self.grid.setCellWidget(row, 6, fk_combo)

        self.grid.resizeColumnsToContents()
        # "FK -> tabla" ya no estira para llenar el ancho sobrante (se sacó
        # setStretchLastSection): con nombres de tabla largos igual puede
        # pedir de más, se limita a un ancho legible — el nombre completo
        # sigue disponible al abrir el combo / en el tooltip.
        if self.grid.columnWidth(6) > 220:
            self.grid.setColumnWidth(6, 220)
        self._resize_grid_pane()

    def _resize_grid_pane(self) -> None:
        # Antes el grid ocupaba lo que el splitter le diera de entrada,
        # quedando un bloque vacío enorme debajo de las últimas filas cuando
        # la tabla tenía pocas columnas de negocio. Acá se ajusta el tamaño
        # inicial del panel al contenido real y el resto pasa al preview —
        # sin fijar una altura máxima dura, así que el separador se puede
        # seguir arrastrando a mano si hace falta más lugar.
        self.grid.resizeRowsToContents()
        content_height = (
            self.grid.horizontalHeader().height()
            + self.grid.verticalHeader().length()
            + 2 * self.grid.frameWidth()
            + 8
        )
        pane_height = max(120, min(content_height, 360))
        total = sum(self.splitter.sizes())
        if total <= 0:
            total = pane_height + 500
        self.splitter.setSizes([pane_height, max(200, total - pane_height)])

    def _on_fk_combo_changed(self, column_name: str, table_name: str) -> None:
        """El combo de 'FK -> tabla' es la fuente de verdad al generar (ver
        _build_manifest) — cualquier columna se puede asignar a cualquier
        tabla acá, sin depender de que el nombre termine en '_id'."""
        if table_name == _FK_NONE_LABEL or not table_name:
            self.current_resolutions.pop(column_name, None)
            return

        self.current_resolutions[column_name] = fk_resolver.FkResolution(
            column_name, column_name, [table_name], "manual", table_name
        )
        self.session_resolved_fks[column_name] = table_name
        if self.config:
            self.fk_cache.set(self.config.connection_id, column_name, table_name)

    def _current_field_selection(self) -> tuple[set[str], set[str], set[str]]:
        included: set[str] = set()
        tiny: set[str] = set()
        relation: set[str] = set()
        for row, column in enumerate(self.current_columns):
            include_cb = self.grid.cellWidget(row, 3)
            relation_cb = self.grid.cellWidget(row, 4)
            tiny_cb = self.grid.cellWidget(row, 5)
            if isinstance(include_cb, QCheckBox) and include_cb.isChecked():
                included.add(column.name)
            if isinstance(tiny_cb, QCheckBox) and tiny_cb.isChecked():
                tiny.add(column.name)
            if isinstance(relation_cb, QCheckBox) and relation_cb.isChecked():
                relation.add(column.name)
        return included, tiny, relation

    def _build_manifest(self) -> generator.ModuleManifest | None:
        if not self.current_table:
            return None
        included, tiny, relation = self._current_field_selection()
        fk_resolutions = {name: res for name, res in self.current_resolutions.items() if res.table}
        user_model_class = self.user_model_input.text().strip() or generator.DEFAULT_USER_MODEL_CLASS
        connection_name = self.connection_name_input.text().strip() or self.database_input.text().strip() or "mysql"
        return generator.build_manifest(
            self.current_table,
            self.current_columns,
            fk_resolutions=fk_resolutions,
            unique_indexes=self.current_unique_indexes,
            included_fields=included,
            tiny_fields=tiny,
            relation_fields=relation,
            connection_name=connection_name,
            user_model_class=user_model_class,
            supports_pagination=self.pagination_checkbox.isChecked(),
            add_comments=self.add_comments_checkbox.isChecked(),
        )

    def _on_update_preview(self) -> None:
        manifest = self._build_manifest()
        if manifest is None:
            return
        self.current_manifest = manifest
        contents = generator.render_all(manifest)
        for key, content in contents.items():
            if key in self.preview_widgets:
                self.preview_widgets[key].setPlainText(content)

    def _on_toggle_preview_popout(self) -> None:
        if self._preview_popout is not None:
            self._preview_popout.close()
            return
        self.preview_layout.removeWidget(self.preview_tabs)
        self._preview_popout = _PreviewPopout(self.preview_tabs, self._on_preview_popout_closed, self)
        self.preview_popout_btn.setText("Volver al panel ↙")
        self._preview_popout.show()

    def _on_preview_popout_closed(self) -> None:
        self._preview_popout = None
        self.preview_popout_btn.setText("Ampliar preview ↗")
        self.preview_layout.addWidget(self.preview_tabs, stretch=1)

    def _on_generate(self) -> None:
        manifest = self._build_manifest()
        if manifest is None:
            return

        if not self.backend_root or not self.frontend_root:
            QMessageBox.warning(
                self,
                "Faltan proyectos destino",
                "Elegí la raíz del proyecto backend y del frontend antes de generar.",
            )
            return

        use_separate_output = self.separate_output_checkbox.isChecked()
        if use_separate_output and (not self.output_backend_root or not self.output_frontend_root):
            QMessageBox.warning(
                self,
                "Falta la carpeta de salida",
                "Elegí la carpeta de salida (backend y frontend) o desmarcá "
                "\"Generar en una carpeta de salida separada\".",
            )
            return
        write_backend_root = self.output_backend_root if use_separate_output else self.backend_root
        write_frontend_root = self.output_frontend_root if use_separate_output else self.frontend_root

        unresolved = [name for name, res in self.current_resolutions.items() if res.status == "ambiguous"]
        if unresolved:
            proceed = QMessageBox.question(
                self,
                "FKs sin resolver",
                "Hay columnas FK sin resolver: " + ", ".join(unresolved) +
                "\nSe van a generar sin relación. ¿Continuar igual?",
            )
            if proceed != QMessageBox.Yes:
                return

        # Si el preview nunca se actualizó a mano, lo generamos ahora para no
        # escribir pestañas vacías.
        if self.current_manifest is None:
            self._on_update_preview()

        contents = {key: widget.toPlainText() for key, widget in self.preview_widgets.items()}

        # Si alguno de los archivos que este módulo va a escribir ya existe
        # en el destino (se está regenerando, o un proyecto legado que por
        # casualidad ya usa esa misma ruta convencional) se confirma antes
        # de pisarlo — antes se sobreescribía todo en silencio, con riesgo
        # de perder un Model/Resource hecho a mano.
        existing = generator.existing_target_files(manifest, write_backend_root, write_frontend_root, contents)

        # Esto cubre solo la ruta convencional -- un Resource/Model legado
        # con otro nombre/ubicación lo detecta model_resource_scan.py (ver
        # "Revisar Model/Resource detectado…" en el análisis de la tabla).
        # El Model detectado se suma directo (es casi siempre inequívoco:
        # nombre literal de tabla o `$table` declarado); los Resources solo
        # si el desarrollador los confirmó a mano, nunca por su cuenta.
        match = self.current_model_resource_match
        if match is not None and match.table == manifest.table:
            if match.model is not None and "model" in contents and "model" not in existing:
                existing["model"] = match.model.path
            for role in ("resource", "relation_resource", "tiny_resource"):
                path = self.confirmed_resources.get((manifest.table, role))
                if path is not None and role in contents and role not in existing:
                    existing[role] = path

        if existing:
            titles = dict(_PREVIEW_TABS)
            listing = "\n".join(f"- {titles.get(key, key)}: {path}" for key, path in existing.items())
            proceed = QMessageBox.question(
                self,
                "Ya existen archivos en el destino",
                "Estos archivos ya existen y se van a sobreescribir:\n\n" + listing + "\n\n¿Continuar?",
            )
            if proceed != QMessageBox.Yes:
                return

        try:
            written = generator.write_files(
                manifest,
                write_backend_root,
                write_frontend_root,
                contents,
                write_audit_interface=self.write_audit_checkbox.isChecked(),
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error al generar archivos", str(exc))
            return

        elapsed = (
            time.monotonic() - self._analysis_started_at
            if self._analysis_started_at is not None
            else 0.0
        )
        entry = logs.build_entry(
            table=manifest.table,
            fk_count=len(manifest.relations),
            field_count=len([f for f in manifest.fields if f.include]),
            elapsed_seconds=elapsed,
            contents_by_key={key: contents[key] for key in written if key in contents},
        )
        logs.append_entry(entry)
        self._analysis_started_at = None

        listing = "\n".join(f"- {p}" for p in written.values())
        QMessageBox.information(
            self,
            "Archivos generados",
            f"Se generaron {entry.file_count} archivos ({entry.line_count} líneas) en "
            f"{entry.elapsed_minutes} min:\n{listing}\n\n"
            "Ver Logs → Historial de generación… para el detalle completo.",
        )

    def _on_backup(self) -> None:
        if not self.config:
            return

        options = BackupOptionsDialog(self)
        if options.exec() != QDialog.Accepted:
            return
        scope = options.scope()
        show_log = options.show_log()

        default_name = f"{self.config.database}_backup.sql"
        output_path, _ = QFileDialog.getSaveFileName(self, "Guardar backup como", default_name, "SQL (*.sql)")
        if not output_path:
            return

        progress = BackupProgressDialog(len(self.tables), show_log, self)
        worker = BackupWorker(self.config, Path(output_path), scope, parent=self)
        self._backup_worker = worker  # mantener referencia viva mientras corre

        worker.progress.connect(progress.append_line)
        worker.succeeded.connect(progress.show_success)
        worker.failed.connect(progress.show_error)
        worker.start()
        progress.exec()


def main() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()  # aplica su propio tema (persistido) en __init__
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
