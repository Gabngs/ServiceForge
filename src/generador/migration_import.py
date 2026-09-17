"""Lee una migración Laravel (`Schema::create` + `Blueprint`) y la traduce a
la misma forma que usa el flujo de conexión a BD (`db.Column` + índices
únicos) — así el resto del pipeline (fk_resolver, mapeo, preview, generación)
no distingue si el origen fue una conexión real o un archivo/texto de
migración.

Deliberadamente NO es un parser de PHP completo — cubre el subset de la DSL
fluida de `Blueprint` que efectivamente se usa en migraciones reales
(`$table->metodo('col', args...)->modificador()->modificador();`), una
llamada encadenada por línea o statement. Cualquier método no reconocido se
ignora (no revienta el parseo del resto de la tabla).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .db import Column

_TABLE_LITERAL_RE = re.compile(r"Schema::create\(\s*['\"]([A-Za-z0-9_]+)['\"]")
_TABLE_PROPERTY_RE = re.compile(r"protected\s+\$table\s*=\s*['\"]([A-Za-z0-9_]+)['\"]")
_STATEMENT_RE = re.compile(r"\$table\s*(->.*?);", re.DOTALL)
_CALL_RE = re.compile(r"->\s*(\w+)\s*\(")

# Métodos que definen una columna nueva y su tipo SQL base (ver docstring del
# módulo). `None` como longitud/precisión = "usar el default de Laravel".
_COLUMN_TYPE_SQL = {
    "id": "bigint(20) unsigned",
    "bigIncrements": "bigint(20) unsigned",
    "increments": "int(10) unsigned",
    "uuid": "char(36)",
    "integer": "int(11)",
    "unsignedInteger": "int(10) unsigned",
    "bigInteger": "bigint(20)",
    "unsignedBigInteger": "bigint(20) unsigned",
    "tinyInteger": "tinyint(4)",
    "unsignedTinyInteger": "tinyint(3) unsigned",
    "smallInteger": "smallint(6)",
    "unsignedSmallInteger": "smallint(5) unsigned",
    "mediumInteger": "mediumint(9)",
    "unsignedMediumInteger": "mediumint(8) unsigned",
    "boolean": "tinyint(1)",
    "float": "float",
    "double": "double",
    "date": "date",
    "dateTime": "datetime",
    "dateTimeTz": "datetime",
    "time": "time",
    "timeTz": "time",
    "timestamp": "timestamp",
    "timestampTz": "timestamp",
    "year": "year(4)",
    "json": "json",
    "jsonb": "json",
    "text": "text",
    "mediumText": "mediumtext",
    "longText": "longtext",
    "tinyText": "tinytext",
    "foreignId": "bigint(20) unsigned",
    "foreignUuid": "char(36)",
    "rememberToken": "varchar(100)",
}

# Métodos "columna nueva" cuyo primer arg NO es el nombre de columna (se
# resuelven aparte en _apply_statement).
_MULTI_COLUMN_METHODS = {"timestamps", "timestampsTz", "softDeletes", "softDeletesTz"}

# Si el PRIMER método de un statement es uno de estos, es una restricción a
# nivel tabla (posiblemente sobre varias columnas), no la definición de una
# columna nueva.
_TABLE_LEVEL_METHODS = {
    "unique", "index", "primary", "foreign", "dropColumn", "dropUnique",
    "dropIndex", "dropForeign", "renameColumn", "spatialIndex", "fullText",
}


@dataclass
class ParsedMigration:
    table: str
    columns: list[Column]
    unique_indexes: dict[str, list[str]] = field(default_factory=dict)
    # columna -> tabla referenciada explícitamente (->constrained('x') /
    # ->references(...)->on('x') / $table->foreign('col')->...->on('x')).
    # Se combina con el mapeo importado (.md) — ver fk_resolver.resolve_fk,
    # que ya le da prioridad sobre la detección automática por convención.
    fk_hints: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class MigrationParseError(ValueError):
    pass


def _split_top_level_args(inside: str) -> list[str]:
    """Separa `a, [1, 2], 'x,y'` en sus 3 partes de top-level, respetando
    comillas y paréntesis/corchetes anidados."""
    parts: list[str] = []
    depth = 0
    quote: str | None = None
    current = []
    i = 0
    while i < len(inside):
        ch = inside[i]
        if quote:
            current.append(ch)
            if ch == "\\" and i + 1 < len(inside):
                current.append(inside[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            current.append(ch)
        elif ch in "([":
            depth += 1
            current.append(ch)
        elif ch in ")]":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
        i += 1
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def _literal(token: str):
    token = token.strip()
    if not token:
        return None
    if token in ("true", "TRUE"):
        return True
    if token in ("false", "FALSE"):
        return False
    if token in ("null", "NULL"):
        return None
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
        return token[1:-1].replace("\\" + token[0], token[0])
    if token.startswith("[") and token.endswith("]"):
        return [_literal(p) for p in _split_top_level_args(token[1:-1])]
    try:
        if re.fullmatch(r"-?\d+", token):
            return int(token)
        return float(token)
    except ValueError:
        return token  # expresión no literal (ej. Modelo::class) -- se deja tal cual


def _split_chain(statement_tail: str) -> list[tuple[str, list]]:
    """`->string('id', 36)->index()` -> [("string", ["id", 36]), ("index", [])]."""
    calls: list[tuple[str, list]] = []
    pos = 0
    text = statement_tail
    while pos < len(text):
        match = _CALL_RE.match(text, pos)
        if not match:
            break
        name = match.group(1)
        depth = 1
        i = match.end()
        start_args = i
        while i < len(text) and depth > 0:
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
            elif text[i] in ("'", '"'):
                quote = text[i]
                i += 1
                while i < len(text) and text[i] != quote:
                    if text[i] == "\\":
                        i += 1
                    i += 1
            i += 1
        args_raw = text[start_args : i - 1]
        args = [_literal(a) for a in _split_top_level_args(args_raw)]
        calls.append((name, args))
        pos = i
    return calls


def _guess_fk_table(column_name: str, calls: list[tuple[str, list]]) -> str | None:
    for name, args in calls:
        if name == "constrained" and args:
            return str(args[0])
        if name == "on" and args:
            return str(args[0])
    return None


def _apply_statement(
    table: str, calls: list[tuple[str, list]], columns: dict[str, Column], parsed: ParsedMigration
) -> None:
    if not calls:
        return
    head_name, head_args = calls[0]

    if head_name in _TABLE_LEVEL_METHODS:
        if head_name == "foreign" and head_args:
            column_name = str(head_args[0])
            target = _guess_fk_table(column_name, calls[1:])
            if target:
                parsed.fk_hints[column_name] = target
        elif head_name == "unique" and head_args:
            cols = head_args[0] if isinstance(head_args[0], list) else [head_args[0]]
            cols = [str(c) for c in cols]
            index_name = f"{table}_{'_'.join(cols)}_unique"
            parsed.unique_indexes[index_name] = cols
        return

    if head_name in _MULTI_COLUMN_METHODS:
        pairs = (
            [("created_at", True), ("updated_at", True)]
            if head_name.startswith("timestamps")
            else [("deleted_at", True)]
        )
        for col_name, nullable in pairs:
            columns[col_name] = Column(
                name=col_name, sql_type="timestamp", nullable=nullable, key="", default=None, extra=""
            )
        return

    sql_type = _COLUMN_TYPE_SQL.get(head_name)
    if head_name == "foreignIdFor":
        sql_type = "bigint(20) unsigned"
        col_name = str(head_args[1]) if len(head_args) > 1 else None
        if not col_name:
            model = str(head_args[0]) if head_args else "model"
            base = model.rsplit("\\", 1)[-1].replace("::class", "")
            col_name = re.sub(r"(?<!^)(?=[A-Z])", "_", base).lower() + "_id"
    elif head_name in ("string", "char"):
        length = head_args[1] if len(head_args) > 1 else 255
        sql_type = f"{head_name}({length})" if head_name == "char" else f"varchar({length})"
        col_name = str(head_args[0]) if head_args else None
    elif head_name == "decimal" or head_name == "unsignedDecimal":
        precision = head_args[1] if len(head_args) > 1 else 8
        scale = head_args[2] if len(head_args) > 2 else 2
        sql_type = f"decimal({precision},{scale})" + (" unsigned" if head_name.startswith("unsigned") else "")
        col_name = str(head_args[0]) if head_args else None
    elif head_name == "enum":
        values = head_args[1] if len(head_args) > 1 and isinstance(head_args[1], list) else []
        rendered = ",".join(f"'{v}'" for v in values)
        sql_type = f"enum({rendered})"
        col_name = str(head_args[0]) if head_args else None
    elif sql_type is not None:
        col_name = str(head_args[0]) if head_args else None
    else:
        parsed.warnings.append(f"Método de columna no reconocido, ignorado: {head_name}()")
        return

    if not col_name:
        parsed.warnings.append(f"No se pudo determinar el nombre de columna en {head_name}()")
        return

    nullable = False
    key = ""
    default = None
    extra = ""

    for name, args in calls[1:]:
        if name == "nullable":
            nullable = not (args and args[0] is False)
        elif name == "default":
            default = str(args[0]) if args else None
        elif name == "unique":
            key = "UNI"
            parsed.unique_indexes[f"{table}_{col_name}_unique"] = [col_name]
        elif name == "index" and key != "UNI":
            key = "MUL"
        elif name in ("primary", "autoIncrement"):
            key = "PRI"
            if name == "autoIncrement":
                extra = "auto_increment"
        elif name == "unsigned" and sql_type and "unsigned" not in sql_type:
            sql_type = f"{sql_type} unsigned"
        elif name in ("constrained", "references", "on"):
            target = _guess_fk_table(col_name, [(name, args)])
            if target:
                parsed.fk_hints[col_name] = target

    columns[col_name] = Column(
        name=col_name, sql_type=sql_type, nullable=nullable, key=key, default=default, extra=extra
    )


def parse_migration(text: str, *, table_hint: str | None = None) -> ParsedMigration:
    """Parsea el texto de UNA migración `Schema::create(...)`.

    `table_hint` sirve cuando el archivo usa `Schema::create($this->table, ...)`
    y por algún motivo no se pudo leer `protected $table` (ej. se pegó solo
    el bloque del `up()`, sin el resto de la clase) — en ese caso hay que
    pasarlo a mano (ver GUI: campo "Tabla" cuando no se detecta sola).
    """
    table_match = _TABLE_LITERAL_RE.search(text)
    if table_match:
        table = table_match.group(1)
    else:
        prop_match = _TABLE_PROPERTY_RE.search(text)
        table = prop_match.group(1) if prop_match else table_hint

    if not table:
        raise MigrationParseError(
            "No se pudo determinar el nombre de la tabla — ni Schema::create('tabla', ...) "
            "ni protected $table están en el texto. Especificá la tabla a mano."
        )

    if "Schema::create" not in text:
        raise MigrationParseError(
            "No se encontró Schema::create(...) en el texto — ¿es una migración de creación "
            "de tabla? (add_x_to_y / alter no están soportados, solo create_x_table)."
        )

    parsed = ParsedMigration(table=table, columns=[])
    columns: dict[str, Column] = {}

    for stmt_match in _STATEMENT_RE.finditer(text):
        calls = _split_chain(stmt_match.group(1))
        _apply_statement(table, calls, columns, parsed)

    parsed.columns = list(columns.values())
    if not parsed.columns:
        parsed.warnings.append("No se reconoció ninguna columna — revisá que el texto tenga el bloque $table->... completo.")
    return parsed


def parse_migration_file(path) -> ParsedMigration:
    from pathlib import Path

    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    return parse_migration(text)


_CREATE_FILENAME_RE = re.compile(r"create_([a-z0-9_]+)_table", re.IGNORECASE)


def scan_migration_tables(backend_root) -> list[str]:
    """Lista los nombres de tabla de `database/migrations/**/*.php` -- sustituto
    de `SHOW TABLES` cuando no hay conexión a BD (ver fk_resolver.find_fk_candidates,
    que necesita la lista completa de tablas del proyecto para reconocer candidatas
    de FK). Primero intenta por convención de nombre de archivo (Model.md#Convención
    de nombres de migraciones); si el archivo no calza esa convención, lee su
    contenido buscando `Schema::create('tabla', ...)`.
    """
    from pathlib import Path

    root = Path(backend_root) / "database" / "migrations"
    if not root.is_dir():
        return []

    tables: set[str] = set()
    for php_file in root.rglob("*.php"):
        match = _CREATE_FILENAME_RE.search(php_file.stem)
        if match:
            tables.add(match.group(1))
            continue
        try:
            text = php_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        literal_match = _TABLE_LITERAL_RE.search(text)
        if literal_match:
            tables.add(literal_match.group(1))
    return sorted(tables)
