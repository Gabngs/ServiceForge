"""Detecta Models y Resources que YA EXISTEN en el proyecto backend para una
tabla dada -- aunque no sigan la convención de nombres/ubicación de esta
herramienta (ver conversación sobre matching Modelo↔Resource;
ApiResponse.md#Resource triple).

El generador (generator.py) asume, por convención, que un Model/Resource
para la tabla `X` vive en la ruta que arma paths.py -- y `existing_target_files`
en generator.py ya avisa cuando ESA ruta puntual está ocupada. Este módulo
cubre el caso que ese chequeo no puede ver: un proyecto legado donde el
Resource de `catalogo_premiaciones` se llama `PremiacionResource` y vive en
otra carpeta, no `PremiacionesResource` en la ruta que este programa usaría.

No es un parser de PHP real -- son regex sobre el texto del archivo, con los
falsos negativos que eso implica (`toArray()` con `array_merge`, campos
condicionales con `when()`/`whenLoaded()`, etc. no se detectan del todo). Por
diseño, ante duda, este módulo prefiere score bajo (candidato descartado o
mostrado con confianza baja) antes que un match inventado: es un soporte
para no duplicar/pisar trabajo existente, no la base de la generación -- la
decisión final siempre queda del lado del desarrollador (ver GUI).
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import match_learner, naming
from .db import Column

_CLASS_RE = re.compile(r"\bclass\s+(\w+)")
_NAMESPACE_RE = re.compile(r"\bnamespace\s+([\w\\]+)\s*;")
_TABLE_PROPERTY_RE = re.compile(r"protected\s+\$table\s*=\s*['\"](\w+)['\"]")
_MIXIN_RE = re.compile(r"@mixin\s+([\w\\]+)")
_TOARRAY_SIG_RE = re.compile(r"function\s+toArray\s*\([^)]*\)\s*(?::\s*[\w\\|]+\s*)?\{")
_ARRAY_KEY_RE = re.compile(r"['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*=>")

# Orden importa: "RelationResource"/"TinyResource" hay que probarlos antes
# que "Resource" (todo nombre que termina en esos dos también termina en
# "Resource", el sufijo genérico tiene que perder).
_ROLE_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("RelationResource", "relation_resource"),
    ("TinyResource", "tiny_resource"),
    ("Resource", "resource"),
)


@dataclass
class ModelInfo:
    class_name: str
    namespace: str
    path: Path
    table_hint: str | None  # de `protected $table = '...'`, si está declarado


@dataclass
class ResourceInfo:
    class_name: str
    namespace: str
    path: Path
    role: str  # "resource" | "relation_resource" | "tiny_resource" | "unknown"
    base_name: str  # class_name sin el sufijo de rol
    fields: set[str]
    mixin_target: str | None  # nombre corto de la clase referenciada por @mixin, si está


@dataclass
class MatchCandidate:
    resource: ResourceInfo
    features: dict[str, float]
    score: float


@dataclass
class ModelResourceMatch:
    table: str
    model: ModelInfo | None
    candidates: list[MatchCandidate] = field(default_factory=list)

    @property
    def best(self) -> MatchCandidate | None:
        return self.candidates[0] if self.candidates else None


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _extract_fields(text: str) -> set[str]:
    """Keys del array que devuelve toArray(). Balancea llaves desde el `{`
    de la firma para no engancharse con el siguiente método de la clase --
    no sigue array_merge()/spread ni claves armadas dinámicamente, esas
    simplemente no entran al set (baja el field_jaccard, no rompe nada)."""
    sig = _TOARRAY_SIG_RE.search(text)
    if not sig:
        return set()

    start = sig.end() - 1  # el '{' de la firma
    depth = 0
    end = len(text)
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    return set(_ARRAY_KEY_RE.findall(text[start:end]))


def _resource_role(class_name: str) -> tuple[str, str]:
    for suffix, role in _ROLE_SUFFIXES:
        if class_name.endswith(suffix):
            return role, class_name[: -len(suffix)]
    return "unknown", class_name


def scan_models(backend_root: Path) -> list[ModelInfo]:
    models_dir = backend_root / "app" / "Models"
    if not models_dir.is_dir():
        return []
    results: list[ModelInfo] = []
    for path in models_dir.rglob("*.php"):
        text = _read_text(path)
        class_match = _CLASS_RE.search(text)
        if not class_match:
            continue
        namespace_match = _NAMESPACE_RE.search(text)
        table_match = _TABLE_PROPERTY_RE.search(text)
        results.append(
            ModelInfo(
                class_name=class_match.group(1),
                namespace=namespace_match.group(1) if namespace_match else "",
                path=path,
                table_hint=table_match.group(1) if table_match else None,
            )
        )
    return results


def scan_resources(backend_root: Path) -> list[ResourceInfo]:
    resources_dir = backend_root / "app" / "Http" / "Resources"
    if not resources_dir.is_dir():
        return []
    results: list[ResourceInfo] = []
    for path in resources_dir.rglob("*.php"):
        text = _read_text(path)
        class_match = _CLASS_RE.search(text)
        if not class_match:
            continue
        namespace_match = _NAMESPACE_RE.search(text)
        mixin_match = _MIXIN_RE.search(text)
        role, base_name = _resource_role(class_match.group(1))
        results.append(
            ResourceInfo(
                class_name=class_match.group(1),
                namespace=namespace_match.group(1) if namespace_match else "",
                path=path,
                role=role,
                base_name=base_name,
                fields=_extract_fields(text),
                mixin_target=mixin_match.group(1).rsplit("\\", 1)[-1] if mixin_match else None,
            )
        )
    return results


def find_model_for_table(models: list[ModelInfo], table: str, model_class: str) -> ModelInfo | None:
    """El Model que esta herramienta genera usa el nombre LITERAL de la
    tabla como clase (ver Model.md) -- pero un proyecto legado puede tener
    un Model con el StudlyCase convencional de Laravel, o declarar `$table`
    a mano con el nombre real de la tabla. Se prueban las tres variantes."""
    by_class = {m.class_name: m for m in models}
    if model_class in by_class:
        return by_class[model_class]
    if table in by_class:
        return by_class[table]
    for m in models:
        if m.table_hint == table:
            return m
    return None


def _normalize(name: str) -> str:
    return name.replace("_", "").lower()


def _name_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def build_features(
    resource: ResourceInfo,
    *,
    table: str,
    modulo: str,
    model: ModelInfo | None,
    business_columns: set[str],
) -> dict[str, float]:
    name_similarity = max(
        _name_similarity(resource.base_name, table),
        _name_similarity(resource.base_name, modulo),
    )

    field_jaccard = 0.0
    if resource.fields:
        union = resource.fields | business_columns
        if union:
            field_jaccard = len(resource.fields & business_columns) / len(union)

    mixin_match = 0.0
    if model is not None and resource.mixin_target:
        mixin_match = 1.0 if resource.mixin_target == model.class_name else 0.0

    same_namespace = 0.0
    if model is not None and model.namespace and resource.namespace:
        # Compara el último segmento del namespace (ej. "dbcatalogo" del
        # Model vs. "catalogo" del Resource, ver paths.py) en vez del
        # namespace completo -- son árboles de carpeta distintos
        # (Models/ vs. Http/Resources/), nunca van a matchear entero.
        model_tail = model.namespace.rsplit("\\", 1)[-1].lower()
        resource_tail = resource.namespace.rsplit("\\", 1)[-1].lower()
        if model_tail and (model_tail in resource_tail or resource_tail in model_tail):
            same_namespace = 1.0

    return {
        "name_similarity": name_similarity,
        "field_jaccard": field_jaccard,
        "mixin_match": mixin_match,
        "same_namespace": same_namespace,
    }


def find_candidates(
    table: str,
    business_columns: list[Column],
    backend_root: Path,
    *,
    learner: "match_learner.MatchLearner | None" = None,
    min_score: float = 0.35,
    relation_names: set[str] | None = None,
) -> ModelResourceMatch:
    """Candidatos de Resource ya existentes para `table`, puntuados por
    `learner` (ver match_learner.py) y ordenados de mayor a menor score --
    `min_score` filtra ruido, un Resource sin ninguna señal en común no
    aparece ni como candidato débil. Sin `learner` explícito usa uno nuevo
    cargado de disco (pesos aprendidos si ya hay confirmaciones previas,
    prior heurístico si no) -- siempre da un score razonable, incluso antes
    de que el desarrollador confirme un solo match.

    `relation_names` -- nombres de relación (alias de FK ya resueltas +
    'created_by'/'updated_by'/'deleted_by') que se suman a las columnas de
    negocio para el cálculo de `field_jaccard`: un {Modulo}RelationResource
    típicamente expone esas claves (`'articulo' => ...`, `whenLoaded(...)`),
    no solo columnas planas -- sin esto, el solapamiento de campos se
    subestima justo para el rol que más lo necesita. Se arma reusando la
    misma resolución de FK ya cacheada/importada/exportada por fk_resolver
    (ver GUI), no una detección nueva."""
    learner = learner or match_learner.MatchLearner.load()
    _, modulo = naming.split_prefijo_modulo(table)
    model_class = naming.model_class_name(table)

    models = scan_models(backend_root)
    resources = scan_resources(backend_root)
    model = find_model_for_table(models, table, model_class)

    columns = {c.name for c in business_columns} | (relation_names or set())
    candidates: list[MatchCandidate] = []
    for resource in resources:
        features = build_features(resource, table=table, modulo=modulo, model=model, business_columns=columns)
        score = learner.score(features)
        if score >= min_score:
            candidates.append(MatchCandidate(resource=resource, features=features, score=score))

    candidates.sort(key=lambda c: c.score, reverse=True)
    return ModelResourceMatch(table=table, model=model, candidates=candidates)
