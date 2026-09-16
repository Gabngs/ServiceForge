"""Acceso de solo lectura a la BD objetivo: SHOW TABLES / DESCRIBE / SHOW INDEX.

Esta es la conexión "BD objetivo" del documento de arquitectura — la que se
analiza para generar código — no la BD propia del programa (acá el prototipo
no persiste nada salvo la caché de resoluciones de FK, ver fk_resolver.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pymysql
import pymysql.cursors

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+$")


@dataclass(frozen=True)
class ConnectionConfig:
    host: str
    port: int
    user: str
    password: str
    database: str

    @property
    def connection_id(self) -> str:
        """Identificador estable para la caché de resoluciones de FK (sin password)."""
        return f"{self.host}:{self.port}/{self.database}"


@dataclass(frozen=True)
class Column:
    name: str
    sql_type: str
    nullable: bool
    key: str  # 'PRI' | 'UNI' | 'MUL' | ''
    default: str | None
    extra: str


def _validate_identifier(name: str) -> str:
    """Los nombres de tabla/columna no se pueden parametrizar en DESCRIBE/SHOW.

    Solo se interpolan directo en SQL nombres que ya vinieron de SHOW TABLES /
    DESCRIBE de la misma conexión — nunca texto libre tipeado a mano sin pasar
    por acá.
    """
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(f"Nombre de tabla/columna inválido: {name!r}")
    return name


def connect(config: ConnectionConfig, *, connect_timeout: int = 5) -> pymysql.connections.Connection:
    return pymysql.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        database=config.database,
        connect_timeout=connect_timeout,
        cursorclass=pymysql.cursors.DictCursor,
    )


def list_tables(conn: pymysql.connections.Connection) -> list[str]:
    with conn.cursor() as cursor:
        cursor.execute("SHOW TABLES")
        rows = cursor.fetchall()
    # SHOW TABLES devuelve una sola columna cuyo nombre varía según la BD;
    # con DictCursor tomamos el primer (único) valor de cada fila.
    return [next(iter(row.values())) for row in rows]


def describe_table(conn: pymysql.connections.Connection, table: str) -> list[Column]:
    table = _validate_identifier(table)
    with conn.cursor() as cursor:
        cursor.execute(f"DESCRIBE `{table}`")
        rows = cursor.fetchall()

    return [
        Column(
            name=row["Field"],
            sql_type=row["Type"],
            nullable=(row["Null"] == "YES"),
            key=row["Key"] or "",
            default=row["Default"],
            extra=row["Extra"] or "",
        )
        for row in rows
    ]


def unique_indexes(conn: pymysql.connections.Connection, table: str) -> dict[str, list[str]]:
    """key_name -> columnas, para índices únicos que no sean la PRIMARY."""
    table = _validate_identifier(table)
    with conn.cursor() as cursor:
        cursor.execute(f"SHOW INDEX FROM `{table}` WHERE Non_unique = 0 AND Key_name != 'PRIMARY'")
        rows = cursor.fetchall()

    indexes: dict[str, list[str]] = {}
    for row in sorted(rows, key=lambda r: (r["Key_name"], r["Seq_in_index"])):
        indexes.setdefault(row["Key_name"], []).append(row["Column_name"])
    return indexes


def has_pkid(columns: list[Column]) -> bool:
    return any(c.name == "pkid" for c in columns)
