"""Qué archivos usa el código generado para las tablas relacionadas (FK) de un módulo, y cómo se
confirma con el desarrollador.

El generador ya no inventa `{Prefijo}\\{Modulo}RelationResource` a partir del nombre de la tabla:
para cada tabla relacionada propone lo que hay en el proyecto y el desarrollador decide (ver
gui.RelationsDialog). La propuesta sale, en este orden, de:

  1. el mapa del proyecto (`relation_map`): lo que ya se confirmó antes para esa tabla, para
     cualquier módulo -- llega precargado y sin duda;
  2. el modelo de estructura (`structure_scan.rank_candidates` + la red): el archivo existente que
     mejor parece el RelationResource de esa tabla, con su confianza;
  3. la convención del layout: "generar uno nuevo", si el proyecto no tiene nada parecido.

Nunca decide sola: `apply_confirmation` solo guarda y le enseña a la red lo que el desarrollador validó.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import naming, structure_scan
from .generator import RelationTarget, short_class
from .layout import StructureLayout
from .relation_map import RelationMap

# Valores especiales de la elección del RelationResource (además de un FQCN real).
GENERATE = "__generar__"
NONE = "__sin_resource__"

# Confianza a partir de la cual se propone un archivo existente en vez de "generar uno nuevo".
PROPOSE_MIN_SCORE = 0.5

RESOURCE_ROLES = ("relation_resource", "resource")


@dataclass
class ClassOption:
    fqcn: str  # o GENERATE / NONE
    label: str
    path: str = ""  # relativa a la raíz del backend
    score: float | None = None  # confianza de la red; None si no viene de ella
    role: str = ""  # relation_resource | resource | model
    features: dict[str, float] | None = None  # entrada de la red, para enseñarle la elección


@dataclass
class RelationChoice:
    """Una tabla relacionada del módulo, con lo que se propone y las alternativas."""

    table: str
    columns: list[str]  # columnas FK del módulo que apuntan a esta tabla
    model_options: list[ClassOption] = field(default_factory=list)
    model_selected: str = ""
    resource_options: list[ClassOption] = field(default_factory=list)
    resource_selected: str = GENERATE
    remembered: bool = False  # el RelationResource viene del mapa (confirmado antes)
    model_exists: bool = True  # el Model relacionado existe en el proyecto (si no, se usa la convención)
    confidence: float | None = None  # de la propuesta de RelationResource, si la dio la red


@dataclass
class Confirmation:
    """Lo que el desarrollador dejó elegido para una tabla relacionada."""

    table: str
    model_fqcn: str
    resource: str  # FQCN, GENERATE o NONE


def _fqcn(namespace: str, class_name: str) -> str:
    return f"{namespace}\\{class_name}" if namespace else class_name


def _model_options(index: structure_scan.RepoIndex) -> list[ClassOption]:
    return [
        ClassOption(fqcn=_fqcn(m.namespace, m.class_name), label=m.class_name, path=m.path, role="model")
        for m in sorted(index.models, key=lambda m: m.class_name.lower())
        if m.path
    ]


def _file_option(f: structure_scan.FileX, score: float | None = None, features: dict[str, float] | None = None) -> ClassOption:
    return ClassOption(
        fqcn=_fqcn(f.namespace, f.class_name), label=f.class_name, path=f.path, score=score, role=f.role, features=features
    )


def build_choices(
    index: structure_scan.RepoIndex,
    learner,
    rmap: RelationMap | None,
    layout: StructureLayout,
    related: dict[str, list[str]],
    *,
    columns_by_table: dict[str, set[str]] | None = None,
) -> list[RelationChoice]:
    """Una `RelationChoice` por tabla relacionada. `related` = tabla -> columnas FK del módulo que
    apuntan a ella. `columns_by_table` (opcional) mejora las features de la red con las columnas reales."""
    columns_by_table = columns_by_table or {}
    all_models = _model_options(index)
    resource_files = [f for role in RESOURCE_ROLES for f in index.files.get(role, [])]
    choices: list[RelationChoice] = []

    for table in sorted(related):
        choice = RelationChoice(table=table, columns=sorted(related[table]))

        # --- Model relacionado
        model_class = naming.model_class_name(table)
        found = structure_scan.find_model(index, table, model_class)
        remembered_model = rmap.file_for(table, "model") if rmap else None
        if remembered_model is not None:
            choice.model_selected = remembered_model.fqcn
        elif found is not None and found.path:
            choice.model_selected = _fqcn(found.namespace, found.class_name)
        else:
            choice.model_selected = layout.fqcn("model", table)
            choice.model_exists = False
        choice.model_options = list(all_models)
        if not any(o.fqcn == choice.model_selected for o in choice.model_options):
            choice.model_options.insert(
                0, ClassOption(fqcn=choice.model_selected, label=f"{short_class(choice.model_selected)} (convención)", role="model")
            )

        # --- RelationResource de esa tabla
        convention = layout.fqcn("relation_resource", table)
        options: list[ClassOption] = [
            ClassOption(fqcn=GENERATE, label=f"(generar nuevo: {short_class(convention)})"),
            ClassOption(fqcn=NONE, label="(sin Resource: columna plana)"),
        ]

        model_x = found or structure_scan.synth_model(
            index, table, model_class, set(columns_by_table.get(table, set()))
        )
        ranked = structure_scan.rank_candidates(index, model_x, learner, roles=RESOURCE_ROLES, min_score=0.0)
        candidates: list[ClassOption] = []
        for role in RESOURCE_ROLES:
            candidates.extend(_file_option(c.file, c.score, c.features) for c in ranked.get(role, []))
        # la red puede dar scores parecidos a un Resource completo y a uno de relación: el de relación va antes
        candidates.sort(key=lambda o: (o.score or 0.0) + (0.02 if o.role == "relation_resource" else 0.0), reverse=True)
        shown = {o.fqcn for o in candidates[:8]}
        options.extend(candidates[:8])
        # el resto de los Resources del proyecto, para poder buscar cualquiera
        options.extend(
            _file_option(f)
            for f in sorted(resource_files, key=lambda f: f.class_name.lower())
            if _fqcn(f.namespace, f.class_name) not in shown
        )
        choice.resource_options = options

        remembered = rmap.file_for(table, "relation_resource") if rmap else None
        by_fqcn = {o.fqcn: o for o in options}
        if remembered is not None:
            choice.remembered = True
            choice.resource_selected = remembered.fqcn
            if remembered.fqcn not in by_fqcn:
                choice.resource_options.insert(
                    2, ClassOption(fqcn=remembered.fqcn, label=remembered.short, path=remembered.path, role="relation_resource")
                )
        elif convention in by_fqcn:
            # la convención ya existe en el proyecto: es la propuesta obvia
            choice.resource_selected = convention
            choice.confidence = by_fqcn[convention].score
        elif candidates and (candidates[0].score or 0.0) >= PROPOSE_MIN_SCORE:
            choice.resource_selected = candidates[0].fqcn
            choice.confidence = candidates[0].score
        else:
            choice.resource_selected = GENERATE
            choice.confidence = candidates[0].score if candidates else None
        choices.append(choice)
    return choices


def to_targets(confirmations: list[Confirmation], layout: StructureLayout) -> dict[str, RelationTarget]:
    """Lo confirmado, en la forma que consume el generador (`build_manifest(relation_targets=...)`)."""
    targets: dict[str, RelationTarget] = {}
    for item in confirmations:
        target = RelationTarget(table=item.table, model_fqcn=item.model_fqcn or None)
        if item.resource == NONE:
            target.no_resource = True
        elif item.resource == GENERATE:
            target.resource_fqcn = layout.fqcn("relation_resource", item.table)
        else:
            target.resource_fqcn = item.resource
        targets[item.table] = target
    return targets


def apply_confirmation(
    rmap: RelationMap | None,
    learner,
    choices: list[RelationChoice],
    confirmations: list[Confirmation],
    *,
    module_table: str | None = None,
    module_relations: dict[str, str] | None = None,
) -> int:
    """Guarda lo que el desarrollador validó y le enseña a la red. Devuelve cuántos ejemplos aprendió.

    - Mapa: el Model y el RelationResource elegidos (los existentes; un "generar nuevo" se guarda
      recién cuando el archivo se escribe, ver `remember_generated`) y las relaciones del módulo.
    - Red: el archivo elegido es un ejemplo positivo; los otros candidatos que se le mostraron con
      confianza, negativos. No aprende de lo que ya venía confirmado y no se tocó.
    """
    by_table = {c.table: c for c in choices}
    learned = 0
    for item in confirmations:
        choice = by_table.get(item.table)
        if choice is None:
            continue
        options = {o.fqcn: o for o in choice.resource_options}
        model_option = next((o for o in choice.model_options if o.fqcn == item.model_fqcn), None)

        if rmap is not None:
            if item.model_fqcn and (model_option is None or model_option.path or choice.model_exists):
                rmap.remember(item.table, "model", item.model_fqcn, model_option.path if model_option else "")
            if item.resource not in (GENERATE, NONE):
                option = options.get(item.resource)
                rmap.remember(item.table, "relation_resource", item.resource, option.path if option else "")
            elif item.resource == NONE:
                rmap.forget(item.table, "relation_resource")

        unchanged_from_memory = choice.remembered and item.resource == choice.resource_selected
        if learner is not None and not unchanged_from_memory:
            for option in choice.resource_options:
                if option.features is None:
                    continue  # (generar), (sin Resource) y los archivos que la red no puntuó
                learner.update(option.features, 1.0 if option.fqcn == item.resource else 0.0, save=False)
                learned += 1
    if learned and learner is not None:
        learner.save()

    if rmap is not None and module_table and module_relations:
        for column, related_table in module_relations.items():
            rmap.remember_relation(module_table, column, related_table)
    return learned


def remember_generated(rmap: RelationMap | None, table: str, fqcn: str, path: str) -> None:
    """Un RelationResource que se acaba de generar ya existe: recién ahí se recuerda para esa tabla."""
    if rmap is not None:
        rmap.remember(table, "relation_resource", fqcn, path)

