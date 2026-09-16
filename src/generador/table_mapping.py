"""Mapeo de relaciones FK portable — un archivo `.md` con `{columna} -> {tabla}`
que se puede versionar/compartir entre desarrolladores, a diferencia de la
caché de resoluciones (`fk_resolver.FkResolutionCache`), que vive local en
`%APPDATA%` y no sale de la máquina de quien la generó.

No reemplaza la caché — la complementa: al analizar una tabla, un mapeo
importado se consulta primero (evita repreguntar FKs ya conocidas por todo
el equipo), y lo que se resuelve a mano se puede exportar a este mismo
formato para compartirlo.

Formato — tabla markdown simple, una fila por columna FK:

    | Columna | Tabla |
    |---|---|
    | tienda_id | catalogo_tienda |
    | rol_id | siaw_roles |

Cualquier línea que no sea una fila de tabla válida (encabezado, separador
`---`, texto libre, comentarios) se ignora — así el archivo puede tener
título y notas alrededor de la tabla sin romper el parseo.
"""

from __future__ import annotations

from pathlib import Path

_SEPARATOR_CHARS = set("-: |")


def parse_mapping_md(text: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue

        cells = [c.strip().strip("`") for c in stripped.strip("|").split("|")]
        if len(cells) < 2:
            continue

        column, table = cells[0], cells[1]
        if not column or not table:
            continue
        if set(column + table) <= _SEPARATOR_CHARS:
            continue  # fila separadora tipo | --- | --- |
        if column.lower() in ("columna", "column", "campo"):
            continue  # fila de encabezado

        mapping[column] = table

    return mapping


def load_mapping_md(path: Path) -> dict[str, str]:
    return parse_mapping_md(path.read_text(encoding="utf-8"))


def render_mapping_md(mapping: dict[str, str], *, title: str = "Mapeo de relaciones") -> str:
    lines = [f"# {title}", "", "| Columna | Tabla |", "|---|---|"]
    for column, table in sorted(mapping.items()):
        lines.append(f"| {column} | {table} |")
    lines.append("")
    return "\n".join(lines)


def save_mapping_md(mapping: dict[str, str], path: Path, *, title: str = "Mapeo de relaciones") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_mapping_md(mapping, title=title), encoding="utf-8")
    return path
