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
from PySide6.QtGui import QAction, QTextCursor
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
    QSplitter,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import __version__, backup, db, fk_resolver, generator, logs, mapping, naming, project_scan, table_mapping
from .settings import Settings
from .theme import build_stylesheet, status_colors

_GRID_COLUMNS = ["Campo", "Tipo SQL", "Nullable", "Incluir", "Tiny", "FK -> tabla"]

_FK_STATUS_LABELS = {
    "auto": "auto",
    "resolved_from_cache": "caché local",
    "from_mapping_file": "mapeo importado",
}

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


class ProjectScanDialog(QDialog):
    """Muestra el resultado de analizar el proyecto backend — solo lectura,
    nunca edita RouteServiceProvider/bootstrap/app.php en automático."""

    def __init__(self, result: project_scan.ProjectScanResult, colors: dict[str, str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Análisis del proyecto backend")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)

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

        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


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


class _CodeEditor(QPlainTextEdit):
    """QPlainTextEdit con autocompletado "por palabras" (sin IA / sin Copilot):
    combina una lista curada de keywords de PHP/Laravel (o TS) con las
    palabras que ya aparecen en el propio documento — el mismo patrón que el
    ejemplo "Custom Completer" de Qt. Se dispara solo al escribir 2+
    caracteres, o a mano con Ctrl+Espacio."""

    def __init__(self, keywords: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._static_words = set(keywords)

        self.completer = QCompleter(self)
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.activated.connect(self._insert_completion)

        self._refresh_completion_model()
        self.textChanged.connect(self._refresh_completion_model)

    def _refresh_completion_model(self) -> None:
        doc_words = set(re.findall(r"[A-Za-z_\\][A-Za-z0-9_\\]{2,}", self.toPlainText()))
        model = QStringListModel(sorted(self._static_words | doc_words), self.completer)
        self.completer.setModel(model)

    def _text_under_cursor(self) -> str:
        cursor = self.textCursor()
        cursor.select(QTextCursor.WordUnderCursor)
        return cursor.selectedText()

    def _insert_completion(self, completion: str) -> None:
        cursor = self.textCursor()
        extra = len(completion) - len(self.completer.completionPrefix())
        cursor.movePosition(QTextCursor.Left)
        cursor.movePosition(QTextCursor.EndOfWord)
        cursor.insertText(completion[-extra:])
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

        help_menu = menu_bar.addMenu("A&yuda")
        about_action = QAction("Acerca de", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        top_row = QHBoxLayout()
        top_row.addWidget(self._build_connection_box(), stretch=2)
        top_row.addWidget(self._build_project_box(), stretch=3)
        root.addLayout(top_row)

        table_row = QHBoxLayout()
        self.table_combo = QComboBox()
        self.table_combo.setMinimumWidth(240)
        self.analyze_btn = QPushButton("→ Analizar")
        self.analyze_btn.clicked.connect(self._on_analyze)
        self.analyze_btn.setEnabled(False)
        table_row.addWidget(QLabel("Tabla:"))
        table_row.addWidget(self.table_combo)
        table_row.addWidget(self.analyze_btn)
        table_row.addStretch()
        root.addLayout(table_row)

        # Grid (mapeo de columnas) y preview en un splitter — el preview es
        # donde se edita el código antes de generar, necesita poder crecer.
        splitter = QSplitter(Qt.Vertical)

        grid_container = QWidget()
        grid_layout = QVBoxLayout(grid_container)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.addWidget(QLabel("Mapeo de columnas"))
        self.grid = QTableWidget(0, len(_GRID_COLUMNS))
        self.grid.setHorizontalHeaderLabels(_GRID_COLUMNS)
        self.grid.horizontalHeader().setStretchLastSection(True)
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
        self.preview_widgets: dict[str, QPlainTextEdit] = {}
        for key, title in _PREVIEW_TABS:
            keywords = _TS_INTERFACE_COMPLETIONS if title.endswith(".ts") else _PHP_LARAVEL_COMPLETIONS
            editor = _CodeEditor(keywords)
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
        root.addWidget(splitter, stretch=1)

        self.status_label = QLabel("Sin conexión.")
        root.addWidget(self.status_label)

    def _build_connection_box(self) -> QGroupBox:
        box = QGroupBox("Conexión — BD objetivo")
        form = QFormLayout(box)

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
        form.addRow(connect_row)

        return box

    def _build_project_box(self) -> QGroupBox:
        box = QGroupBox("Proyectos destino")
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

        self.write_audit_checkbox = QCheckBox(
            "Generar audit-user.interface.ts compartido (desmarcar si el proyecto ya lo tiene)"
        )
        self.write_audit_checkbox.setChecked(False)
        form.addRow(self.write_audit_checkbox)

        return box

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
        self._set_connection_status("ok", f"Conectado — {len(self.tables)} tablas")

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
        ProjectScanDialog(result, self.colors, self).exec()

    # ------------------------------------------------------------- análisis
    def _on_analyze(self) -> None:
        if not self.conn or not self.config:
            return
        table = self.table_combo.currentText()
        if not table:
            return

        # Arranca acá el cronómetro del lead time con la herramienta para este
        # módulo (ver logs.py / 3.2.5 del informe) — se cierra al confirmar
        # "Generar archivos".
        self._analysis_started_at = time.monotonic()

        try:
            columns = db.describe_table(self.conn, table)
            unique_idx = db.unique_indexes(self.conn, table)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error al analizar la tabla", str(exc))
            return

        prefijo, _ = naming.split_prefijo_modulo(table)
        business_columns = [c for c in columns if c.name not in mapping.EXCLUDED_FIELDS]

        resolutions: dict[str, fk_resolver.FkResolution] = {}
        ambiguous: list[fk_resolver.FkResolution] = []
        for column in business_columns:
            resolution = fk_resolver.resolve_fk(
                column.name,
                prefijo,
                self.tables,
                connection_id=self.config.connection_id,
                cache=self.fk_cache,
                imported_mapping=self.imported_mapping,
            )
            if resolution is None:
                continue
            resolutions[column.name] = resolution
            if resolution.status == "ambiguous":
                ambiguous.append(resolution)

        if ambiguous:
            dialog = FkResolutionDialog(ambiguous, self.tables, self)
            if dialog.exec() == QDialog.Accepted:
                chosen = dialog.resolutions()
                for column, table_name in chosen.items():
                    self.fk_cache.set(self.config.connection_id, column, table_name)
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

            tiny_cb = QCheckBox()
            tiny_cb.setChecked(row < 2)  # sugerencia inicial, editable
            self.grid.setCellWidget(row, 4, tiny_cb)

            if resolution is None:
                fk_text = ""
            elif resolution.table:
                status_label = _FK_STATUS_LABELS.get(resolution.status, resolution.status)
                fk_text = f"{resolution.table} ({status_label})"
            else:
                fk_text = "⚠ sin resolver"
            self.grid.setItem(row, 5, QTableWidgetItem(fk_text))

        self.grid.resizeColumnsToContents()

    def _current_field_selection(self) -> tuple[set[str], set[str]]:
        included: set[str] = set()
        tiny: set[str] = set()
        for row, column in enumerate(self.current_columns):
            include_cb = self.grid.cellWidget(row, 3)
            tiny_cb = self.grid.cellWidget(row, 4)
            if isinstance(include_cb, QCheckBox) and include_cb.isChecked():
                included.add(column.name)
            if isinstance(tiny_cb, QCheckBox) and tiny_cb.isChecked():
                tiny.add(column.name)
        return included, tiny

    def _build_manifest(self) -> generator.ModuleManifest | None:
        if not self.current_table or not self.config:
            return None
        included, tiny = self._current_field_selection()
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
            connection_name=connection_name,
            user_model_class=user_model_class,
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

        try:
            written = generator.write_files(
                manifest,
                self.backend_root,
                self.frontend_root,
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
