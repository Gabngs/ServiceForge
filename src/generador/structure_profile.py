"""Detecta la ESTRUCTURA que ya usa un proyecto Laravel: en qué carpeta guarda cada tipo de
archivo del patrón de servicios y cómo lo nombra, como un `layout.StructureLayout`.

Parte del mismo escáner con el que se armó el dataset (`structure_scan`): clasifica cada .php por
rol y le asigna un dueño (el modelo al que pertenece, por nombre). Con esos pares (modelo, archivo)
infiere, por rol, la plantilla de carpeta y de nombre que mejor explica los archivos existentes:

    app/Http/Request/dbsiaw/catalogo_parametrosistema/Storecatalogo_parametrosistemaRequest.php
      ->  carpeta app/Http/Request/dbsiaw/{table}   nombre Store{table}Request

Un segmento se generaliza a un token (`{table}`, `{Prefijo}`...) solo si el proyecto realmente
varía ahí; si todos los archivos están en la misma carpeta, queda literal. Es una inferencia, no
una verdad: el desarrollador la revisa y decide en `gui.ProjectStructureDialog`.
"""

from __future__ import annotations

import itertools
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from . import layout, naming, structure_scan
from .layout import ORIGIN_PROJECT, ORIGIN_STANDARD, RolePlacement, StructureLayout, namespace_from_directory

# Solo los criterios de dueño por NOMBRE: los demás (import, carpeta) son señales débiles y
# arrastrarían a un archivo compartido como si fuera "el" Service de un módulo.
_NAME_TIERS = {"declared", "name_exact_full", "name_prefix_full", "name_exact", "name_stem", "name_prefix"}
_MAX_SAMPLES = 400
_MAX_CANDIDATES = 600
_TOKEN_RE = re.compile(r"\{\w+\}")
_TINY_RE = re.compile(r"Tiny[A-Za-z]*Resource$")

# Rol del generador -> rol del escáner
_SCAN_ROLE = {
    "filters": "filter",
    "store_request": "store_request",
    "update_request": "update_request",
    "trait": "request_trait",
    "resource": "resource",
    "relation_resource": "relation_resource",
    "tiny_resource": "relation_resource",
    "service": "service",
    "controller": "controller",
    "routes_module": "route",
}


@dataclass
class Sample:
    """Un archivo existente y el módulo (tabla) al que pertenece."""

    table: str
    directory: str  # relativa a la raíz, con '/'
    name: str  # nombre de clase (o del archivo, en rutas)
    namespace: str
    path: str


@dataclass
class RoleEvidence:
    role: str
    samples: int = 0  # archivos existentes de ese rol con dueño conocido
    matching: int = 0  # cuántos explica la plantilla elegida
    placement: RolePlacement | None = None  # None = no hay archivos de ese rol en el proyecto
    examples: list[str] = field(default_factory=list)
    approximate: bool = False  # el nombre coincide sin distinguir mayúsculas (ej. `SolicitudVacaciones`)
    inferred_from: str | None = None  # rol del que se dedujo, si el proyecto no tiene archivos de este

    @property
    def confidence(self) -> float:
        return self.matching / self.samples if self.samples else 0.0


@dataclass
class ProjectStructure:
    backend_root: Path
    layout: StructureLayout
    evidence: dict[str, RoleEvidence]
    models: int = 0

    def detected_roles(self) -> list[str]:
        """Roles de los que el proyecto tiene archivos (no cuenta los deducidos)."""
        return [
            role
            for role in layout.ROLES
            if self.evidence[role].placement is not None and self.evidence[role].inferred_from is None
        ]


def _norm_dir(directory: str) -> str:
    return directory.replace("\\", "/").strip("/")


def _split_dir(directory: str) -> list[str]:
    return [p for p in _norm_dir(directory).split("/") if p]


