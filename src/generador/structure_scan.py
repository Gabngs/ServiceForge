"""Escáner de ESTRUCTURA de un backend Laravel + features de un par (modelo, archivo).

Reconoce el ROL de cada archivo (Filter, Resource, Resource mínimo, Requests, trait de
validación, Service, Controller, rutas) respecto de un modelo, aunque cada proyecto use
otras carpetas, nombres, prefijos o singular/plural. Es la misma lógica con la que se armó y
se evaluó el dataset de `datasets/structure/` (ver su README): un solo código para entrenar
y para usar en la app, así las features de entrenamiento y las de runtime no pueden divergir.

  - `scan_repo(root)`        clasifica cada .php por rol (segmentos de ruta + nombre de clase, no carpetas fijas)
  - `assign_owners(index)`   ground truth de repos reales: de qué modelo es cada archivo (criterios auditables)
  - `pair_features(...)`     las FEATURES de un par -- entrada del modelo (ver `match_learner.StructureLearner`)
  - `rank_candidates(...)`   candidatos existentes de cada rol para un modelo, puntuados por un aprendiz

No es un parser de PHP: son regex sobre el texto. Ante duda prefiere un score bajo antes que un
match inventado, y nunca decide sola: el desarrollador confirma (ver gui.py).
"""

from __future__ import annotations

import difflib
import functools
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from . import migration_import, naming

# Copias EXACTAS de helpers de model_resource_scan.py (no se importa el módulo: él importa a este,
# y un import circular rompería la carga). Un test verifica que siguen dando lo mismo.
_MIXIN_RE = re.compile(r"@mixin\s+([\w\\]+)")
_TOARRAY_SIG_RE = re.compile(r"function\s+toArray\s*\([^)]*\)\s*(?::\s*[\w\\|]+\s*)?\{")
_TOARRAY_KEY_RE = re.compile(r"['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*=>")


def _normalize(name: str) -> str:
    return name.replace("_", "").lower()


def _extract_fields(text: str) -> set[str]:
    """Keys del array que devuelve toArray() (balancea llaves; no sigue array_merge ni claves dinámicas)."""
    sig = _TOARRAY_SIG_RE.search(text)
    if not sig:
        return set()
    start = sig.end() - 1
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
    return set(_TOARRAY_KEY_RE.findall(text[start:end]))

# Roles del dataset. `other_request` (Bulk, Autorizar, Cerrar...) se escanea y se asigna a su
# dueño en el manifiesto, pero NO entra al dataset: no es un rol que el generador ubique.
ROLES: tuple[str, ...] = (
    "filter",
    "resource",
    "relation_resource",
    "base_request",
    "store_request",
    "update_request",
    "request_trait",
    "service",
    "controller",
    "route",
)

# Orden fijo de features del modelo NUEVO. Las 4 primeras son las del modelo de
# fábrica actual (generador/match_learner.py::FEATURE_NAMES) y se calculan igual.
LEGACY_FEATURES: tuple[str, ...] = ("name_similarity", "field_jaccard", "mixin_match", "same_namespace")
EXTRA_FEATURES: tuple[str, ...] = (
    "name_sim_norm",  # similitud difusa de nombres NORMALIZADOS (sin prefijo de tabla/sufijo de rol/acción, sin '_')
    "name_contains",  # un nombre normalizado contiene al otro (cubre singular/plural y variantes)
    "path_segment_match",  # alguna carpeta del candidato coincide con el nombre del modelo ({tabla}/)
    "imports_model",  # el candidato importa (use) la clase del modelo
    "declared_by_model",  # el modelo declara al candidato (`$default_filters`)
    "route_names_controller",  # (rutas) el archivo referencia un controller que se llama como el modelo
    "dominant_root",  # el candidato está en la carpeta raíz más frecuente del proyecto para ese rol
    "subfolder_share",  # fracción de los archivos de ese rol que comparten el sub-nivel del candidato
    "has_columns",  # el modelo tiene columnas conocidas (migraciones/$fillable)
    "has_keys",  # el candidato expone keys (toArray/rules/allowedFilters)
    "import_breadth",  # cuántos modelos distintos importa el candidato (0..1) -- alto = archivo compartido
)
ALL_ROLES: tuple[str, ...] = ROLES + ("other_request",)
ROLE_FEATURES: tuple[str, ...] = tuple(f"role_{r}" for r in ROLES)
FEATURES: tuple[str, ...] = LEGACY_FEATURES + EXTRA_FEATURES + ROLE_FEATURES

