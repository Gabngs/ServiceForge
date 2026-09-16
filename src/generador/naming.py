"""Convenciones de nombres compartidas entre el generador de backend y frontend."""

from __future__ import annotations


def split_prefijo_modulo(table: str) -> tuple[str, str]:
    """`siaw_permiso_usuario` -> ("siaw", "permiso_usuario")."""
    if "_" not in table:
        return table, table
    prefijo, modulo = table.split("_", 1)
    return prefijo, modulo


def studly(snake: str) -> str:
    """`permiso_usuario` -> `PermisoUsuario` (nombre de clase para Service/Controller/Resource)."""
    return "".join(part.capitalize() for part in snake.split("_") if part)


def model_class_name(table: str) -> str:
    """El Model usa el nombre literal de la tabla como clase (ver Model.md) — no StudlyCase."""
    return table