def _segment_reps(segment: str, table: str) -> list[str]:
    """Formas en que un segmento de carpeta puede escribirse: literal o con algún token."""
    tokens = layout.tokens_for(table)
    reps = [segment]
    if segment == tokens["table"]:
        reps.append("{table}")
    if segment == f"db{tokens['prefijo']}":
        reps.append("db{prefijo}")
    if segment == tokens["prefijo"]:
        reps.append("{prefijo}")
    if segment.lower() == tokens["Prefijo"].lower() and segment[:1].isupper():
        reps.append("{Prefijo}")
    if segment == tokens["modulo"] and segment != tokens["table"]:
        reps.append("{modulo}")
    if segment.lower() == tokens["Modulo"].lower() and segment[:1].isupper():
        reps.append("{Modulo}")
    return reps


def _name_reps(name: str, table: str) -> list[str]:
    """Formas en que un nombre de clase puede escribirse: el módulo reemplazado por un token."""
    tokens = layout.tokens_for(table)
    reps: list[str] = []
    for token, value in (
        ("{table}", tokens["table"]),
        ("{Table}", tokens["Table"]),
        ("{Modulo}", tokens["Modulo"]),
        ("{modulo}", tokens["modulo"]),
    ):
        if not value:
            continue
        for match in re.finditer(re.escape(value), name, flags=re.IGNORECASE):
            candidate = name[: match.start()] + token + name[match.end():]
            if candidate not in reps:
                reps.append(candidate)
    return reps


def _matches(template: str, table: str, actual: str) -> tuple[bool, bool]:
    """(coincide, exacto): la plantilla expandida contra lo real, sin distinguir mayúsculas."""
    expanded = layout.expand(template, table)
    return expanded.lower() == actual.lower(), expanded == actual


def _diverse(samples: list[Sample], per_directory: int = 3, max_directories: int = 40) -> list[Sample]:
    """Muestras repartidas entre las carpetas distintas: los candidatos a plantilla salen de todas las
    variantes que hay, no solo de las primeras por orden alfabético."""
    picked: list[Sample] = []
    counts: Counter[str] = Counter()
    for sample in samples:
        key = _norm_dir(sample.directory)
        if counts[key] >= per_directory or (counts[key] == 0 and len(counts) >= max_directories):
            continue
        counts[key] += 1
        picked.append(sample)
    return picked


def _rank_directories(samples: list[Sample]) -> list[tuple[str, int]]:
    """Plantillas de carpeta candidatas con cuántas muestras explica cada una, mejores primero.

    Con empate gana la que usa menos tokens: un literal (`dbsip`) es lo que el proyecto tiene y no
    supone nada; un token solo se justifica cuando explica archivos que el literal no puede."""
    if not samples:
        return []
    by_depth: dict[int, list[Sample]] = {}
    for s in samples:
        by_depth.setdefault(len(_split_dir(s.directory)), []).append(s)

    ranked: list[tuple[tuple[int, int], str]] = []
    for depth, group in by_depth.items():
        if depth == 0:
            ranked.append(((len(group), 0), ""))
            continue
        candidates: set[tuple[str, ...]] = set()
        for sample in _diverse(group):
            options = [_segment_reps(seg, sample.table) for seg in _split_dir(sample.directory)]
            total = 1
            for opt in options:
                total *= len(opt)
            if total > _MAX_CANDIDATES:
                options = [opt[:2] if len(opt) > 2 else opt for opt in options]
            candidates.update(itertools.islice(itertools.product(*options), _MAX_CANDIDATES))
        for combo in candidates:
            template = "/".join(combo)
            matches = sum(1 for s in group if _matches(template, s.table, _norm_dir(s.directory))[0])
            ranked.append(((matches, -sum(1 for seg in combo if "{" in seg)), template))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [(template, score[0]) for score, template in ranked]


