"""Genera esqueletos de proyectos Laravel SINTÉTICOS para el dataset de estructura.

Por qué existen: con 5 repos reales el modelo puede memorizar sus estilos en vez
de aprender a reconocer el ROL de cada archivo. Cada repo sintético toma otra
combinación de convenciones (carpetas, singular/plural, prefijos, sufijos,
layout modular/DDD, idioma...), así que las variaciones entre proyectos --que
son la señal de entrenamiento-- se multiplican sin tocar código de terceros.

Qué son: esqueletos en disco (.php mínimos pero plausibles + migraciones), que
los MISMOS scanners de los repos reales (structure_lib.py) leen sin cambios.
No tienen lógica de negocio.

Ground truth POR CONSTRUCCIÓN: cada repo escribe `manifest.yaml` con los
archivos que efectivamente creó para cada modelo/rol. La etiqueta sale de ahí,
no de una heurística de nombres.

Uso:
    python scripts/generate_synthetic_repos.py --count 30 --seed 20260923
        [--out datasets/structure/synthetic] [--min-models 15 --max-models 60]

Reproducible: misma semilla + mismos parámetros => mismos repos (byte a byte).
Cobertura: cada valor de cada eje aparece en >= 2 repos (si count lo permite).
"""

from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO_ROOT = Path(__file__).resolve().parent.parent
STRUCT = REPO_ROOT / "datasets" / "structure"
NOW_FMT = "%d-%m-%Y %H:%M:%S"
GENERATOR_VERSION = "1.0"

# ───────────────────────────── catálogo de ejes ──────────────────────────
# Los nombres de valor coinciden con los del perfil de variaciones de los
# repos reales (build_variation_profile.py) para poder tomar sus frecuencias.
AXES: dict[str, list[str]] = {
    "layout": ["classic", "modular", "ddd"],
    "requests_dir": ["Request", "Requests"],
    "sublevel": ["conexion", "sistema", "ninguno"],
    "per_table_folder_requests": ["si", "no"],
    "per_table_folder_resources": ["si", "no"],
    "request_traits": ["Traits/{tabla}/Validates{X}", "Traits/Validates{X} plano", "ninguno"],
    "service_name": ["{tabla}", "{CamelSinPrefijo}", "{CamelConPrefijo}", "{ClaseModelo}", "sin_sufijo", "Manager"],
    "entity_name": ["{tabla}", "{CamelSinPrefijo}", "{CamelConPrefijo}", "{ClaseModelo}"],
    "request_name": ["{tabla}", "{CamelSinPrefijo}", "{ClaseModelo}", "accion_en_carpeta", "sin_sufijo_Request", "accion_sufijo"],
    "filter_suffix": ["Filters", "Filter"],
    "base_request": ["clase Base abstracta", "sin base"],
    "min_resource_suffix": ["Relation", "Relacion", "Tiny", "Left", "Data", "Show"],
    "routes_location": ["routes/{tabla}.php", "routes/modules/{tabla}.php", "en línea en api.php", "routes/{area}.php", "routes/api/{modulo}.php"],
    "route_registration": ["RouteServiceProvider", "require en api.php", "bootstrap/app.php"],
    "controllers_dir": ["Api/{sub}", "Api raíz", "Api/V1"],
    "token_middleware": ["[ApiToken::class]", "'ApiToken'", "ValidateSessionKey", "auth:sanctum"],
    "audit_relation": ["created_by", "createdBy", "create_by", "ausente"],
    "user_model": ["User", "catalogo_usuario", "usuarios"],
    "soft_delete": ["deleted_at", "deleted", "no"],
    "pk": ["id uuid string", "pkid int", "pkid + id", "natural"],
    "class_style": ["snake literal", "StudlyCase", "mixto"],
    "language": ["es", "en"],
    "table_prefix": ["por sistema", "catalogo mixto", "ninguno"],
    "file_number": ["plural", "singular"],
}
OUT_OF_SET_WEIGHT = 0.7  # valores que ningún repo real usa (DDD, modular, inglés...) pesan menos que los reales, pero no cero