# Features que dependen casi 1:1 del criterio con el que se etiquetan los repos
# reales (igualdad de nombre normalizado / carpeta / $default_filters / import).
# Se las quita en la variante "soft" de la evaluación para medir cuánto del
# resultado depende de haber visto la regla de etiquetado (ver README del dataset).
DIRECT_SIGNAL_FEATURES: tuple[str, ...] = (
    "path_segment_match",
    "imports_model",
    "declared_by_model",
    "route_names_controller",
)

_SKIP_DIRS = {"vendor", "node_modules", ".git", "storage", "public", "tests", "database", "bootstrap", ".idea", ".vscode", "cache"}
_SKIP_FILES = {"console", "channels", "web"}

_CLASS_RE = re.compile(r"^[ \t]*(?:(abstract|final)\s+)?(class|trait|interface)\s+(\w+)(?:\s+extends\s+([\w\\]+))?", re.M)
_NAMESPACE_RE = re.compile(r"^\s*namespace\s+([\w\\]+)\s*;", re.M)
_USE_RE = re.compile(r"^use\s+([\w\\]+)(?:\s+as\s+(\w+))?\s*;", re.M)
_USE_GROUP_RE = re.compile(r"^use\s+([\w\\]+)\\\{([^}]*)\}\s*;", re.M)
_TABLE_RE = re.compile(r"\$table\s*=\s*['\"]([\w.]+)['\"]")
_CONNECTION_RE = re.compile(r"\$connection\s*=\s*['\"](\w+)['\"]")
_PK_RE = re.compile(r"\$primaryKey\s*=\s*['\"](\w+)['\"]")
_INCR_RE = re.compile(r"\$incrementing\s*=\s*(true|false)")
_KEYTYPE_RE = re.compile(r"\$keyType\s*=\s*['\"](\w+)['\"]")
_DELETED_AT_RE = re.compile(r"const\s+DELETED_AT\s*=\s*['\"](\w+)['\"]")
_DEFAULT_FILTERS_RE = re.compile(r"\$default_filters\s*=\s*([\w\\]+)::class")
_FILLABLE_RE = re.compile(r"\$fillable\s*=\s*\[(.*?)\]", re.S)
_CASTS_RE = re.compile(r"\$casts\s*=\s*\[(.*?)\]\s*;", re.S)
_QUOTED_RE = re.compile(r"['\"]([A-Za-z_][\w]*)['\"]")
_KEY_ARROW_RE = re.compile(r"['\"]([A-Za-z_][\w.*]*)['\"]\s*=>")
_RELATION_RE = re.compile(
    r"function\s+(\w+)\s*\([^)]*\)[^{]*\{\s*return\s+\$this->(belongsTo|hasMany|hasOne|belongsToMany|morphTo|morphMany)\(\s*([\w\\]+)::class"
    r"(?:\s*,\s*['\"](\w+)['\"])?(?:\s*,\s*['\"](\w+)['\"])?",
    re.S,
)
_CONTROLLER_REF_RE = re.compile(r"\b([A-Za-z_]\w*Controller)\b")
_ALLOWED_PROP_RE = re.compile(r"\$(?:allowedFilters|allowedSearch|columnSearch|allowedSorts)\s*=\s*\[(.*?)\]", re.S)
_PUBLIC_METHOD_RE = re.compile(r"public\s+function\s+([a-z_]\w*)\s*\(\s*\$\w+")

_RELATION_STYLE_SUFFIX = r"(?:Relation|Relacion|Tiny|Left|Data|Show|Lite|Mini)"
_MIN_RESOURCE_RE = re.compile(rf"^(?P<base>.+?){_RELATION_STYLE_SUFFIX}Resource$")
_GENERIC_FOLDERS = {
    "app", "http", "request", "requests", "resources", "resource", "traits", "trait", "services", "service", "controllers",
    "controller", "api", "filters", "filter", "models", "model", "routes", "modules", "module", "domain", "v1", "v2",
}


# ─────────────────────────────── nombres ────────────────────────────────