def _rank_names(samples: list[Sample]) -> list[tuple[str, int, int]]:
    """Plantillas de nombre de clase candidatas: (plantilla, coincidencias, exactas), mejores primero."""
    candidates: set[str] = set()
    for sample in samples[:60]:
        candidates.update(_name_reps(sample.name, sample.table))
    ranked: list[tuple[tuple[int, int, int], str]] = []
    for template in candidates:
        matches = sum(1 for s in samples if _matches(template, s.table, s.name)[0])
        exact = sum(1 for s in samples if _matches(template, s.table, s.name)[1])
        literal = len(_TOKEN_RE.sub("", template))
        ranked.append(((matches, exact, -literal), template))
    # Una diferencia del 3 % de las muestras no justifica quedarse con la plantilla que fija texto
    # del proyecto (`sip_{modulo}`) en vez de la general (`{table}`): dentro de esa tolerancia
    # se consideran empatadas y gana la que deja menos texto fijo.
    top = max((score[0] for score, _ in ranked), default=0)
    tolerance = int(len(samples) * 0.03)
    ranked = [
        ((max(score[0], top) if top - score[0] <= tolerance else score[0], score[1], score[2]), template, score[0])
        for score, template in ranked
    ]
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [(template, real, score[1]) for score, template, real in ranked]


def _infer_namespace(samples: list[Sample], directory: str) -> str | None:
    """None si el namespace sale de la carpeta (PSR-4); si no, la plantilla del namespace real."""
    if not any(s.namespace for s in samples):
        return None  # rutas y demás archivos sin namespace
    derived_ok = sum(
        1 for s in samples if namespace_from_directory(layout.expand(directory, s.table)) == s.namespace
    )
    if derived_ok >= max(1, len(samples) * 0.8):
        return None
    ranked = _rank_directories(
        [Sample(s.table, s.namespace.replace("\\", "/"), s.name, s.namespace, s.path) for s in samples if s.namespace]
    )
    return ranked[0][0].replace("/", "\\") if ranked else None


_TOP_DIRECTORIES = 6
_TOP_NAMES = 10


def _infer_placement(samples: list[Sample]) -> tuple[RolePlacement, int, bool] | None:
    """Carpeta y nombre se eligen JUNTOS: la pareja que explica más archivos a la vez. Elegirlos por
    separado puede combinar una carpeta de los archivos legados con un nombre de los nuevos y no
    explicar ninguno."""
    if not samples:
        return None
    samples = samples[:_MAX_SAMPLES]
    directories = _rank_directories(samples)[:_TOP_DIRECTORIES]
    names = _rank_names(samples)[:_TOP_NAMES]
    if not directories or not names:
        return None

    pairs: list[tuple[int, int, int, str, str, bool]] = []
    for dir_template, dir_matches in directories:
        for name_template, name_matches, name_exact in names:
            joint = sum(
                1
                for s in samples
                if _matches(dir_template, s.table, _norm_dir(s.directory))[0] and _matches(name_template, s.table, s.name)[0]
            )
            pairs.append((joint, dir_matches, name_exact, dir_template, name_template, name_matches > name_exact))
    if not pairs:
        return None
    top = max(p[0] for p in pairs)
    if top == 0:
        return None
    # Dentro de una tolerancia pequeña (el 3 % de las muestras) las parejas se consideran empatadas y gana
    # la más general: menos tokens en la carpeta y menos texto fijo del proyecto en el nombre.
    tolerance = int(len(samples) * 0.03)
    eligible = [p for p in pairs if p[0] >= top - tolerance]
    joint, _, _, dir_template, name_template, approximate = max(
        eligible,
        key=lambda p: (
            -sum(1 for seg in _split_dir(p[3]) if "{" in seg),
            -len(_TOKEN_RE.sub("", p[4])),
            p[0],
            p[1],
            p[2],
        ),
    )
    matching_samples = [
        s
        for s in samples
        if _matches(dir_template, s.table, _norm_dir(s.directory))[0] and _matches(name_template, s.table, s.name)[0]
    ]
    namespace = _infer_namespace(matching_samples, dir_template)
    return RolePlacement(directory=dir_template, name=name_template, namespace=namespace), joint, approximate


