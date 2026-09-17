"""Historial de generaciones — persistido para sustentar la medición de lead
time por módulo (ver 3.2.5 del informe de prácticas: comparación de tiempo
manual vs. tiempo con la herramienta).

Cada vez que la GUI escribe archivos de un módulo, registra una entrada con
lo que la propia herramienta puede medir objetivamente: cuántas FKs y campos
tenía el módulo, cuánto tiempo pasó desde que se analizó la tabla hasta que
se confirmó "Generar archivos", cuántos archivos se escribieron y cuántas
líneas de código se generaron. El tiempo del proceso MANUAL sigue siendo un
dato que el desarrollador cronometra aparte — la herramienta no puede medir
un proceso que no ejecutó.
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class GenerationLogEntry:
    timestamp: str  # ISO 8601 UTC — momento en que se confirmó "Generar archivos"
    table: str
    fk_count: int
    field_count: int
    elapsed_seconds: float  # desde "Analizar" hasta "Generar archivos" en esta sesión
    file_count: int
    line_count: int
    files: list[str] = field(default_factory=list)  # rutas relativas escritas, para detalle

    @property
    def elapsed_minutes(self) -> float:
        return round(self.elapsed_seconds / 60, 2)


def default_log_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "ServiceForge" / "generation_log.json"


def build_entry(
    *,
    table: str,
    fk_count: int,
    field_count: int,
    elapsed_seconds: float,
    contents_by_key: dict[str, str],
) -> GenerationLogEntry:
    """`contents_by_key` es el subconjunto de `contents` efectivamente escrito
    (las claves de `written`, ver generator.write_files) — cuenta archivos y
    líneas sobre lo que quedó en disco, no sobre el render "de fábrica"."""
    line_count = sum(content.count("\n") + 1 for content in contents_by_key.values())
    return GenerationLogEntry(
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        table=table,
        fk_count=fk_count,
        field_count=field_count,
        elapsed_seconds=round(elapsed_seconds, 1),
        file_count=len(contents_by_key),
        line_count=line_count,
        files=sorted(contents_by_key.keys()),
    )


def load_log(path: Path | None = None) -> list[GenerationLogEntry]:
    path = path or default_log_path()
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    entries = []
    for item in raw:
        try:
            entries.append(GenerationLogEntry(**item))
        except TypeError:
            continue  # entrada de un formato viejo/corrupto — se ignora, no rompe el resto
    return entries


def append_entry(entry: GenerationLogEntry, path: Path | None = None) -> None:
    path = path or default_log_path()
    entries = load_log(path)
    entries.append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([asdict(e) for e in entries], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


CSV_HEADERS = [
    "Fecha (UTC)",
    "Módulo",
    "# de FK",
    "# de campos",
    "Tiempo ServiceForge (min)",
    "Archivos generados",
    "Líneas generadas",
]


def export_csv(entries: list[GenerationLogEntry], path: Path) -> None:
    """Formato pensado para pegar directo en la planilla de 3.2.5 (Módulo, #FK,
    #campos, Tiempo con la herramienta, Archivos, Líneas) — falta agregar a mano
    solo la columna de tiempo manual y la de reducción, que la herramienta no
    puede medir."""
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(CSV_HEADERS)
        for e in entries:
            writer.writerow(
                [e.timestamp, e.table, e.fk_count, e.field_count, e.elapsed_minutes, e.file_count, e.line_count]
            )
