"""Dónde va cada archivo generado y cómo se llama: la ESTRUCTURA del proyecto.

El patrón de servicios (Model, Filter, Requests, Resource, Service, Controller, ruta) es
por orden y conveniencia: no depende de una estructura de carpetas concreta. Cada
proyecto guarda esos archivos en carpetas y con nombres propios (`Http/Request` o
`Http/Requests`, `routes/` o `routes/modules/`, `{tabla}Service` o `{Camel}Service`...).

Un `StructureLayout` dice, para cada rol, en qué carpeta y con qué nombre de clase se
genera. `STANDARD_LAYOUT` es el estándar de la herramienta; el layout del proyecto se
detecta con `structure_profile.detect_layout` y el desarrollador decide cuál usar (ver
gui.ProjectStructureDialog).

Las carpetas y los nombres son plantillas con estos tokens (de la tabla `siaw_permiso_usuario`):

    {table}    siaw_permiso_usuario      {prefijo}  siaw      {Prefijo}  Siaw
    {modulo}   permiso_usuario           {Modulo}   PermisoUsuario
    {Table}    Siaw_permiso_usuario      (la tabla con la primera letra en mayúscula)

Lo que no es un token es literal: el sub-nivel `dbsiaw` de un proyecto que agrupa por
conexión, en vez de por prefijo de tabla, queda como texto fijo en la plantilla.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import naming

ROLES: tuple[str, ...] = (
    "model",
    "service",
    "filters",
    "store_request",
    "update_request",
    "trait",
    "resource",
    "relation_resource",
    "tiny_resource",
    "controller",
    "routes_module",
)

ROLE_LABELS: dict[str, str] = {
    "model": "Model",
    "service": "Service",
    "filters": "Filters",
    "store_request": "Store Request",
    "update_request": "Update Request",
    "trait": "Trait de validación",
    "resource": "Resource",
    "relation_resource": "Relation Resource",
    "tiny_resource": "Tiny Resource",
    "controller": "Controller",
    "routes_module": "Ruta del módulo",
}

ORIGIN_STANDARD = "estandar"
ORIGIN_PROJECT = "proyecto"
ORIGIN_MANUAL = "manual"
ORIGINS = (ORIGIN_STANDARD, ORIGIN_PROJECT, ORIGIN_MANUAL)

_TOKEN_RE = re.compile(r"\{(\w+)\}")


def tokens_for(table: str) -> dict[str, str]:
    prefijo, modulo = naming.split_prefijo_modulo(table)
    return {
        "table": table,
        "Table": table[:1].upper() + table[1:],
        "prefijo": prefijo,
        "Prefijo": naming.studly(prefijo),
        "modulo": modulo,
        "Modulo": naming.studly(modulo),
    }


def expand(template: str, table: str) -> str:
    """Reemplaza los tokens de `template` con los de `table`; un token desconocido queda tal cual."""
    tokens = tokens_for(table)
    return _TOKEN_RE.sub(lambda m: tokens.get(m.group(1), m.group(0)), template)


def namespace_from_directory(directory: str) -> str:
    """`app/Http/Resources/Siaw` -> `App\\Http\\Resources\\Siaw` (PSR-4 con `app` como `App`)."""
    parts = [p for p in directory.replace("\\", "/").strip("/").split("/") if p]
    if parts and parts[0].lower() == "app":
        parts[0] = "App"
    return "\\".join(parts)


@dataclass(frozen=True)
class RolePlacement:
    directory: str  # plantilla de carpeta relativa a la raíz del backend, con '/'
    name: str  # plantilla del nombre de clase (o del archivo, en `routes_module`)
    namespace: str | None = None  # plantilla del namespace; None = se deriva de la carpeta

    def describe(self, *, extension: bool = True) -> str:
        """Cómo se ve la ruta con tokens, para mostrar en la GUI."""
        return f"{self.directory}/{self.name}" + (".php" if extension else "")


_STANDARD_PLACEMENTS: dict[str, RolePlacement] = {
    "model": RolePlacement("app/Models/db{prefijo}", "{table}"),
    "service": RolePlacement("app/Services", "{Modulo}Service"),
    "filters": RolePlacement("app/Filters", "{table}Filters"),
    "store_request": RolePlacement("app/Http/Requests/{Prefijo}/{Modulo}", "Store{Modulo}Request"),
    "update_request": RolePlacement("app/Http/Requests/{Prefijo}/{Modulo}", "Update{Modulo}Request"),
    "trait": RolePlacement("app/Http/Requests/{Prefijo}/Traits/{Modulo}", "Validates{Modulo}"),
    "resource": RolePlacement("app/Http/Resources/{Prefijo}", "{Modulo}Resource"),
    "relation_resource": RolePlacement("app/Http/Resources/{Prefijo}", "{Modulo}RelationResource"),
    "tiny_resource": RolePlacement("app/Http/Resources/{Prefijo}", "{Modulo}TinyResource"),
    "controller": RolePlacement("app/Http/Controllers/Api/{Prefijo}", "{table}Controller"),
    "routes_module": RolePlacement("routes/modules", "{modulo}"),
}


@dataclass
class StructureLayout:
    placements: dict[str, RolePlacement] = field(default_factory=lambda: dict(_STANDARD_PLACEMENTS))
    # rol -> "estandar" | "proyecto" | "manual": de dónde salió cada ubicación (lo muestra y guarda la GUI)
    origins: dict[str, str] = field(default_factory=dict)

    def placement(self, role: str) -> RolePlacement:
        return self.placements.get(role) or _STANDARD_PLACEMENTS[role]

    def origin(self, role: str) -> str:
        return self.origins.get(role, ORIGIN_STANDARD)

    def directory(self, role: str, table: str) -> str:
        return expand(self.placement(role).directory, table).strip("/")

    def class_name(self, role: str, table: str) -> str:
        return expand(self.placement(role).name, table)

    def namespace(self, role: str, table: str) -> str:
        placement = self.placement(role)
        if placement.namespace is not None:
            return expand(placement.namespace, table)
        return namespace_from_directory(self.directory(role, table))

    def fqcn(self, role: str, table: str) -> str:
        namespace = self.namespace(role, table)
        name = self.class_name(role, table)
        return f"{namespace}\\{name}" if namespace else name

    def path(self, role: str, table: str) -> Path:
        directory = self.directory(role, table)
        return Path(directory) / f"{self.class_name(role, table)}.php" if directory else Path(f"{self.class_name(role, table)}.php")

    def with_placement(self, role: str, placement: RolePlacement, origin: str) -> "StructureLayout":
        placements = dict(self.placements)
        placements[role] = placement
        origins = dict(self.origins)
        origins[role] = origin
        return StructureLayout(placements=placements, origins=origins)

    def is_standard(self) -> bool:
        return all(self.placement(role) == _STANDARD_PLACEMENTS[role] for role in ROLES)

    # ------------------------------------------------------ persistencia
    def to_dict(self) -> dict[str, dict[str, str | None]]:
        return {
            role: {
                "directory": self.placement(role).directory,
                "name": self.placement(role).name,
                "namespace": self.placement(role).namespace,
                "origin": self.origin(role),
            }
            for role in ROLES
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StructureLayout":
        placements = dict(_STANDARD_PLACEMENTS)
        origins: dict[str, str] = {}
        for role in ROLES:
            item = data.get(role)
            if not isinstance(item, dict) or "directory" not in item or not item.get("name"):
                continue
            placements[role] = RolePlacement(
                directory=str(item["directory"]),
                name=str(item["name"]),
                namespace=item.get("namespace") or None,
            )
            origin = item.get("origin")
            if origin in ORIGINS:
                origins[role] = origin
        return cls(placements=placements, origins=origins)


STANDARD_LAYOUT = StructureLayout(origins={role: ORIGIN_STANDARD for role in ROLES})
