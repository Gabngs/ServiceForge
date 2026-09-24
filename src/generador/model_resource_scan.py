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

from . import match_learner, naming, structure_scan
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
    # Archivos YA existentes de los demás roles (Filter, Requests, Service, Controller, rutas...) que el
    # modelo de estructura reconoce como de este Model, mejor puntuados primero. Es informativo: la
    # generación todavía solo usa los Resources confirmados de `candidates` (ver gui.py).
    others: dict[str, list["structure_scan.RoleCandidate"]] = field(default_factory=dict)

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


def _resource_info(f: "structure_scan.FileX", backend_root: Path) -> ResourceInfo:
    """FileX del escáner de estructura -> ResourceInfo, el tipo que ya consumen la GUI y la generación."""
    role = "tiny_resource" if f.class_name.endswith("TinyResource") else f.role
    return ResourceInfo(
        class_name=f.class_name,
        namespace=f.namespace,
        path=backend_root / f.path,
        role=role,
        base_name=_resource_role(f.class_name)[1],
        fields=set(f.keys),
        mixin_target=f.mixin_target,
    )


def find_candidates(
    table: str,
    business_columns: list[Column],
    backend_root: Path,
    *,
    learner: "match_learner.MatchLearner | None" = None,
    min_score: float = 0.35,
    relation_names: set[str] | None = None,
) -> ModelResourceMatch:
    """Candidatos ya existentes en el proyecto para `table`, puntuados por `learner` (ver
    match_learner.py) y ordenados de mayor a menor score -- `min_score` filtra ruido, un archivo sin
    ninguna señal en común no aparece ni como candidato débil.

    Escanea el proyecto con `structure_scan` (el mismo código con el que se armó el dataset de
    entrenamiento, así las features de entrenamiento y las de uso no divergen). Devuelve los
    Resources (completo / de relación / tiny) en `candidates`, con la forma de siempre, y los
    archivos de los demás roles en `others`.

    Sin `learner` explícito usa `StructureLearner` cargado de disco: el modelo de estructura de
    fábrica, más lo que ya haya aprendido de las confirmaciones del desarrollador en esta máquina.
    Si no hay ningún modelo entrenado, cae al prior heurístico -- siempre da un score razonable.

    `relation_names` -- nombres de relación (alias de FK ya resueltas + 'created_by'/'updated_by'/
    'deleted_by') que se suman a las columnas de negocio para el cálculo de `field_jaccard`: un
    {Modulo}RelationResource típicamente expone esas claves (`'articulo' => ...`, `whenLoaded(...)`),
    no solo columnas planas -- sin esto, el solapamiento de campos se subestima justo para el rol
    que más lo necesita."""
    learner = learner or match_learner.StructureLearner.load()
    model_class = naming.model_class_name(table)
    columns = {c.name for c in business_columns} | (relation_names or set())

    index = structure_scan.scan_repo(backend_root)
    existing = structure_scan.find_model(index, table, model_class)
    if existing is not None:
        existing.columns |= columns
        model = existing
    else:
        model = structure_scan.synth_model(index, table, model_class, columns)

    ranked = structure_scan.rank_candidates(index, model, learner, min_score=min_score)

    candidates = [
        MatchCandidate(resource=_resource_info(c.file, backend_root), features=c.features, score=c.score)
        for role in ("resource", "relation_resource")
        for c in ranked[role]
    ]
    candidates.sort(key=lambda c: c.score, reverse=True)

    others = {role: found[:3] for role, found in ranked.items() if role not in ("resource", "relation_resource") and found}

    model_info = None
    if existing is not None:
        model_info = ModelInfo(
            class_name=existing.class_name,
            namespace=existing.namespace,
            path=backend_root / existing.path,
            table_hint=existing.table if existing.table != existing.class_name else None,
        )
    return ModelResourceMatch(table=table, model=model_info, candidates=candidates, others=others)