def _samples_by_role(index: structure_scan.RepoIndex) -> dict[str, list[Sample]]:
    owners = structure_scan.assign_owners(index)
    files_by_path = {f.path: f for role_files in index.files.values() for f in role_files}
    model_by_class = index.model_by_class
    result: dict[str, list[Sample]] = {role: [] for role in layout.ROLES}

    for model in index.models:
        parts = model.path.rsplit("/", 1)
        result["model"].append(
            Sample(model.table or model.class_name, parts[0] if len(parts) == 2 else "", model.class_name, model.namespace, model.path)
        )

    for class_name, by_role in owners.items():
        model = model_by_class.get(class_name)
        if model is None or not model.table:
            continue
        for role, scan_role in _SCAN_ROLE.items():
            for path, tier in by_role.get(scan_role, ()):
                if tier not in _NAME_TIERS:
                    continue
                f = files_by_path.get(path)
                if f is None:
                    continue
                if scan_role == "relation_resource":
                    is_tiny = bool(_TINY_RE.search(f.class_name))
                    if (role == "tiny_resource") != is_tiny:
                        continue
                parts = f.path.rsplit("/", 1)
                name = f.class_name if role != "routes_module" else parts[-1][:-4]
                result[role].append(Sample(model.table, parts[0] if len(parts) == 2 else "", name, f.namespace, f.path))
    return result


# Rol sin archivos en el proyecto -> (rol del que se deduce, texto a reemplazar en el nombre, texto nuevo).
# Un proyecto que ya guarda sus Resources en una carpeta casi seguro guarda ahí también los de relación
# y los tiny, con el mismo estilo de nombre; sin esto esos roles caerían en la carpeta del estándar y
# quedarían separados del resto.
_DERIVED_ROLES: dict[str, tuple[str, str, str]] = {
    "relation_resource": ("resource", "Resource", "RelationResource"),
    "tiny_resource": ("resource", "Resource", "TinyResource"),
    "update_request": ("store_request", "Store", "Update"),
    "store_request": ("update_request", "Update", "Store"),
}


def _derive_placement(source: RolePlacement, old: str, new: str) -> RolePlacement | None:
    name = source.name
    if old == "Resource":  # sufijo
        if not name.endswith("Resource"):
            return None
        derived = name[: -len("Resource")] + new
    else:  # prefijo de acción
        if old not in name:
            return None
        derived = name.replace(old, new, 1)
    return RolePlacement(source.directory, derived, source.namespace)


def detect_layout(backend_root: Path, index: structure_scan.RepoIndex | None = None) -> ProjectStructure:
    """La estructura que usa el proyecto en `backend_root`. Los roles sin ningún archivo existente
    (proyecto nuevo, o un rol que todavía no usa) quedan con la ubicación estándar y origen
    "estandar": no hay nada que detectar, y el estándar es el mejor punto de partida."""
    index = index or structure_scan.scan_repo(backend_root)
    samples = _samples_by_role(index)

    detected = StructureLayout(origins={role: ORIGIN_STANDARD for role in layout.ROLES})
    evidence: dict[str, RoleEvidence] = {}
    for role in layout.ROLES:
        role_samples = samples[role]
        item = RoleEvidence(role=role, samples=len(role_samples))
        inferred = _infer_placement(role_samples)
        if inferred is not None:
            placement, matching, approximate = inferred
            item.placement = placement
            item.matching = matching
            item.approximate = approximate
            item.examples = [
                s.path
                for s in role_samples
                if _matches(placement.directory, s.table, _norm_dir(s.directory))[0]
                and _matches(placement.name, s.table, s.name)[0]
            ][:3]
            detected = detected.with_placement(role, placement, ORIGIN_PROJECT)
        evidence[role] = item

    for role, (source_role, old, new) in _DERIVED_ROLES.items():
        item = evidence[role]
        source = evidence[source_role]
        if item.placement is not None or source.placement is None or source.inferred_from is not None:
            continue
        derived = _derive_placement(source.placement, old, new)
        if derived is None:
            continue
        item.placement = derived
        item.inferred_from = source_role
        detected = detected.with_placement(role, derived, ORIGIN_PROJECT)
    return ProjectStructure(backend_root=Path(backend_root), layout=detected, evidence=evidence, models=len(index.models))
