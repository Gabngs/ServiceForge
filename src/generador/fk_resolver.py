"""Detección de relaciones FK -> belongsTo (columna `{campo}_id` -> tabla candidata).

Implementa el algoritmo documentado en Script Generador Backend.md:
1. `{campo}_id` -> quitar sufijo `_id` -> `{campo}`
2. Buscar coincidencias exactas / singular-plural / con-sin prefijo del proyecto
3. Exactamente 1 coincidencia -> resolver automático (owner key siempre `pkid`)
4. 0 o 2+ coincidencias -> ambiguo, requiere resolución manual (ver GUI)
5. La resolución manual se cachea por (conexión, columna) para no repreguntar
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FkResolution:
    column: str
    base_name: str
    candidates: list[str]
    status: str  # "auto" | "ambiguous" | "resolved_from_cache" | "from_mapping_file"
    table: str | None  # tabla resuelta, si status != "ambiguous"


def _name_variants(base: str) -> set[str]:
    variants = {base, f"{base}s", f"{base}es"}
    if base.endswith("s") and len(base) > 1:
        variants.add(base[:-1])
    return variants


def find_fk_candidates(column_name: str, prefijo: str, tables: list[str]) -> tuple[str | None, list[str]]:
    """Retorna (base_name, tablas_candidatas) para una columna `{campo}_id`.

    `base_name` es None si `column_name` no termina en `_id` (no es una FK).
    """
    if not column_name.endswith("_id") or column_name == "_id":
        return None, []

    base = column_name[: -len("_id")]
    variants = _name_variants(base)
    all_candidate_names = set(variants) | {f"{prefijo}_{v}" for v in variants}

    lookup = {t.lower(): t for t in tables}
    matched = [lookup[name.lower()] for name in all_candidate_names if name.lower() in lookup]
    # Orden estable y sin duplicados, preservando el nombre real de la tabla.
    seen: set[str] = set()
    unique_matched = []
    for t in matched:
        if t not in seen:
            seen.add(t)
            unique_matched.append(t)
    return base, unique_matched


class FkResolutionCache:
    """Persiste resoluciones manuales de FK por conexión + columna.

    Formato en disco: {"{connection_id}::{column}": "tabla_resuelta"}
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_cache_path()
        self._data: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _key(connection_id: str, column: str) -> str:
        return f"{connection_id}::{column}"

    def get(self, connection_id: str, column: str) -> str | None:
        return self._data.get(self._key(connection_id, column))

    def set(self, connection_id: str, column: str, table: str) -> None:
        self._data[self._key(connection_id, column)] = table
        self._save()


def default_cache_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "GeneradorFrontBack" / "fk_resolutions.json"


def resolve_fk(
    column_name: str,
    prefijo: str,
    tables: list[str],
    *,
    connection_id: str,
    cache: FkResolutionCache,
    imported_mapping: dict[str, str] | None = None,
) -> FkResolution | None:
    """Resuelve una columna FK.

    Orden de prioridad: mapeo importado (`.md` compartido por el equipo, ver
    table_mapping.py) > caché local de resoluciones manuales > detección
    automática por convención de nombres > ambiguo (requiere al desarrollador).

    Retorna None si `column_name` no es una FK (no termina en `_id`).
    """
    base, candidates = find_fk_candidates(column_name, prefijo, tables)
    if base is None:
        return None

    mapped_table = (imported_mapping or {}).get(column_name)
    if mapped_table:
        return FkResolution(column_name, base, candidates, "from_mapping_file", mapped_table)

    cached_table = cache.get(connection_id, column_name)
    if cached_table:
        return FkResolution(column_name, base, candidates, "resolved_from_cache", cached_table)

    if len(candidates) == 1:
        return FkResolution(column_name, base, candidates, "auto", candidates[0])

    return FkResolution(column_name, base, candidates, "ambiguous", None)
