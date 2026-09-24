"""Mapa del proyecto: lo que el desarrollador CONFIRMÓ sobre qué archivo usa cada tabla, guardado
como notas `.md` con wikilinks (`[[...]]`, el formato de Obsidian) -- legibles, versionables y
portables entre PCs, a diferencia de los pesos de la red neuronal.

Una nota por tabla (`{tabla}.md`) y una nota `_estructura.md` con la estructura de carpetas elegida:

    # catalogo_tiposistema

    ## Archivos
    - model: [[catalogo_tiposistema]] · `App\\Models\\dbsiaw\\catalogo_tiposistema` · `app/Models/dbsiaw/catalogo_tiposistema.php`
    - relation_resource: [[catalogo_tiposistemaRelationResource]] · `App\\...` · `app/...`

    ## Relaciones
    - tipo_sistema_id → [[catalogo_tiposistema]]

Las relaciones apuntan a otra nota de tabla, así que Obsidian dibuja el grafo entre módulos.

Regla: solo se guarda lo que el desarrollador validó (ver gui.RelationsDialog); una sugerencia de
la red sin confirmar nunca llega acá. Y una vez guardada vale para CUALQUIER módulo que use esa
tabla: si `catalogo_tiposistema` ya tiene su RelationResource confirmado, el próximo módulo con una
FK a esa tabla lo trae precargado.

Las rutas son relativas a la raíz del backend, así el mapa funciona igual en otra PC.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import layout as layout_module
from .layout import StructureLayout

# Roles de archivo de una tabla que se recuerdan.
FILE_ROLES: tuple[str, ...] = ("model", "resource", "relation_resource", "tiny_resource")

LAYOUT_NOTE = "_estructura.md"
DECISION_STANDARD = "estandar"
DECISION_PROJECT = "proyecto"
DECISION_CUSTOM = "personalizado"
DECISIONS = (DECISION_STANDARD, DECISION_PROJECT, DECISION_CUSTOM)

_FILE_LINE_RE = re.compile(r"^- (\w+): \[\[(?P<link>[^\]]+)\]\] · `(?P<fqcn>[^`]*)`(?: · `(?P<path>[^`]*)`)?\s*$")
_REL_LINE_RE = re.compile(r"^- (?P<column>[^\s→]+) → \[\[(?P<table>[^\]]+)\]\]\s*$")
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass
class ClassRef:
    fqcn: str
    path: str = ""  # relativa a la raíz del backend, con '/'

    @property
    def short(self) -> str:
        return self.fqcn.rsplit("\\", 1)[-1]


@dataclass
class TableNote:
    table: str
    files: dict[str, ClassRef] = field(default_factory=dict)  # rol -> clase confirmada
    relations: dict[str, str] = field(default_factory=dict)  # columna FK -> tabla relacionada


def default_maps_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "ServiceForge" / "mapas"


def project_key(backend_root: Path | str) -> str:
    """Nombre de la carpeta del mapa de un proyecto: el nombre de su carpeta raíz. No la ruta
    completa, para que el mismo proyecto en otra PC (otra ruta) use el mismo mapa."""
    name = Path(backend_root).name or "proyecto"
    return _SAFE_NAME_RE.sub("_", name)


def _note_file_name(table: str) -> str:
    return _SAFE_NAME_RE.sub("_", table) + ".md"


def render_note(note: TableNote) -> str:
    lines = [
        f"# {note.table}",
        "",
        "> Mapa de ServiceForge. Lo confirmó el desarrollador; se puede editar a mano.",
        "",
        "## Archivos",
    ]
    for role in FILE_ROLES:
        ref = note.files.get(role)
        if ref is None:
            continue
        line = f"- {role}: [[{ref.short}]] · `{ref.fqcn}`"
        if ref.path:
            line += f" · `{ref.path}`"
        lines.append(line)
    if note.relations:
        lines += ["", "## Relaciones"]
        for column, related in sorted(note.relations.items()):
            lines.append(f"- {column} → [[{related}]]")
    lines.append("")
    return "\n".join(lines)


def parse_note(table: str, text: str) -> TableNote:
    note = TableNote(table=table)
    for raw in text.splitlines():
        line = raw.rstrip()
        match = _FILE_LINE_RE.match(line)
        if match and match.group(1) in FILE_ROLES:
            note.files[match.group(1)] = ClassRef(match.group("fqcn"), match.group("path") or "")
            continue
        match = _REL_LINE_RE.match(line)
        if match:
            note.relations[match.group("column")] = match.group("table")
    return note


def render_layout_note(layout: StructureLayout, decision: str) -> str:
    lines = [
        "# Estructura del proyecto",
        "",
        "> Dónde genera ServiceForge cada archivo. Los tokens son `{table}`, `{Table}`, `{prefijo}`, `{Prefijo}`, `{modulo}` y `{Modulo}`.",
        "",
        f"Decisión: {decision}",
        "",
        "| Rol | Carpeta | Nombre | Namespace | Origen |",
        "|---|---|---|---|---|",
    ]
    for role in layout_module.ROLES:
        placement = layout.placement(role)
        lines.append(
            f"| {role} | {placement.directory} | {placement.name} | {placement.namespace or ''} | {layout.origin(role)} |"
        )
    lines.append("")
    return "\n".join(lines)


def parse_layout_note(text: str) -> tuple[StructureLayout, str] | None:
    decision = DECISION_STANDARD
    data: dict[str, dict[str, str | None]] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if line.lower().startswith("decisión:") or line.lower().startswith("decision:"):
            value = line.split(":", 1)[1].strip().lower()
            if value in DECISIONS:
                decision = value
            continue
        if not line.startswith("|"):
            continue
        cells = [c.strip().strip("`") for c in line.strip("|").split("|")]
        if len(cells) < 5 or cells[0] not in layout_module.ROLES:
            continue
        role, directory, name, namespace, origin = cells[:5]
        data[role] = {"directory": directory, "name": name, "namespace": namespace or None, "origin": origin}
    if not data:
        return None
    return StructureLayout.from_dict(data), decision


class RelationMap:
    """Las notas de un proyecto, en una carpeta."""

    def __init__(self, folder: Path) -> None:
        self.folder = Path(folder)

    @classmethod
    def for_project(cls, backend_root: Path | str, *, base: Path | None = None) -> "RelationMap":
        return cls((base or default_maps_dir()) / project_key(backend_root))

    # ------------------------------------------------------------ lectura
    def _path(self, table: str) -> Path:
        return self.folder / _note_file_name(table)

    def get(self, table: str) -> TableNote | None:
        path = self._path(table)
        try:
            return parse_note(table, path.read_text(encoding="utf-8"))
        except OSError:
            return None

    def tables(self) -> list[str]:
        if not self.folder.is_dir():
            return []
        return sorted(p.stem for p in self.folder.glob("*.md") if not p.name.startswith("_"))

    def file_for(self, table: str, role: str) -> ClassRef | None:
        note = self.get(table)
        return note.files.get(role) if note else None

    # ---------------------------------------------------------- escritura
    def _write(self, note: TableNote) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        self._path(note.table).write_text(render_note(note), encoding="utf-8")

    def remember(self, table: str, role: str, fqcn: str, path: str = "") -> None:
        """Guarda que `table` usa `fqcn` para `role`. Solo se llama con lo que el desarrollador confirmó."""
        if role not in FILE_ROLES:
            raise ValueError(f"rol desconocido: {role}")
        note = self.get(table) or TableNote(table=table)
        note.files[role] = ClassRef(fqcn, path.replace("\\", "/"))
        self._write(note)

    def forget(self, table: str, role: str) -> None:
        note = self.get(table)
        if note is None or role not in note.files:
            return
        del note.files[role]
        if note.files or note.relations:
            self._write(note)
        else:
            self._path(table).unlink(missing_ok=True)

    def remember_relation(self, table: str, column: str, related_table: str) -> None:
        note = self.get(table) or TableNote(table=table)
        note.relations[column] = related_table
        self._write(note)

    # ---------------------------------------------------------- estructura
    def load_layout(self) -> tuple[StructureLayout, str] | None:
        try:
            return parse_layout_note((self.folder / LAYOUT_NOTE).read_text(encoding="utf-8"))
        except OSError:
            return None

    def save_layout(self, layout: StructureLayout, decision: str) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / LAYOUT_NOTE).write_text(render_layout_note(layout, decision), encoding="utf-8")

    # --------------------------------------------------- exportar / importar
    def export_to(self, destination: Path) -> int:
        """Copia las notas (y la de estructura) a `destination`, por ejemplo una carpeta de un vault de Obsidian."""
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        count = 0
        for source in sorted(self.folder.glob("*.md")) if self.folder.is_dir() else []:
            shutil.copyfile(source, destination / source.name)
            count += 1
        return count

    def import_from(self, source: Path) -> int:
        """Suma las notas de `source` al mapa. Lo que ya hay se conserva salvo que la nota importada
        diga algo distinto para el mismo rol/columna: ahí gana la importada (es más nueva a propósito).
        Devuelve cuántas notas de tabla se leyeron."""
        source = Path(source)
        count = 0
        for path in sorted(source.glob("*.md")):
            if path.name == LAYOUT_NOTE:
                parsed = parse_layout_note(path.read_text(encoding="utf-8"))
                if parsed is not None and self.load_layout() is None:
                    self.save_layout(*parsed)
                continue
            if path.name.startswith("_"):
                continue
            incoming = parse_note(path.stem, path.read_text(encoding="utf-8"))
            if not incoming.files and not incoming.relations:
                continue
            note = self.get(incoming.table) or TableNote(table=incoming.table)
            note.files.update(incoming.files)
            note.relations.update(incoming.relations)
            self._write(note)
            count += 1
        return count
