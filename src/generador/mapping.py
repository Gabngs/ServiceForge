"""Mapeo columna SQL -> reglas de validación Laravel, casts y tipos TypeScript.

Refleja la tabla de referencia documentada en el estándar de backend
(ver "Mapeo de columnas -> reglas de validación" en Script Generador Backend.md).
No inventa reglas nuevas: cada rama de este módulo tiene que poder señalarse
a una fila de esa tabla.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .db import Column

# Campos que nunca van en fillable de usuario ni en validación — los asigna
# el CrudService/Laravel automáticamente.
EXCLUDED_FIELDS = frozenset(
    {
        "pkid",
        "id",
        "created_at",
        "updated_at",
        "deleted_at",
        "created_by_id",
        "updated_by_id",
        "deleted_by_id",
    }
)


def soft_delete_column(columns: list["Column"]) -> str | None:
    """None si la tabla usa `deleted_at` (el default de SoftDeletes de
    Laravel, no hace falta declarar nada de más) -- `'deleted'` si la tabla
    es legada y usa ese nombre en su lugar. En ese caso el Model generado
    tiene que declarar `const DELETED_AT = 'deleted';` (ver Model.php.j2)
    para que el trait SoftDeletes la use en vez de asumir `deleted_at` y
    romper en cualquier query/delete/restore contra una columna que no
    existe. Si por algún motivo la tabla tiene las dos, gana `deleted_at`
    (el caso real) y `deleted` se trata como columna de negocio común."""
    names = {c.name for c in columns}
    if "deleted" in names and "deleted_at" not in names:
        return "deleted"
    return None


def business_columns(columns: list["Column"]) -> list["Column"]:
    """Columnas de negocio: saca siempre las de EXCLUDED_FIELDS, y además la
    columna de soft-delete legada (`deleted`) cuando la tabla la usa en vez
    de `deleted_at` -- ver `soft_delete_column`. Único punto de esta
    exclusión: tanto el grid de la GUI como `generator.build_manifest` la
    usan, para no repetir la detección en los dos lugares."""
    excluded = set(EXCLUDED_FIELDS)
    legacy_soft_delete = soft_delete_column(columns)
    if legacy_soft_delete:
        excluded.add(legacy_soft_delete)
    return [c for c in columns if c.name not in excluded]

# Familias de tipos SQL que comparten regla de validación.
_TEXT_FAMILY = {"text", "longtext", "mediumtext", "tinytext"}
_INT_FAMILY = {"int", "integer", "bigint", "smallint", "mediumint"}
_DATETIME_FAMILY = {"datetime", "timestamp"}

_TYPE_RE = re.compile(r"^\s*(\w+)\s*(\(([^)]*)\))?", re.IGNORECASE)
_ENUM_VALUE_RE = re.compile(r"'((?:[^'\\]|\\.)*)'")


@dataclass(frozen=True)
class ParsedType:
    base: str
    length: int | None = None
    precision: int | None = None
    scale: int | None = None
    enum_values: tuple[str, ...] = field(default_factory=tuple)
    raw: str = ""


def parse_sql_type(sql_type: str) -> ParsedType:
    """Parsea un tipo SQL crudo (tal como lo devuelve DESCRIBE) a sus partes."""
    raw = sql_type.strip()
    match = _TYPE_RE.match(raw)
    if not match:
        return ParsedType(base=raw.lower(), raw=raw)

    base = match.group(1).lower()
    inside = match.group(3)

    if base in ("varchar", "char") and inside:
        return ParsedType(base=base, length=int(inside.strip()), raw=raw)

    if base in ("decimal", "numeric") and inside:
        parts = [p.strip() for p in inside.split(",")]
        precision = int(parts[0]) if parts and parts[0].isdigit() else None
        scale = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
        return ParsedType(base="decimal", precision=precision, scale=scale, raw=raw)

    if base in ("enum", "set") and inside:
        values = tuple(_ENUM_VALUE_RE.findall(inside))
        return ParsedType(base=base, enum_values=values, raw=raw)

    if inside and inside.strip().isdigit():
        return ParsedType(base=base, length=int(inside.strip()), raw=raw)

    return ParsedType(base=base, raw=raw)


def _normalized_family(parsed: ParsedType) -> str:
    if parsed.base in _TEXT_FAMILY:
        return "text"
    if parsed.base in _INT_FAMILY:
        return "int"
    if parsed.base in _DATETIME_FAMILY:
        return "datetime"
    return parsed.base


def validation_rules(
    parsed: ParsedType,
    nullable: bool,
    *,
    is_fk: bool = False,
    fk_table: str | None = None,
) -> tuple[str, str]:
    """Retorna (regla_store, regla_update) para Store{Modulo}Request / Update{Modulo}Request."""
    if is_fk:
        table = fk_table or "{tabla}"
        base = f"string|exists:{table},id"
        if nullable:
            return f"nullable|{base}", f"nullable|{base}"
        return f"required|{base}", f"sometimes|{base}"

    family = _normalized_family(parsed)
    presence_required = "nullable" if nullable else "required"
    presence_update = "nullable" if nullable else "sometimes"

    if family in ("varchar",):
        return (
            f"{presence_required}|string|max:{parsed.length or 255}",
            f"{presence_update}|string|max:{parsed.length or 255}",
        )
    if family == "char":
        return (
            f"{presence_required}|string|size:{parsed.length or 1}",
            f"{presence_update}|string|size:{parsed.length or 1}",
        )
    if family == "text":
        return f"{presence_required}|string", f"{presence_update}|string"
    if family == "int":
        return f"{presence_required}|integer", f"{presence_update}|integer"
    if family == "tinyint" and parsed.length == 1:
        # Booleano: el estándar usa `sometimes` en ambas reglas, tenga o no default.
        return "sometimes|boolean", "sometimes|boolean"
    if family == "decimal":
        return f"{presence_required}|numeric", f"{presence_update}|numeric"
    if family == "date":
        return f"{presence_required}|date", f"{presence_update}|date"
    if family == "datetime":
        fmt = "date_format:Y-m-d H:i:s"
        return f"{presence_required}|{fmt}", f"{presence_update}|{fmt}"
    if family == "json":
        return f"{presence_required}|array", f"{presence_update}|array"
    if family == "enum" and parsed.enum_values:
        values = ",".join(parsed.enum_values)
        return f"{presence_required}|in:{values}", f"{presence_update}|in:{values}"

    # Fallback conservador para tipos no listados en el estándar — nunca reventar.
    return f"{presence_required}|string", f"{presence_update}|string"


def laravel_cast(parsed: ParsedType) -> str | None:
    """Cast automático a declarar en `$casts` del Model, si aplica."""
    if parsed.base == "tinyint" and parsed.length == 1:
        return "boolean"
    if parsed.base == "decimal" and parsed.scale is not None:
        return f"decimal:{parsed.scale}"
    if parsed.base == "json":
        return "array"
    if parsed.base == "date":
        return "date"
    if parsed.base in _DATETIME_FAMILY:
        return "datetime"
    return None


def is_searchable(parsed: ParsedType) -> bool:
    """Campos elegibles para `$columnSearch` (LIKE) en la clase Filters — ver useFilters.md."""
    return _normalized_family(parsed) in ("varchar", "char", "text")


def oa_type(parsed: ParsedType) -> str:
    """Tipo OpenAPI (`@OA\\Property(type=...)`) equivalente, para Swagger."""
    family = _normalized_family(parsed)
    if family in ("varchar", "char", "text", "date", "datetime"):
        return "string"
    if family == "tinyint" and parsed.length == 1:
        return "boolean"
    if family == "int":
        return "integer"
    if family == "decimal":
        return "number"
    if family == "json":
        return "array"
    return "string"


def oa_format(parsed: ParsedType) -> str | None:
    """`format` de OpenAPI, cuando el `type` por sí solo no alcanza."""
    family = _normalized_family(parsed)
    if family == "date":
        return "date"
    if family == "datetime":
        return "date-time"
    if parsed.base == "decimal":
        return "float"
    return None


def ts_type(parsed: ParsedType, *, is_fk: bool = False) -> str:
    """Tipo TypeScript equivalente, para las interfaces del frontend."""
    if is_fk:
        return "string"  # UUID en Create/Update; en I{Modulo} se sobreescribe con la Tiny relacionada

    family = _normalized_family(parsed)
    if family in ("varchar", "char", "text", "date", "datetime"):
        return "string"
    if family == "tinyint" and parsed.length == 1:
        return "boolean"
    if family in ("int", "decimal"):
        return "number"
    if family == "json":
        return "unknown[]"
    if family == "enum" and parsed.enum_values:
        return " | ".join(f"'{v}'" for v in parsed.enum_values)
    return "unknown"