def norm_raw(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def stem(norm: str) -> str:
    if norm.endswith("ies") and len(norm) > 5:
        return norm[:-3] + "y"
    if norm.endswith("es") and len(norm) > 4:
        return norm[:-2]
    if norm.endswith("s") and len(norm) > 3:
        return norm[:-1]
    return norm


def derive_prefixes(tables: list[str], class_names: list[str]) -> list[str]:
    """Prefijos de tabla del repo: primer token (antes de `_`) que se repite en
    >= 3 nombres (`sip_`, `catalogo_`, `agh_`). Sin mirar ninguna etiqueta."""
    counter: Counter[str] = Counter()
    for name in set(tables) | set(class_names):
        if "_" in name:
            counter[name.split("_", 1)[0].lower()] += 1
    prefixes = [p for p, n in counter.items() if n >= 3 and len(p) >= 2]
    return sorted(prefixes, key=len, reverse=True)


def strip_prefix(norm: str, prefixes: list[str]) -> str:
    for p in prefixes:
        pn = norm_raw(p)
        if norm.startswith(pn) and len(norm) - len(pn) >= 3:
            return norm[len(pn):]
    return norm


def _strip_role_decoration(role: str, class_name: str) -> str:
    """Nombre de clase sin sufijo de rol ni prefijo/sufijo de acción."""
    name = class_name
    if role in ("resource", "relation_resource"):
        m = _MIN_RESOURCE_RE.match(name)
        name = m.group("base") if m else re.sub(r"Resource$", "", name)
    elif role == "filter":
        name = re.sub(r"Filters?$", "", name)
    elif role == "service":
        name = re.sub(r"Service$", "", name)
    elif role == "controller":
        name = re.sub(r"Controller$", "", name)
    elif role in ("base_request", "store_request", "update_request", "request_trait", "other_request"):
        name = re.sub(r"Request$", "", name)
        name = re.sub(r"^(?:Base|Store|Update|Bulk|Validates?)", "", name)
        name = re.sub(r"(?:Store|Update)$", "", name)
    return name


def effective_base(role: str, class_name: str, stem_name: str, folders: list[str]) -> str:
    """Nombre 'de negocio' del archivo. Si el nombre de clase no lo trae
    (`StoreRequest.php` dentro de `AghAlmacenes/`), se toma la carpeta más cercana."""
    if role == "route":
        return stem_name
    base = _strip_role_decoration(role, class_name)
    if norm_raw(base) == "":
        for folder in reversed(folders):
            if folder.lower() not in _GENERIC_FOLDERS:
                return folder
    return base


# ─────────────────────────────── estructuras ────────────────────────────


@dataclass
class ModelX:
    class_name: str
    path: str  # relativa al repo, con '/'
    namespace: str
    table: str
    connection: str | None
    pk: dict
    soft_delete: str
    has_factory: bool
    auditoria: list[str]
    relaciones: list[dict]
    default_filters: str | None
    columns: set[str]
    norms: set[str] = field(default_factory=set)  # normalizados y SIN prefijo de tabla
    stems: set[str] = field(default_factory=set)
    norms_full: set[str] = field(default_factory=set)  # normalizados CON prefijo (nombre literal)


@dataclass
class FileX:
    path: str
    role: str
    class_name: str
    namespace: str
    folders: list[str]  # carpetas del path (sin el archivo)
    root_path: str  # carpeta raíz del rol (hasta el segmento de rol), ej. app/Http/Request
    subfolder: str  # sub-nivel bajo la raíz del rol (primer segmento) o ''
    base_name: str
    norm: str  # normalizado sin prefijo
    norm_full: str  # normalizado con prefijo (nombre literal)
    imports: set[str]  # nombres cortos importados
    controllers_used: set[str]
    keys: set[str]
    mixin_target: str | None
    is_abstract: bool


@dataclass
class RepoIndex:
    root: Path
    name: str
    models: list[ModelX]
    files: dict[str, list[FileX]]
    prefixes: list[str]
    model_by_class: dict[str, ModelX]
    dominant_root: dict[str, str]
    subfolder_counts: dict[tuple[str, str], int]
    role_totals: dict[str, int]
    table_columns: dict[str, set[str]]
    meta: dict = field(default_factory=dict)


# ─────────────────────────────── lectura de PHP ─────────────────────────


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _imports(text: str) -> set[str]:
    out: set[str] = set()
    for fq, alias in _USE_RE.findall(text):
        out.add(alias or fq.rsplit("\\", 1)[-1])
    for _, group in _USE_GROUP_RE.findall(text):
        for item in group.split(","):
            item = item.strip()
            if item:
                out.add(item.split(" as ")[-1].strip().rsplit("\\", 1)[-1])
    return out


def _balanced_block(text: str, start_pattern: re.Pattern) -> str:
    m = start_pattern.search(text)
    if not m:
        return ""
    start = m.end() - 1
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i]
    return text[start:]