# ───────────────────────────── vocabulario ───────────────────────────────
# (español plural, inglés plural, columnas típicas ES, columnas típicas EN)
DOMAINS: dict[str, list[tuple[str, str]]] = {
    "inventario": [("productos", "products"), ("almacenes", "warehouses"), ("categorias", "categories"), ("marcas", "brands"),
                   ("proveedores", "suppliers"), ("unidades", "units"), ("lotes", "batches"), ("movimientos", "movements"),
                   ("kardex", "ledger"), ("ubicaciones", "locations"), ("presentaciones", "packagings"), ("etiquetas", "labels")],
    "ventas": [("clientes", "customers"), ("pedidos", "orders"), ("facturas", "invoices"), ("cotizaciones", "quotes"),
               ("vendedores", "salespeople"), ("descuentos", "discounts"), ("cupones", "coupons"), ("pagos", "payments"),
               ("devoluciones", "returns"), ("comisiones", "commissions"), ("canales", "channels"), ("zonas", "zones")],
    "clinica": [("pacientes", "patients"), ("medicos", "doctors"), ("citas", "appointments"), ("diagnosticos", "diagnoses"),
                ("tratamientos", "treatments"), ("recetas", "prescriptions"), ("examenes", "exams"), ("habitaciones", "rooms"),
                ("especialidades", "specialties"), ("aseguradoras", "insurers"), ("historias", "records"), ("enfermeras", "nurses")],
    "colegio": [("alumnos", "students"), ("profesores", "teachers"), ("cursos", "courses"), ("aulas", "classrooms"),
                ("matriculas", "enrollments"), ("notas", "grades"), ("horarios", "schedules"), ("apoderados", "guardians"),
                ("asistencias", "attendances"), ("periodos", "terms"), ("materias", "subjects"), ("becas", "scholarships")],
    "logistica": [("envios", "shipments"), ("rutas", "routes"), ("vehiculos", "vehicles"), ("conductores", "drivers"),
                  ("guias", "waybills"), ("despachos", "dispatches"), ("paquetes", "parcels"), ("sucursales", "branches"),
                  ("transportistas", "carriers"), ("incidencias", "incidents"), ("peajes", "tolls"), ("combustibles", "fuels")],
    "rrhh": [("empleados", "employees"), ("cargos", "positions"), ("departamentos", "departments"), ("contratos", "contracts"),
             ("vacaciones", "vacations"), ("planillas", "payrolls"), ("marcaciones", "clockings"), ("permisos", "leaves"),
             ("capacitaciones", "trainings"), ("evaluaciones", "reviews"), ("beneficios", "benefits"), ("sanciones", "sanctions")],
    "contabilidad": [("cuentas", "accounts"), ("asientos", "entries"), ("diarios", "journals"), ("impuestos", "taxes"),
                     ("bancos", "banks"), ("conciliaciones", "reconciliations"), ("centros_costo", "cost_centers"),
                     ("presupuestos", "budgets"), ("monedas", "currencies"), ("retenciones", "withholdings"), ("activos", "assets"), ("balances", "balances")],
    "biblioteca": [("libros", "books"), ("autores", "authors"), ("editoriales", "publishers"), ("prestamos", "loans"),
                   ("socios", "members"), ("ejemplares", "copies"), ("generos", "genres"), ("reservas", "holds"),
                   ("multas", "fines"), ("estantes", "shelves"), ("revistas", "magazines"), ("donaciones", "donations")],
    "hotel": [("huespedes", "guests"), ("reservas", "bookings"), ("habitaciones", "rooms"), ("tarifas", "rates"),
              ("servicios", "services"), ("consumos", "charges"), ("limpiezas", "housekeepings"), ("pisos", "floors"),
              ("check_ins", "check_ins"), ("canales", "channels"), ("promociones", "promotions"), ("eventos", "events")],
    "taller": [("ordenes", "work_orders"), ("repuestos", "parts"), ("mecanicos", "mechanics"), ("diagnosticos", "diagnostics"),
               ("garantias", "warranties"), ("herramientas", "tools"), ("bahias", "bays"), ("inspecciones", "inspections"),
               ("presupuestos", "estimates"), ("recambios", "spares"), ("flotas", "fleets"), ("citas", "bookings")],
}
SATELLITES = {"es": ["detalle", "historial", "tipos", "estados", "documentos", "contactos"], "en": ["details", "history", "types", "statuses", "documents", "contacts"]}
SYSTEM_PREFIXES = ["inv", "vta", "cli", "col", "log", "rrhh", "con", "bib", "hot", "tal", "gsp", "sip", "erp", "crm", "sis"]

COLUMN_POOL = {
    "es": {
        "string": ["nombre", "descripcion", "codigo", "direccion", "telefono", "correo", "observacion", "documento", "serie", "numero", "referencia", "titulo"],
        "decimal": ["monto", "precio", "total", "cantidad", "saldo", "peso", "costo", "tarifa"],
        "integer": ["orden", "stock", "edad", "nivel", "duracion", "capacidad"],
        "date": ["fecha_inicio", "fecha_fin", "fecha_emision", "fecha_registro", "fecha_nacimiento"],
        "boolean": ["activo", "es_principal", "visible", "vigente"],
    },
    "en": {
        "string": ["name", "description", "code", "address", "phone", "email", "notes", "document", "serial", "number", "reference", "title"],
        "decimal": ["amount", "price", "total", "quantity", "balance", "weight", "cost", "rate"],
        "integer": ["position", "stock", "age", "level", "duration", "capacity"],
        "date": ["start_date", "end_date", "issued_at", "registered_at", "birth_date"],
        "boolean": ["active", "is_primary", "visible", "valid"],
    },
}


def studly(s: str) -> str:
    return "".join(p[:1].upper() + p[1:] for p in re.split(r"[_\W]+", s) if p)


def singular(word: str, lang: str) -> str:
    w = word
    if lang == "en":
        if w.endswith("ies"):
            return w[:-3] + "y"
        if w.endswith(("sses", "ches", "shes", "xes", "zes")):
            return w[:-2]
        return w[:-1] if w.endswith("s") and not w.endswith("ss") else w
    if w.endswith("ciones"):
        return w[:-2]
    if w.endswith(("ces",)):
        return w[:-3] + "z"
    if w.endswith("es") and len(w) > 4 and w[-3] not in "aeiou":
        return w[:-2]
    return w[:-1] if w.endswith("s") and len(w) > 3 else w


# ───────────────────────────── muestreo de ejes ──────────────────────────


def load_real_weights() -> dict[str, dict[str, float]]:
    """Frecuencia (share) de cada valor en los repos reales, si hay perfil."""
    path = STRUCT / "variation_profile.json"
    weights: dict[str, dict[str, float]] = {}
    if not path.exists():
        return weights
    profile = json.loads(path.read_text(encoding="utf-8"))
    for axis, spec in profile.get("axes", {}).items():
        weights[axis] = {v: info["share"] for v, info in spec["values"].items()}
    return weights


def sample_axes(count: int, rng: random.Random) -> list[dict[str, str]]:
    """Un valor por eje y repo. Muestrea con frecuencias reales pero GARANTIZA
    que cada valor de cada eje aparezca en >= 2 repos (diseño de cobertura)."""
    real = load_real_weights()
    configs: list[dict[str, str]] = [{} for _ in range(count)]
    for axis, values in AXES.items():
        weights = [1.0 + 3.0 * real.get(axis, {}).get(v, 0.0) if v in real.get(axis, {}) else OUT_OF_SET_WEIGHT for v in values]
        column: list[str] = []
        for v in values:  # cobertura: 2 apariciones mínimas de cada valor
            column += [v, v]
        column = column[:count] if len(column) > count else column
        while len(column) < count:
            column.append(rng.choices(values, weights=weights)[0])
        rng.shuffle(column)
        for cfg, v in zip(configs, column):
            cfg[axis] = v
    return configs


# ───────────────────────────── modelo de datos ───────────────────────────


class ModelCtx:
    def __init__(self, table: str, bare: str, prefix: str, system: str, module: str, lang: str):
        self.table = table
        self.bare = bare
        self.prefix = prefix
        self.system = system
        self.module = module
        self.lang = lang
        self.class_name = ""
        self.columns: list[tuple[str, str]] = []
        self.fks: list[tuple[str, "ModelCtx"]] = []
        self.files: dict[str, list[str]] = {}  # rol -> [paths]
        self.usado: dict[str, list[str]] = {}
        self.has_filter = self.has_resource = self.has_service = self.has_controller = True
        self.service_group: str | None = None