_RULES_SIG_RE = re.compile(r"function\s+rules\s*\([^)]*\)\s*(?::\s*[\w\\|]+\s*)?\{")


def _file_keys(role: str, text: str) -> set[str]:
    if role in ("resource", "relation_resource"):
        return _extract_fields(text)
    if role in ("base_request", "store_request", "update_request", "request_trait"):
        block = _balanced_block(text, _RULES_SIG_RE) or text
        return {k.split(".")[0] for k in _KEY_ARROW_RE.findall(block) if k.split(".")[0] not in {"required", "sometimes", "nullable"}}
    if role == "filter":
        keys: set[str] = set()
        for chunk in _ALLOWED_PROP_RE.findall(text):
            keys.update(_QUOTED_RE.findall(chunk))
        keys.update(_PUBLIC_METHOD_RE.findall(text))
        return keys
    return set()


def _classify(rel_parts: list[str], kind: str, class_name: str, is_abstract: bool) -> str | None:
    """Rol de un archivo por SEGMENTOS de ruta + nombre de clase (no por carpeta fija)."""
    dirs = [p.lower() for p in rel_parts[:-1]]
    stem_name = rel_parts[-1][:-4]
    if rel_parts[-1].endswith(".blade.php"):
        return None
    if dirs and dirs[0] == "resources":  # views/lang de la raíz del repo
        return None
    if "routes" in dirs:
        return "route"
    if "models" in dirs or "model" in dirs:
        return "model" if kind == "class" and not is_abstract else None
    if "filters" in dirs or "filter" in dirs:
        return "filter" if kind == "class" and not is_abstract else None
    if "resources" in dirs:
        if kind != "class" or is_abstract:
            return None
        return "relation_resource" if _MIN_RESOURCE_RE.match(class_name) else "resource"
    if "request" in dirs or "requests" in dirs:
        if kind == "trait" or re.match(r"^Validates?", class_name):
            return "request_trait"
        if re.match(r"^Base", class_name) or (is_abstract and class_name.startswith("Base")):
            return "base_request"
        if re.match(r"^Store", class_name) or re.search(r"Store(Request)?$", class_name):
            return "store_request"
        if re.match(r"^Update", class_name) or re.search(r"Update(Request)?$", class_name):
            return "update_request"
        return "other_request" if kind == "class" and not is_abstract else None
    if "traits" in dirs and kind == "trait" and re.match(r"^Validates?", class_name):
        return "request_trait"
    if "services" in dirs or "service" in dirs:
        if kind != "class" or is_abstract or class_name in ("CrudService", "Service"):
            return None
        return "service"
    if "controllers" in dirs:
        if kind != "class" or is_abstract or class_name == "Controller":
            return None
        return "controller"
    return None


def _role_root(rel_parts: list[str], role: str) -> tuple[str, str]:
    """(raíz del rol, sub-nivel). La raíz llega hasta el segmento de rol
    (`app/Http/Request`); el sub-nivel es el primer segmento siguiente."""
    markers = {
        "filter": ("filters", "filter"),
        "resource": ("resources",),
        "relation_resource": ("resources",),
        "other_request": ("request", "requests"),
        "base_request": ("request", "requests"),
        "store_request": ("request", "requests"),
        "update_request": ("request", "requests"),
        "request_trait": ("request", "requests", "traits"),
        "service": ("services", "service"),
        "controller": ("controllers",),
        "route": ("routes",),
        "model": ("models", "model"),
    }[role]
    dirs = rel_parts[:-1]
    for i, seg in enumerate(dirs):
        if seg.lower() in markers:
            sub = dirs[i + 1] if i + 1 < len(dirs) else ""
            return "/".join(dirs[: i + 1]), sub
    return "/".join(dirs), ""


def _model_from_text(rel: str, text: str, columns_by_table: dict[str, set[str]]) -> ModelX | None:
    cm = _CLASS_RE.search(text)
    if not cm:
        return None
    class_name = cm.group(3)
    ns = _NAMESPACE_RE.search(text)
    table_m = _TABLE_RE.search(text)
    table = table_m.group(1) if table_m else class_name
    conn_m = _CONNECTION_RE.search(text)
    incr = _INCR_RE.search(text)
    fillable_m = _FILLABLE_RE.search(text)
    fillable = set(_QUOTED_RE.findall(fillable_m.group(1))) if fillable_m else set()
    casts_m = _CASTS_RE.search(text)
    casts = set(_KEY_ARROW_RE.findall(casts_m.group(1))) if casts_m else set()
    soft = "no"
    if "SoftDeletes" in text:
        d = _DELETED_AT_RE.search(text)
        soft = d.group(1) if d else "deleted_at"
    pk_m = _PK_RE.search(text)
    kt = _KEYTYPE_RE.search(text)
    pk = {
        "name": pk_m.group(1) if pk_m else "id",
        "incrementing": incr.group(1) == "true" if incr else "default",
        "keyType": kt.group(1) if kt else "default",
        "pkid_en_fillable": "pkid" in fillable,
    }
    auditoria = [c for c in ("created_by_id", "updated_by_id", "deleted_by_id") if c in text]
    relaciones = []
    for alias, kind, target, fk, pk_col in _RELATION_RE.findall(text):
        detail = f"{kind} {target.rsplit(chr(92), 1)[-1]}"
        if fk:
            detail += f" ({fk}{', ' + pk_col if pk_col else ''})"
        relaciones.append({alias: detail})
    df = _DEFAULT_FILTERS_RE.search(text)
    columns = set(columns_by_table.get(table, set())) | fillable | casts
    return ModelX(
        class_name=class_name,
        path=rel,
        namespace=ns.group(1) if ns else "",
        table=table,
        connection=conn_m.group(1) if conn_m else None,
        pk=pk,
        soft_delete=soft,
        has_factory="HasFactory" in text,
        auditoria=auditoria,
        relaciones=relaciones,
        default_filters=df.group(1).rsplit("\\", 1)[-1] if df else None,
        columns=columns,
    )


def _load_table_columns(root: Path) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    mig = root / "database" / "migrations"
    if not mig.is_dir():
        return result
    for php in mig.rglob("*.php"):
        try:
            parsed = migration_import.parse_migration_file(php)
        except (migration_import.MigrationParseError, OSError, Exception):  # noqa: BLE001
            continue
        result.setdefault(parsed.table, set()).update(c.name for c in parsed.columns)
    return result


def _iter_php(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d.lower() not in _SKIP_DIRS]
        rel_dir = Path(dirpath).relative_to(root)
        if rel_dir.parts and rel_dir.parts[0].lower() in _SKIP_DIRS:
            continue
        for fn in filenames:
            if fn.endswith(".php"):
                yield Path(dirpath) / fn