class RepoBuilder:
    def __init__(self, idx: int, cfg: dict[str, str], rng: random.Random, out: Path, min_models: int, max_models: int, real_names: list[str]):
        self.idx = idx
        self.cfg = cfg
        self.rng = rng
        self.root = out / f"repo_{idx:02d}"
        self.min_models, self.max_models = min_models, max_models
        self.real_names = real_names
        self.lang = cfg["language"]
        self.models: list[ModelCtx] = []
        self.written: list[str] = []
        self.services_sub = rng.random() < 0.4
        self.folder_style = rng.choice(["snake", "camel"])
        self.trait_verb = rng.choice(["Validates", "Validate"])
        self.system_labels: list[tuple[str, str]] = []  # (prefijo, Sistema)
        self.modules: list[str] = []

    # ── utilidades de escritura ──
    def w(self, rel: str, content: str) -> str:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        self.written.append(rel)
        return rel

    # ── construcción de modelos ──
    def build_models(self) -> None:
        cfg, rng = self.cfg, self.rng
        n = rng.randint(self.min_models, self.max_models)
        domains = rng.sample(list(DOMAINS), k=min(len(DOMAINS), 1 + (n // 20)))
        pool: list[tuple[str, str]] = []
        for d in domains:
            pool += [(d, e) for e in DOMAINS[d]]  # type: ignore[misc]
        rng.shuffle(pool)
        n_sys = rng.randint(2, 4) if cfg["table_prefix"] != "ninguno" else 1
        systems = rng.sample(SYSTEM_PREFIXES, k=n_sys)
        self.system_labels = [(p, studly(p) if len(p) > 3 else p.upper()) for p in systems]
        n_modules = rng.randint(2, 4)
        module_names = ["Inventario", "Ventas", "Clinica", "Colegio", "Logistica", "Personal", "Finanzas", "Reportes", "Catalogos"]
        if self.lang == "en":
            module_names = ["Inventory", "Sales", "Clinic", "School", "Logistics", "Staff", "Finance", "Reports", "Catalogs"]
        self.modules = rng.sample(module_names, k=n_modules)
        seen: set[str] = set()
        i = 0
        while len(self.models) < n and i < 10_000:
            i += 1
            if pool and rng.random() < 0.85:
                domain, (es, en) = pool[(len(self.models) + i) % len(pool)]
                base = es if self.lang == "es" else en
            elif self.real_names and rng.random() < 0.5:
                domain, base = "real", rng.choice(self.real_names)
            else:
                domain, (es, en) = rng.choice(pool)
                base = es if self.lang == "es" else en
            if rng.random() < 0.35:  # satélite: personal -> personal_historial (colisiones de nombre realistas)
                base = f"{base}_{rng.choice(SATELLITES[self.lang])}"
            if base in seen:
                continue
            seen.add(base)
            pfx, sysname = rng.choice(self.system_labels)
            if cfg["table_prefix"] == "por sistema":
                prefix = pfx
            elif cfg["table_prefix"] == "catalogo mixto":
                prefix = rng.choice(["catalogo", "catalogo", pfx, ""])
            else:
                prefix = ""
            table = f"{prefix}_{base}" if prefix else base
            ctx = ModelCtx(table, base, prefix, sysname, rng.choice(self.modules), self.lang)
            self._decide_class_and_columns(ctx)
            self.models.append(ctx)
        for ctx in self.models:  # FKs solo entre modelos del mismo repo
            for other in rng.sample(self.models, k=min(len(self.models), rng.randint(0, 3))):
                if other is not ctx:
                    fk_col = f"{singular(other.bare, self.lang)}_id"
                    if fk_col not in {c for c, _ in ctx.columns} and (fk_col, other) not in ctx.fks:
                        ctx.fks.append((fk_col, other))

    def _decide_class_and_columns(self, ctx: ModelCtx) -> None:
        rng, cfg = self.rng, self.cfg
        style = cfg["class_style"]
        if style == "mixto":
            style = rng.choice(["snake literal", "StudlyCase"])
        ctx.class_name = ctx.table if style == "snake literal" else studly(ctx.table)
        pool = COLUMN_POOL[self.lang]
        cols: list[tuple[str, str]] = []
        for kind, names in pool.items():
            for name in rng.sample(names, k=min(len(names), rng.randint(0, 3 if kind != "string" else 4))):
                cols.append((name, kind))
        if not any(k == "string" for _, k in cols):
            cols.append((pool["string"][0], "string"))
        ctx.columns = list(dict(cols).items())
        r = rng.random()
        ctx.has_resource = r > 0.05
        ctx.has_service = rng.random() > 0.08
        ctx.has_filter = rng.random() > 0.05
        ctx.has_controller = rng.random() > 0.03

    # ── nombres ──
    def core(self, ctx: ModelCtx, style: str) -> str:
        singular_files = self.cfg["file_number"] == "singular"
        bare = singular(ctx.bare, self.lang) if singular_files else ctx.bare
        table = f"{ctx.prefix}_{bare}" if ctx.prefix else bare
        if style == "{tabla}":
            return table
        if style == "{CamelSinPrefijo}":
            return studly(bare)
        if style == "{CamelConPrefijo}":
            return studly(table)
        return studly(table) if ctx.class_name == studly(ctx.table) else (ctx.class_name if not singular_files else table)

    def sub_folder(self, ctx: ModelCtx) -> str:
        s = self.cfg["sublevel"]
        if s == "conexion":
            return "db" + (ctx.prefix or "main")
        if s == "sistema":
            return ctx.system
        return ""

    def table_folder(self, ctx: ModelCtx) -> str:
        return ctx.table if self.folder_style == "snake" else studly(ctx.table)

    def ns(self, rel_dir: str) -> str:
        parts = rel_dir.split("/")
        parts[0] = {"app": "App"}.get(parts[0], parts[0])
        return "\\".join(parts)

    def base_dirs(self, ctx: ModelCtx) -> dict[str, str]:
        layout = self.cfg["layout"]
        sub = self.sub_folder(ctx)
        join = lambda *p: "/".join(x for x in p if x)  # noqa: E731
        req = self.cfg["requests_dir"]
        if layout == "modular":
            b = f"Modules/{ctx.module}/App"
            return {
                "model": join(b, "Models", sub), "filter": join(b, "Filters", sub), "resource": join(b, "Http/Resources", sub),
                "request": join(b, "Http", req, sub), "service": join(b, "Services", sub if self.services_sub else ""),
                "controller": join(b, "Http/Controllers", sub),
            }
        if layout == "ddd":
            b = f"app/Domain/{ctx.module}"
            ctl = {"Api/{sub}": join("app/Http/Controllers/Api", ctx.module), "Api raíz": "app/Http/Controllers/Api", "Api/V1": join("app/Http/Controllers/Api/V1", ctx.module)}[self.cfg["controllers_dir"]]
            return {
                "model": join(b, "Models"), "filter": join(b, "Filters"), "resource": join(b, "Resources"),
                "request": join(b, req), "service": join(b, "Services"), "controller": ctl,
            }
        ctl_base = {"Api/{sub}": join("app/Http/Controllers/Api", sub), "Api raíz": "app/Http/Controllers/Api", "Api/V1": join("app/Http/Controllers/Api/V1", sub)}[self.cfg["controllers_dir"]]
        return {
            "model": join("app/Models", sub), "filter": join("app/Filters", sub), "resource": join("app/Http/Resources", sub),
            "request": join("app/Http", req, sub), "service": join("app/Services", sub if self.services_sub else ""),
            "controller": ctl_base,
        }

    # ── PHP ──
    def php_model(self, ctx: ModelCtx, dirs: dict[str, str], filt_fq: str | None) -> str:
        cfg = self.cfg
        imports = ["use Illuminate\\Database\\Eloquent\\Model;", "use Illuminate\\Database\\Eloquent\\Factories\\HasFactory;", "use Essa\\APIToolKit\\Filters\\Filterable;"]
        traits = ["HasFactory", "Filterable"]
        if cfg["soft_delete"] != "no":
            imports.append("use Illuminate\\Database\\Eloquent\\SoftDeletes;")
            traits.append("SoftDeletes")
        if filt_fq:
            imports.append(f"use {filt_fq};")
        rels: list[str] = []
        for fk_col, other in ctx.fks:
            alias = singular(other.bare, self.lang)
            other_fq = f"{self.ns(self.base_dirs(other)['model'])}\\{other.class_name}"
            if other_fq not in " ".join(imports):
                imports.append(f"use {other_fq};")
            rels.append(f"    public function {alias}()\n    {{\n        return $this->belongsTo({other.class_name}::class, '{fk_col}', 'pkid');\n    }}\n")
        aud = cfg["audit_relation"]
        aud_cols = []
        if aud != "ausente":
            aud_cols = ["created_by_id", "updated_by_id"]
            user_cls = "User" if cfg["user_model"] == "User" else cfg["user_model"]
            for name in {"created_by": ("created_by", "updated_by"), "createdBy": ("createdBy", "updatedBy"), "create_by": ("create_by", "update_by")}[aud]:
                rels.append(f"    public function {name}()\n    {{\n        return $this->belongsTo({user_cls}::class, '{'created_by_id' if name.lower().startswith('create') else 'updated_by_id'}', 'pkid');\n    }}\n")
        fillable = [c for c, _ in ctx.columns] + [fk for fk, _ in ctx.fks] + aud_cols
        pk = cfg["pk"]
        pk_lines = {
            "id uuid string": "    protected $primaryKey = 'id';\n    public $incrementing = false;\n    protected $keyType = 'string';\n",
            "pkid int": "    protected $primaryKey = 'pkid';\n",
            "pkid + id": "    protected $primaryKey = 'pkid';\n",
            "natural": "    protected $primaryKey = 'codigo';\n    public $incrementing = false;\n    protected $keyType = 'string';\n",
        }[pk]
        if pk in ("pkid int", "pkid + id"):
            fillable = ["pkid"] + fillable
        extra = "    const DELETED_AT = 'deleted';\n" if cfg["soft_delete"] == "deleted" else ""
        default_filters = f"    protected string $default_filters = {filt_fq.rsplit(chr(92), 1)[-1]}::class;\n" if filt_fq else ""
        conn = f"    protected $connection = 'mysql_{('db' + ctx.prefix) if ctx.prefix else 'dbmain'}';\n"
        if cfg["sublevel"] == "conexion":
            conn = f"    protected $connection = 'mysql_{self.sub_folder(ctx)}';\n"
        return (
            "<?php\n\nnamespace " + self.ns(dirs["model"]) + ";\n\n" + "\n".join(imports) + "\n\n"
            f"class {ctx.class_name} extends Model\n{{\n    use {', '.join(traits)};\n\n{extra}{conn}    protected $table = '{ctx.table}';\n{pk_lines}"
            f"{default_filters}\n    protected $fillable = [{', '.join(repr(f) for f in fillable)}];\n\n" + "\n".join(rels) + "}\n"
        )

    def php_filter(self, ctx: ModelCtx, cls: str, dirs: dict[str, str], model_fq: str, extra_models: list[str]) -> str:
        cols = [c for c, k in ctx.columns if k in ("string", "boolean")]
        search = [c for c, k in ctx.columns if k == "string"][:3]
        allowed = ["activo"] + [fk for fk, _ in ctx.fks][:3]
        uses = "\n".join(f"use {m};" for m in [model_fq] + extra_models)
        methods = "".join(f"    public function {c}($term)\n    {{\n        return $this->builder->where('{c}', 'LIKE', \"%{{$term}}%\");\n    }}\n\n" for c in cols[:2])
        return (
            f"<?php\n\nnamespace {self.ns(dirs['filter'])};\n\n{uses}\nuse Essa\\APIToolKit\\Filters\\QueryFilters;\n\n"
            f"class {cls} extends QueryFilters\n{{\n    protected array $columnSearch = [{', '.join(repr(s) for s in search)}];\n"
            f"    protected array $allowedFilters = [{', '.join(repr(a) for a in allowed)}];\n\n{methods}}}\n"
        )

    def php_resource(self, ctx: ModelCtx, cls: str, dirs: dict[str, str], minimal: bool, mixin: str | None) -> str:
        cols = [c for c, _ in ctx.columns]
        keys = ["id"] + (cols[:2] if minimal else cols) + ([] if minimal else [self.singular_alias(o) for _, o in ctx.fks][:2])
        body = "".join(f"            '{k}' => $this->{k},\n" for k in keys)
        doc = f"/**\n * @mixin {mixin}\n */\n" if mixin else ""
        return (
            f"<?php\n\nnamespace {self.ns(dirs['resource'])};\n\nuse Illuminate\\Http\\Resources\\Json\\JsonResource;\n\n{doc}"
            f"class {cls} extends JsonResource\n{{\n    public function toArray($request): array\n    {{\n        return [\n{body}        ];\n    }}\n}}\n"
        )

    def singular_alias(self, other: ModelCtx) -> str:
        return singular(other.bare, self.lang)

    def php_request(self, ctx: ModelCtx, cls: str, ns_dir: str, kind: str, model_fq: str, base_fq: str | None, trait_fq: str | None) -> str:
        cols = [c for c, _ in ctx.columns] + [fk for fk, _ in ctx.fks]
        marker = "'required'" if kind == "store" else "'sometimes'"
        rules = "".join(f"            '{c}' => [{marker}],\n" for c in cols[:6])
        uses = ["use Illuminate\\Foundation\\Http\\FormRequest;"]
        if kind == "base":
            return (
                f"<?php\n\nnamespace {self.ns(ns_dir)};\n\nuse Illuminate\\Foundation\\Http\\FormRequest;\n\n"
                f"abstract class {cls} extends FormRequest\n{{\n    public function authorize(): bool\n    {{\n        return true;\n    }}\n\n"
                f"    public function messages(): array\n    {{\n        return [];\n    }}\n}}\n"
            )
        parent = "FormRequest"
        if base_fq:
            uses.append(f"use {base_fq};")
            parent = base_fq.rsplit("\\", 1)[-1]
        if trait_fq:
            uses.append(f"use {trait_fq};")
        if self.rng.random() < 0.5:
            uses.append(f"use {model_fq};")
        trait_use = f"    use {trait_fq.rsplit(chr(92), 1)[-1]};\n\n" if trait_fq else ""
        return (
            f"<?php\n\nnamespace {self.ns(ns_dir)};\n\n" + "\n".join(dict.fromkeys(uses)) + f"\n\nclass {cls} extends {parent}\n{{\n{trait_use}"
            f"    public function rules(): array\n    {{\n        return [\n{rules}        ];\n    }}\n}}\n"
        )

    def php_trait(self, ctx: ModelCtx, cls: str, ns_dir: str) -> str:
        rules = "".join(f"            '{fk}' => [Rule::exists('{ctx.table}', 'id')],\n" for fk, _ in ctx.fks[:3])
        return (
            f"<?php\n\nnamespace {self.ns(ns_dir)};\n\nuse Illuminate\\Validation\\Rule;\n\ntrait {cls}\n{{\n"
            f"    public function getRelacionesRules(): array\n    {{\n        return [\n{rules}        ];\n    }}\n}}\n"
        )

    def php_service(self, cls: str, dirs: dict[str, str], models: list[ModelCtx]) -> str:
        uses = ["use App\\Services\\CrudService;"] + [f"use {self.ns(self.base_dirs(m)['model'])}\\{m.class_name};" for m in models]
        return (
            f"<?php\n\nnamespace {self.ns(dirs['service'])};\n\n" + "\n".join(uses) + f"\n\nclass {cls}\n{{\n    public function __construct(private CrudService $crud)\n    {{\n    }}\n\n"
            f"    public function index(bool $paginate = false)\n    {{\n        return {models[0].class_name}::useFilters()->get();\n    }}\n}}\n"
        )

    def php_controller(self, cls: str, dirs: dict[str, str], service_fq: str | None, models: list[ModelCtx]) -> str:
        uses = ["use App\\Http\\Controllers\\Controller;", "use Essa\\APIToolKit\\Api\\ApiResponse;"]
        if service_fq:
            uses.append(f"use {service_fq};")
        uses += [f"use {self.ns(self.base_dirs(m)['model'])}\\{m.class_name};" for m in models]
        ctor = ""
        if service_fq:
            s = service_fq.rsplit("\\", 1)[-1]
            ctor = f"    public function __construct(protected {s} $service)\n    {{\n    }}\n\n"
        return (
            f"<?php\n\nnamespace {self.ns(dirs['controller'])};\n\n" + "\n".join(uses) + f"\n\nclass {cls} extends Controller\n{{\n    use ApiResponse;\n\n{ctor}"
            f"    public function index()\n    {{\n        return $this->responseSuccess('ok', []);\n    }}\n}}\n"
        )

    def php_migration(self, ctx: ModelCtx) -> str:
        cfg = self.cfg
        lines = []
        pk = cfg["pk"]
        if pk == "id uuid string":
            lines.append("            $table->char('id', 36)->primary();")
        elif pk == "pkid int":
            lines.append("            $table->id('pkid');")
        elif pk == "pkid + id":
            lines.append("            $table->id('pkid');")
            lines.append("            $table->char('id', 36)->unique();")
        else:
            lines.append("            $table->string('codigo', 20)->primary();")
        type_map = {"string": "string('{c}', 150)->nullable()", "decimal": "decimal('{c}', 12, 2)->nullable()", "integer": "integer('{c}')->nullable()",
                    "date": "date('{c}')->nullable()", "boolean": "boolean('{c}')->default(true)"}
        for c, k in ctx.columns:
            lines.append("            $table->" + type_map[k].format(c=c) + ";")
        for fk, _ in ctx.fks:
            lines.append(f"            $table->unsignedBigInteger('{fk}')->nullable();")
        if cfg["audit_relation"] != "ausente":
            lines.append("            $table->unsignedBigInteger('created_by_id')->nullable();")
            lines.append("            $table->unsignedBigInteger('updated_by_id')->nullable();")
        lines.append("            $table->timestamps();")
        if cfg["soft_delete"] == "deleted_at":
            lines.append("            $table->softDeletes();")
        elif cfg["soft_delete"] == "deleted":
            lines.append("            $table->timestamp('deleted')->nullable();")
        return (
            "<?php\n\nuse Illuminate\\Database\\Migrations\\Migration;\nuse Illuminate\\Database\\Schema\\Blueprint;\nuse Illuminate\\Support\\Facades\\Schema;\n\n"
            f"return new class extends Migration\n{{\n    public function up(): void\n    {{\n        Schema::create('{ctx.table}', function (Blueprint $table) {{\n"
            + "\n".join(lines) + "\n        });\n    }\n};\n"
        )

    # ── construcción del repo ──
    def build(self) -> dict:
        cfg, rng = self.cfg, self.rng
        if self.root.exists():
            shutil.rmtree(self.root)
        self.build_models()

        # modelo de usuario (sin recursos): existe en el repo, sin dueño de archivos
        user_ctx = None
        if cfg["audit_relation"] != "ausente" or True:
            ubare = {"User": "users", "catalogo_usuario": "usuario", "usuarios": "usuarios"}[cfg["user_model"]]
            user_ctx = ModelCtx(ubare if cfg["user_model"] != "catalogo_usuario" else "catalogo_usuario", ubare, "", "Auth", self.modules[0], self.lang)
            user_ctx.class_name = cfg["user_model"]
            user_ctx.columns = [("name", "string"), ("email", "string")]
            user_dir = "app/Models"
            self.w(f"{user_dir}/{user_ctx.class_name}.php", self.php_model(user_ctx, {"model": user_dir}, None))

        # migraciones
        for i, ctx in enumerate(self.models):
            self.w(f"database/migrations/2026_01_01_{i:06d}_create_{ctx.table}_table.php", self.php_migration(ctx))

        # servicios agrupados (un Service atiende 2-3 modelos): dueño = el primero, el resto queda como "usado en"
        group_of: dict[str, list[ModelCtx]] = {}
        candidates = [m for m in self.models if m.has_service]
        rng.shuffle(candidates)
        for _ in range(rng.randint(1, 3)):
            if len(candidates) >= 3:
                g = [candidates.pop() for _ in range(rng.randint(2, 3))]
                for extra in g[1:]:
                    extra.has_service = False
                group_of[g[0].table] = g

        controllers_written: dict[str, ModelCtx] = {}
        route_records: list[tuple[ModelCtx, str, str]] = []  # (modelo, FQCN controller, controller class)

        for ctx in self.models:
            dirs = self.base_dirs(ctx)
            model_path = self.w(f"{dirs['model']}/{ctx.class_name}.php", "")
            model_fq = f"{self.ns(dirs['model'])}\\{ctx.class_name}"

            # Filter
            filt_fq = None
            if ctx.has_filter:
                fcls = self.core(ctx, cfg["entity_name"]) + cfg["filter_suffix"]
                extra = [f"{self.ns(self.base_dirs(o)['model'])}\\{o.class_name}" for _, o in ctx.fks[:2] if rng.random() < 0.5]
                fpath = self.w(f"{dirs['filter']}/{fcls}.php", self.php_filter(ctx, fcls, dirs, model_fq, extra))
                filt_fq = f"{self.ns(dirs['filter'])}\\{fcls}"
                ctx.files.setdefault("filter", []).append(fpath)
                for o in ctx.fks[:2]:
                    pass
            (self.root / model_path).write_text(self.php_model(ctx, dirs, filt_fq), encoding="utf-8", newline="\n")

            # Resources
            if ctx.has_resource:
                rcls = self.core(ctx, cfg["entity_name"]) + "Resource"
                mixin = model_fq if rng.random() < 0.3 else None
                ctx.files.setdefault("resource", []).append(self.w(f"{self.res_dir(ctx, dirs)}/{rcls}.php", self.php_resource(ctx, rcls, {"resource": self.res_dir(ctx, dirs)}, False, mixin)))
                suffix = cfg["min_resource_suffix"]
                if rng.random() < 0.08:
                    suffix = rng.choice(["Relation", "Relacion"])  # grafía inconsistente
                mcls = f"{self.core(ctx, cfg['entity_name'])}{suffix}Resource"
                ctx.files.setdefault("relation_resource", []).append(self.w(f"{self.res_dir(ctx, dirs)}/{mcls}.php", self.php_resource(ctx, mcls, {"resource": self.res_dir(ctx, dirs)}, True, None)))

            # Requests
            self.write_requests(ctx, dirs, model_fq)

            # Service
            service_fq = None
            if ctx.has_service or ctx.table in group_of:
                models_served = group_of.get(ctx.table, [ctx])
                scls = self.service_class(ctx)
                spath = self.w(f"{dirs['service']}/{scls}.php", self.php_service(scls, dirs, models_served))
                service_fq = f"{self.ns(dirs['service'])}\\{scls}"
                ctx.files.setdefault("service", []).append(spath)
                for extra in models_served[1:]:
                    extra.usado.setdefault("service", []).append(spath)
                ctx.has_service = True

            # Controller
            if ctx.has_controller:
                ccls = self.core(ctx, cfg["entity_name"]) + "Controller"
                cdir = dirs["controller"]
                if rng.random() < 0.12:  # controller legado: en otra sub-carpeta (`Legacy/`), no en la del patrón del proyecto
                    cdir = cdir.split("Controllers")[0] + "Controllers/Legacy"
                cpath = self.w(f"{cdir}/{ccls}.php", self.php_controller(ccls, {"controller": cdir}, service_fq, [ctx]))
                ctx.files.setdefault("controller", []).append(cpath)
                controllers_written[ccls] = ctx
                route_records.append((ctx, f"{self.ns(cdir)}\\{ccls}", ccls))

        self.write_routes(route_records)
        self.write_noise()
        self.write_registration()
        return self.manifest()

    def res_dir(self, ctx: ModelCtx, dirs: dict[str, str]) -> str:
        if self.cfg["per_table_folder_resources"] == "si":
            return f"{dirs['resource']}/{self.table_folder(ctx)}"
        return dirs["resource"]

    def service_class(self, ctx: ModelCtx) -> str:
        style = self.cfg["service_name"]
        if style == "sin_sufijo":
            return self.core(ctx, "{CamelSinPrefijo}")
        if style == "Manager":
            return self.core(ctx, "{CamelSinPrefijo}") + "Manager"
        return self.core(ctx, style) + "Service"

    def write_requests(self, ctx: ModelCtx, dirs: dict[str, str], model_fq: str) -> None:
        cfg = self.cfg
        style = cfg["request_name"]
        in_folder = style == "accion_en_carpeta"
        per_table = cfg["per_table_folder_requests"] == "si" or in_folder
        rdir = f"{dirs['request']}/{self.table_folder(ctx)}" if per_table else dirs["request"]
        if in_folder:
            core = ""
        elif style == "{tabla}":
            core = self.core(ctx, "{tabla}")
        elif style in ("{CamelSinPrefijo}", "sin_sufijo_Request", "accion_sufijo"):
            core = self.core(ctx, "{CamelSinPrefijo}")
        else:
            core = self.core(ctx, "{ClaseModelo}")

        def cls(action: str) -> str:
            if in_folder:
                return f"{action}Request"
            if style == "sin_sufijo_Request":
                return f"{action}{core}"
            if style == "accion_sufijo" and action != "Base":
                return f"{core}{action}Request"
            return f"{action}{core}Request"

        base_fq = None
        if cfg["base_request"] == "clase Base abstracta":
            bcls = cls("Base")
            bpath = self.w(f"{rdir}/{bcls}.php", self.php_request(ctx, bcls, rdir, "base", model_fq, None, None))
            ctx.files.setdefault("base_request", []).append(bpath)
            base_fq = f"{self.ns(rdir)}\\{bcls}"

        trait_fq = None
        tstyle = cfg["request_traits"]
        if tstyle != "ninguno":
            tcls = f"{self.trait_verb}{studly(self.core(ctx, '{CamelSinPrefijo}'))}"
            tdir = f"{dirs['request']}/Traits/{self.table_folder(ctx)}" if tstyle.startswith("Traits/{tabla}") else f"{dirs['request']}/Traits"
            tpath = self.w(f"{tdir}/{tcls}.php", self.php_trait(ctx, tcls, tdir))
            ctx.files.setdefault("request_trait", []).append(tpath)
            trait_fq = f"{self.ns(tdir)}\\{tcls}"

        for action, kind in (("Store", "store"), ("Update", "update")):
            c = cls(action)
            p = self.w(f"{rdir}/{c}.php", self.php_request(ctx, c, rdir, kind, model_fq, base_fq, trait_fq))
            ctx.files.setdefault(f"{kind}_request", []).append(p)

    def route_path_for(self, records: list[tuple[ModelCtx, str, str]]) -> list[tuple[str, list[tuple[ModelCtx, str, str]]]]:
        cfg, rng = self.cfg, self.rng
        loc = cfg["routes_location"]
        layout = cfg["layout"]
        groups: dict[str, list] = {}
        for rec in records:
            ctx = rec[0]
            if layout == "modular":
                key = f"Modules/{ctx.module}/routes/api.php" if loc == "en línea en api.php" else f"Modules/{ctx.module}/routes/{ctx.table}.php"
            elif loc == "routes/{tabla}.php":
                key = f"routes/{ctx.table}.php"
            elif loc == "routes/modules/{tabla}.php":
                key = f"routes/modules/{ctx.table}.php"
            elif loc == "en línea en api.php":
                key = "routes/api.php"
            elif loc == "routes/{area}.php":
                key = f"routes/{ctx.module.lower()}.php"
            else:
                key = f"routes/api/{ctx.module.lower()}.php"
            groups.setdefault(key, []).append(rec)
        return list(groups.items())

    def write_routes(self, records: list[tuple[ModelCtx, str, str]]) -> None:
        mw = self.cfg["token_middleware"]
        mw_expr = {"[ApiToken::class]": "Route::middleware([ApiToken::class])", "'ApiToken'": "Route::middleware('ApiToken')",
                   "ValidateSessionKey": "Route::middleware(ValidateSessionKey::class)", "auth:sanctum": "Route::middleware('auth:sanctum')"}[mw]
        mw_use = {"[ApiToken::class]": "use App\\Http\\Middleware\\ApiToken;\n", "ValidateSessionKey": "use App\\Http\\Middleware\\ValidateSessionKey;\n"}.get(mw, "")
        for path, recs in self.route_path_for(records):
            uses = "".join(f"use {fq};\n" for _, fq, _ in recs)
            body = "".join(f"    Route::apiResource('{ctx.table}', {cls}::class);\n" for ctx, _, cls in recs)
            self.w(path, f"<?php\n\nuse Illuminate\\Support\\Facades\\Route;\n{mw_use}{uses}\n{mw_expr}->group(function () {{\n{body}}});\n")
            for ctx, _, _ in recs:
                ctx.files.setdefault("route", []).append(path)

    def write_noise(self) -> None:
        rng, cfg = self.rng, self.cfg
        # clases base genéricas (no son de ningún modelo)
        self.w("app/Http/Controllers/Controller.php", "<?php\n\nnamespace App\\Http\\Controllers;\n\nabstract class Controller\n{\n}\n")
        self.w("app/Services/CrudService.php", "<?php\n\nnamespace App\\Services;\n\nclass CrudService\n{\n}\n")
        self.w("app/Services/AbstractModuleService.php", "<?php\n\nnamespace App\\Services;\n\nabstract class AbstractModuleService\n{\n}\n")
        # controllers de reportes que importan muchos modelos (ruido: no son dueños de ninguno)
        for i in range(rng.randint(1, 3)):
            picked = rng.sample(self.models, k=min(len(self.models), rng.randint(6, 10)))
            cdir = "app/Http/Controllers/Api" + ("/Reportes" if cfg["controllers_dir"] != "Api raíz" else "")
            cls = f"Reporte{i + 1}Controller" if cfg["language"] == "es" else f"Report{i + 1}Controller"
            path = self.w(f"{cdir}/{cls}.php", self.php_controller(cls, {"controller": cdir}, None, picked))
            for m in picked:
                m.usado.setdefault("controller", []).append(path)
        # otros requests (Bulk, Cerrar...): existen pero no son de ningún rol del dataset
        for m in rng.sample(self.models, k=min(len(self.models), rng.randint(2, 6))):
            rdir = self.base_dirs(m)["request"]
            self.w(f"{rdir}/Bulk{studly(m.bare)}Request.php", f"<?php\n\nnamespace {self.ns(rdir)};\n\nuse Illuminate\\Foundation\\Http\\FormRequest;\n\nclass Bulk{studly(m.bare)}Request extends FormRequest\n{{\n}}\n")
        # carpetas vacías (restos de generaciones anteriores: NO deben contar como estructura)
        for name in rng.sample(["app/Http/Resources/Legacy", "app/Models/Old", "app/Services/Tmp", "routes/modules_old", "app/Filters/Backup"], k=rng.randint(2, 4)):
            (self.root / name).mkdir(parents=True, exist_ok=True)

    def write_registration(self) -> None:
        reg = self.cfg["route_registration"]
        if reg == "RouteServiceProvider":
            self.w("app/Providers/RouteServiceProvider.php", "<?php\n\nnamespace App\\Providers;\n\nclass RouteServiceProvider\n{\n    public function boot(): void\n    {\n        // Route::middleware('api')->prefix('api')->group(base_path('routes/api.php'));\n        $this->routes(function () {\n            Route::middleware('api')->prefix('api')->group(base_path('routes/api.php'));\n        });\n    }\n}\n")
        elif reg == "bootstrap/app.php":
            self.w("bootstrap/app.php", "<?php\n\nreturn Application::configure(basePath: dirname(__DIR__))\n    ->withRouting(\n        api: __DIR__.'/../routes/api.php',\n    )->create();\n")
        if self.cfg["routes_location"] != "en línea en api.php" and self.cfg["layout"] != "modular":
            body = "<?php\n\nuse Illuminate\\Support\\Facades\\Route;\n\n" + ("foreach (glob(base_path('routes/modules/*.php')) as $file) {\n    require $file;\n}\n" if reg == "require en api.php" else "")
            self.w("routes/api.php", body)
        self.w("composer.json", json.dumps({"require": {"php": "^8.2", "laravel/framework": "^12.0", "essa/api-tool-kit": "^1.1"}}, indent=2))
        self.w("config/database.php", "<?php\n\nreturn [\n    'connections' => [\n" + "".join(f"        'mysql_{n}' => ['driver' => 'mysql'],\n" for n in sorted({('db' + (m.prefix or 'main')) for m in self.models})) + "    ],\n];\n")

    # ── manifiesto (ground truth por construcción) ──
    def manifest(self) -> dict:
        entries = []
        role_to_key = {"filter": "filter", "resource": "resources", "relation_resource": "resources", "base_request": "requests", "store_request": "requests",
                       "update_request": "requests", "request_trait": "requests", "service": "service", "controller": "controller", "route": "routes"}
        for ctx in sorted(self.models, key=lambda c: c.class_name.lower()):
            entry: dict = {
                "model": ctx.class_name,
                "path": f"{self.base_dirs(ctx)['model']}/{ctx.class_name}.php",
                "table": ctx.table,
                "soft_delete": self.cfg["soft_delete"],
            }
            by_key: dict[str, list[str]] = {}
            for role, paths in ctx.files.items():
                by_key.setdefault(role_to_key[role], []).extend(paths)
            for key in ("filter", "resources", "requests", "service", "controller", "routes"):
                if key in by_key:
                    entry[key] = sorted(set(by_key[key]))
            for role, paths in sorted(ctx.usado.items()):
                entry[f"{role_to_key[role]}_usado_en"] = sorted(set(paths))
            entry["roles"] = {role: [{"path": p, "via": "manifest"} for p in sorted(set(paths))] for role, paths in sorted(ctx.files.items())}
            entries.append(entry)
        return {"repo": f"repo_{self.idx:02d}", "generator": GENERATOR_VERSION, "axes": self.cfg, "models": entries}


def load_real_names() -> list[str]:
    """Nombres de tabla (sin prefijo) de los repos reales, para mezclarlos con dominios nuevos."""
    names: set[str] = set()
    for f in (STRUCT / "real").glob("*.yaml"):
        try:
            for e in yaml.safe_load(f.read_text(encoding="utf-8")) or []:
                t = str(e.get("table", ""))
                bare = t.split("_", 1)[1] if "_" in t else t
                if 4 <= len(bare) <= 24 and re.fullmatch(r"[a-z_]+", bare):
                    names.add(bare)
        except Exception:  # noqa: BLE001
            continue
    return sorted(names)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--count", type=int, default=30)
    ap.add_argument("--seed", type=int, default=20260923)
    ap.add_argument("--out", default=str(STRUCT / "synthetic"))
    ap.add_argument("--min-models", type=int, default=15)
    ap.add_argument("--max-models", type=int, default=60)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    master = random.Random(args.seed)
    configs = sample_axes(args.count, master)
    real_names = load_real_names()
    index: dict = {
        "generated_at": datetime.now().strftime(NOW_FMT),
        "seed": args.seed,
        "count": args.count,
        "min_models": args.min_models,
        "max_models": args.max_models,
        "generator_version": GENERATOR_VERSION,
        "repos": {},
    }
    total_files = total_models = 0
    for i, cfg in enumerate(configs, start=1):
        rng = random.Random(f"{args.seed}-{i}")
        builder = RepoBuilder(i, cfg, rng, out, args.min_models, args.max_models, real_names)
        manifest = builder.build()
        (builder.root / "manifest.yaml").write_text(
            f"# Ground truth por construcción de {manifest['repo']} (semilla {args.seed}). Etiqueta = lo que el generador escribió.\n"
            + yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True, width=200, default_flow_style=None),
            encoding="utf-8",
        )
        index["repos"][manifest["repo"]] = {"axes": cfg, "models": len(manifest["models"]), "php_files": len(builder.written)}
        total_files += len(builder.written)
        total_models += len(manifest["models"])
        print(f"repo_{i:02d}: {len(manifest['models']):>3} modelos, {len(builder.written):>4} archivos  [{cfg['layout']}, {cfg['language']}, {cfg['requests_dir']}, {cfg['routes_location']}]")
    (out / "_index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n{args.count} repos, {total_models} modelos, {total_files} archivos en {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