def scan_repo(root: Path, name: str | None = None) -> RepoIndex:
    root = Path(root)
    columns_by_table = _load_table_columns(root)
    models: list[ModelX] = []
    parsed: list[tuple[str, str, str, list[str], str]] = []

    for php in _iter_php(root):
        rel_parts = list(php.relative_to(root).parts)
        rel = "/".join(rel_parts)
        text = _read(php)
        cm = _CLASS_RE.search(text)
        kind = cm.group(2) if cm else "class"
        class_name = cm.group(3) if cm else php.stem
        is_abstract = bool(cm and cm.group(1) == "abstract")
        # una ruta no declara clase: se clasifica solo por carpeta
        role = _classify(rel_parts, kind if cm else "class", class_name, is_abstract)
        if role is None:
            continue
        # routes/console.php, channels.php y web.php son del framework: se ignoran salvo que
        # registren controllers (un módulo real puede llamarse `channels`)
        if role == "route" and php.stem.lower() in _SKIP_FILES and not _CONTROLLER_REF_RE.search(text):
            continue
        if role == "model":
            m = _model_from_text(rel, text, columns_by_table)
            if m:
                models.append(m)
            continue
        parsed.append((rel, role, class_name, rel_parts, text, is_abstract))

    tables = [m.table for m in models]
    classes = [m.class_name for m in models]
    prefixes = derive_prefixes(tables, classes)
    for m in models:
        raw = {strip_prefix(norm_raw(m.class_name), prefixes), strip_prefix(norm_raw(m.table), prefixes)}
        m.norms = {r for r in raw if r}
        m.stems = {stem(r) for r in m.norms}
        m.norms_full = {norm_raw(m.class_name), norm_raw(m.table)}

    files: dict[str, list[FileX]] = {r: [] for r in ALL_ROLES}
    for rel, role, class_name, rel_parts, text, abs_flag in parsed:
        stem_name = rel_parts[-1][:-4]
        folders = rel_parts[:-1]
        root_path, sub = _role_root(rel_parts, role)
        base = effective_base(role, class_name, stem_name, folders)
        mixin = _MIXIN_RE.search(text)
        ns = _NAMESPACE_RE.search(text)
        files[role].append(
            FileX(
                path=rel,
                role=role,
                class_name=class_name,
                namespace=ns.group(1) if ns else "",
                folders=folders,
                root_path=root_path,
                subfolder=sub,
                base_name=base,
                norm=strip_prefix(norm_raw(base), prefixes),
                norm_full=norm_raw(base),
                imports=_imports(text),
                controllers_used=set(_CONTROLLER_REF_RE.findall(text)),
                keys=_file_keys(role, text),
                mixin_target=mixin.group(1).rsplit("\\", 1)[-1] if mixin else None,
                is_abstract=abs_flag,
            )
        )

    dominant_root: dict[str, str] = {}
    subfolder_counts: dict[tuple[str, str], int] = {}
    role_totals: dict[str, int] = {}
    for role, items in files.items():
        role_totals[role] = len(items)
        if not items:
            continue
        counter = Counter(f.root_path for f in items)
        dominant_root[role] = counter.most_common(1)[0][0]
        for f in items:
            subfolder_counts[(role, f.subfolder)] = subfolder_counts.get((role, f.subfolder), 0) + 1

    return RepoIndex(
        root=root,
        name=name or root.name,
        models=models,
        files=files,
        prefixes=prefixes,
        model_by_class={m.class_name: m for m in models},
        dominant_root=dominant_root,
        subfolder_counts=subfolder_counts,
        role_totals=role_totals,
        table_columns=columns_by_table,
    )


# ─────────────────────────────── ground truth ───────────────────────────

# Jerarquía de criterios (de más a menos fuerte). Cada asignación queda
# etiquetada con el criterio que la produjo (`via`) para poder auditarla.
TIER_ORDER = (
    "declared", "name_exact_full", "name_prefix_full", "name_exact", "name_stem", "name_prefix", "folder", "route_controller", "import_single",
)


def _owner_candidates_for_file(index: RepoIndex, f: FileX) -> tuple[str, list[ModelX]]:
    """(criterio, modelos dueños) del archivo `f`; ([]) si ningún criterio lo asigna."""
    models = index.models
    if f.role == "filter":
        declared = [m for m in models if m.default_filters == f.class_name]
        if declared:
            return "declared", declared

    def longest_prefix(value: str, getter) -> list[ModelX]:
        best_len, best = 0, []
        for m in models:
            for n in getter(m):
                if len(n) >= 5 and value.startswith(n):
                    if len(n) > best_len:
                        best_len, best = len(n), [m]
                    elif len(n) == best_len and m not in best:
                        best.append(m)
        return best

    # 1) nombre LITERAL (con prefijo de tabla): `sip_tiendaResource` es de `sip_tienda`, no de `catalogo_tienda`
    if f.norm_full:
        exact_full = [m for m in models if f.norm_full in m.norms_full]
        if exact_full:
            return "name_exact_full", exact_full
        prefix_full = longest_prefix(f.norm_full, lambda m: m.norms_full)
        if prefix_full:
            return "name_prefix_full", prefix_full

    # 2) nombre SIN prefijo de tabla (`SolicitudVacacionesService` -> `sip_solicitudvacaciones`)
    f_raw = f.norm
    f_stem = stem(f_raw)
    if f_raw:
        exact = [m for m in models if f_raw in m.norms]
        if exact:
            return "name_exact", exact
        stemmed = [m for m in models if f_stem in m.stems]
        if stemmed:
            return "name_stem", stemmed
        prefix = longest_prefix(f_raw, lambda m: m.norms)
        if prefix:
            return "name_prefix", prefix

    seg_norms = {strip_prefix(norm_raw(seg), index.prefixes) for seg in f.folders if seg.lower() not in _GENERIC_FOLDERS}
    seg_stems = {stem(s) for s in seg_norms}
    if seg_norms:
        by_folder = [m for m in models if (m.norms & seg_norms) or (m.stems & seg_stems)]
        if by_folder:
            return "folder", by_folder
    return "", []


def assign_owners(index: RepoIndex) -> dict[str, dict[str, list[tuple[str, str]]]]:
    """model class -> role -> [(path, criterio)]. También calcula los `*_usado_en`
    (archivos que importan el modelo pero no son suyos) en `usado_en`."""
    owners: dict[str, dict[str, list[tuple[str, str]]]] = {m.class_name: defaultdict(list) for m in index.models}
    file_owner: dict[str, set[str]] = {}
    non_route_files = [f for r in ALL_ROLES if r != "route" for f in index.files[r]]

    for f in non_route_files:
        tier, ms = _owner_candidates_for_file(index, f)
        if not ms and f.role in ("service", "controller", "base_request", "store_request", "update_request", "request_trait", "other_request"):
            imported = [m for m in index.models if m.class_name in f.imports]
            # el import es señal SECUNDARIA: solo cuenta si además hay algo de parecido de nombre
            if len(imported) == 1 and max((_sim(f.norm, n) for n in imported[0].norms), default=0.0) >= 0.5:
                tier, ms = "import_single", imported
        for m in ms:
            owners[m.class_name][f.role].append((f.path, tier))
            file_owner.setdefault(f.path, set()).add(m.class_name)

    controller_owner: dict[str, set[str]] = {}
    for f in index.files["controller"]:
        controller_owner[f.class_name] = file_owner.get(f.path, set())

    for f in index.files["route"]:
        tier, ms = _owner_candidates_for_file(index, f)
        claimed: dict[str, str] = {m.class_name: tier for m in ms}
        # además, dueño de todo controller que el archivo importa (una ruta en línea en api.php cuenta)
        for c in f.controllers_used:
            for owner_class in controller_owner.get(c, ()):
                claimed.setdefault(owner_class, "route_controller")
        for class_name, via in claimed.items():
            owners[class_name]["route"].append((f.path, via))
            file_owner.setdefault(f.path, set()).add(class_name)
    return owners


def usado_en(index: RepoIndex, owners: dict) -> dict[str, dict[str, list[str]]]:
    """model class -> role -> [paths] de archivos que importan el modelo sin ser suyos."""
    result: dict[str, dict[str, list[str]]] = {m.class_name: defaultdict(list) for m in index.models}
    owned = {m: {role: {p for p, _ in items} for role, items in roles.items()} for m, roles in owners.items()}
    for role in ALL_ROLES:
        for f in index.files[role]:
            for m in index.models:
                if m.class_name in f.imports and f.path not in owned[m.class_name].get(role, set()):
                    result[m.class_name][role].append(f.path)
    return result


# ─────────────────────────────── features ───────────────────────────────


@functools.lru_cache(maxsize=400_000)
def _sim(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _modulo_of(table: str) -> str:
    try:
        return naming.split_prefijo_modulo(table)[1]
    except Exception:  # noqa: BLE001
        return table


def pair_features(index: RepoIndex, m: ModelX, f: FileX) -> dict[str, float]:
    table = m.table or m.class_name
    modulo = _modulo_of(table)
    legacy_name = max(
        difflib.SequenceMatcher(None, _normalize(f.base_name), _normalize(table)).ratio() if f.base_name else 0.0,
        difflib.SequenceMatcher(None, _normalize(f.base_name), _normalize(modulo)).ratio() if f.base_name else 0.0,
    )
    field_jaccard = 0.0
    if f.keys and m.columns:
        union = f.keys | m.columns
        field_jaccard = len(f.keys & m.columns) / len(union) if union else 0.0

    mixin_match = 1.0 if f.mixin_target and f.mixin_target == m.class_name else 0.0
    same_ns = 0.0
    if m.namespace and f.namespace:
        mt = m.namespace.rsplit("\\", 1)[-1].lower()
        ft = f.namespace.rsplit("\\", 1)[-1].lower()
        if mt and (mt in ft or ft in mt):
            same_ns = 1.0

    name_sim_norm = max((_sim(f.norm, n) for n in m.norms), default=0.0)
    name_contains = 0.0
    for n in m.norms:
        if f.norm and n and len(min(f.norm, n, key=len)) >= 4 and (n in f.norm or f.norm in n):
            name_contains = 1.0
            break

    seg_norms = {strip_prefix(norm_raw(s), index.prefixes) for s in f.folders if s.lower() not in _GENERIC_FOLDERS}
    path_segment_match = 1.0 if (m.norms & seg_norms) or (m.stems & {stem(s) for s in seg_norms}) else 0.0

    imports_model = 1.0 if m.class_name in f.imports else 0.0
    declared = 1.0 if (f.role == "filter" and m.default_filters == f.class_name) else 0.0
    route_names = 0.0
    if f.role == "route":
        for c in f.controllers_used:
            cn = strip_prefix(norm_raw(re.sub(r"Controller$", "", c)), index.prefixes)
            if cn and (cn in m.norms or stem(cn) in m.stems):
                route_names = 1.0
                break

    dom = 1.0 if index.dominant_root.get(f.role) == f.root_path else 0.0
    total = index.role_totals.get(f.role, 0)
    share = index.subfolder_counts.get((f.role, f.subfolder), 0) / total if total else 0.0
    n_models_imported = sum(1 for x in index.models if x.class_name in f.imports)
    breadth = min(n_models_imported, 10) / 10.0

    feats: dict[str, float] = {
        "name_similarity": legacy_name,
        "field_jaccard": field_jaccard,
        "mixin_match": mixin_match,
        "same_namespace": same_ns,
        "name_sim_norm": name_sim_norm,
        "name_contains": name_contains,
        "path_segment_match": path_segment_match,
        "imports_model": imports_model,
        "declared_by_model": declared,
        "route_names_controller": route_names,
        "dominant_root": dom,
        "subfolder_share": share,
        "has_columns": 1.0 if m.columns else 0.0,
        "has_keys": 1.0 if f.keys else 0.0,
        "import_breadth": breadth,
    }
    for r in ROLES:
        feats[f"role_{r}"] = 1.0 if f.role == r else 0.0
    return feats


def feature_vector(feats: dict[str, float], names: tuple[str, ...] = FEATURES) -> list[float]:
    return [feats[n] for n in names]


# ─────────────────────────────── uso en la app: candidatos existentes ────


@dataclass
class RoleCandidate:
    """Un archivo YA EXISTENTE del proyecto que podría ser el `role` del modelo, con su puntaje."""

    file: FileX
    features: dict[str, float]
    score: float


def find_model(index: RepoIndex, table: str, model_class: str) -> ModelX | None:
    """El Model de la tabla en el proyecto: por nombre de clase, por nombre de tabla o por `$table`."""
    for key in (model_class, table):
        if key in index.model_by_class:
            return index.model_by_class[key]
    for m in index.models:
        if m.table == table:
            return m
    return None


def synth_model(index: RepoIndex, table: str, model_class: str, columns: set[str]) -> ModelX:
    """Model 'virtual' para una tabla que todavía no tiene Model en el proyecto: las features
    necesitan un modelo con nombre y columnas, y ese es el caso más común (generar por primera vez)."""
    model = ModelX(
        class_name=model_class, path="", namespace="", table=table, connection=None,
        pk={"name": "id", "incrementing": "default", "keyType": "default", "pkid_en_fillable": False},
        soft_delete="no", has_factory=False, auditoria=[], relaciones=[], default_filters=None, columns=set(columns),
    )
    raw = {strip_prefix(norm_raw(model_class), index.prefixes), strip_prefix(norm_raw(table), index.prefixes)}
    model.norms = {r for r in raw if r}
    model.stems = {stem(r) for r in model.norms}
    model.norms_full = {norm_raw(model_class), norm_raw(table)}
    return model


def rank_candidates(
    index: RepoIndex,
    model: ModelX,
    learner,
    *,
    roles: tuple[str, ...] = ROLES,
    min_score: float = 0.35,
    limit: int | None = None,
) -> dict[str, list[RoleCandidate]]:
    """Para cada rol, los archivos existentes que `learner` (cualquier objeto con `.score(features)`)
    puntúa por encima de `min_score`, de mayor a menor. Un archivo sin ninguna señal en común no
    aparece ni como candidato débil: es un soporte para no duplicar, no una lista de sospechosos."""
    result: dict[str, list[RoleCandidate]] = {}
    for role in roles:
        ranked: list[RoleCandidate] = []
        for f in index.files.get(role, []):
            feats = pair_features(index, model, f)
            score = learner.score(feats)
            if score >= min_score:
                ranked.append(RoleCandidate(file=f, features=feats, score=score))
        ranked.sort(key=lambda c: c.score, reverse=True)
        result[role] = ranked[:limit] if limit else ranked
    return result
