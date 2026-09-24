"""Perfil de variaciones entre proyectos (Paso 3 del prompt de dataset).

Mide, sobre los repos REALES escaneados, cuánto varían las convenciones de
estructura -- esa variación es justamente la señal de entrenamiento. Por cada
eje guarda los valores observados, en qué repos aparece cada uno y su
frecuencia. El generador de repos sintéticos (generate_synthetic_repos.py) lo
lee para muestrear con frecuencias reales.

Uso:
    python scripts/build_variation_profile.py [--repos-root ..]

Lee `datasets/structure/repos_manifest.json` y `datasets/structure/real/*.yaml`
(los produce scan_backend_structure.py). Escribe
`datasets/structure/variation_profile.json`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import structure_lib as sl  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "datasets" / "structure"
NOW_FMT = "%d-%m-%Y %H:%M:%S"


def _studly(s: str) -> str:
    return "".join(p.capitalize() for p in re.split(r"[_\W]+", s) if p)


def _strip_prefix_literal(table: str, prefixes: list[str]) -> str:
    for p in prefixes:
        if table.lower().startswith(p.lower() + "_"):
            return table[len(p) + 1 :]
    return table


def detect_axes(index: sl.RepoIndex) -> dict[str, str | dict[str, float]]:
    """Valor (o distribución) de cada eje para UN repo."""
    owners = sl.assign_owners(index)
    models = {m.class_name: m for m in index.models}
    axes: dict[str, object] = {}

    # carpeta de Requests: Request | Requests
    req_roots = Counter(f.root_path.rsplit("/", 1)[-1] for r in ("store_request", "update_request", "base_request") for f in index.files[r])
    axes["requests_dir"] = req_roots.most_common(1)[0][0] if req_roots else "ninguno"

    # sub-nivel bajo cada raíz: conexión / sistema / ninguno
    conn_tails = {re.sub(r"^(mysql_|db)", "", (m.connection or "")).lower() for m in index.models} - {""}
    conn_tails |= {(m.connection or "").lower() for m in index.models} - {""}
    subs: list[str] = []
    for r in ("filter", "resource", "store_request", "service"):
        subs += [f.subfolder for f in index.files[r]]
    if subs:
        empty = sum(1 for s in subs if not s) / len(subs)
        conn_hit = sum(1 for s in subs if s and (s.lower() in conn_tails or re.sub(r"^db", "", s.lower()) in conn_tails)) / len(subs)
        axes["sublevel"] = "ninguno" if empty > 0.6 else ("conexion" if conn_hit > 0.4 else "sistema")
    else:
        axes["sublevel"] = "ninguno"

    # carpeta por tabla en Requests / Resources
    def per_table_share(roles: tuple[str, ...]) -> float:
        files = [f for r in roles for f in index.files[r]]
        if not files:
            return 0.0
        hit = 0
        for f in files:
            segs = {sl.strip_prefix(sl.norm_raw(x), index.prefixes) for x in f.folders if x.lower() not in sl._GENERIC_FOLDERS}
            if any(sl.strip_prefix(sl.norm_raw(m.table), index.prefixes) in segs or sl.norm_raw(m.class_name) in segs for m in index.models):
                hit += 1
        return hit / len(files)

    axes["per_table_folder_requests"] = "si" if per_table_share(("store_request", "update_request")) > 0.3 else "no"
    axes["per_table_folder_resources"] = "si" if per_table_share(("resource",)) > 0.3 else "no"

    # traits de validación
    traits = index.files["request_trait"]
    if not traits:
        axes["request_traits"] = "ninguno"
    else:
        with_table = per_table_share(("request_trait",)) > 0.3
        axes["request_traits"] = "Traits/{tabla}/Validates{X}" if with_table else "Traits/Validates{X} plano"

    # nombre del Service / del Request (contra la tabla del dueño)
    def naming_style(role: str, strip: str) -> str:
        c: Counter[str] = Counter()
        for cls, roles in owners.items():
            m = models[cls]
            for path, via in roles.get(role, []):
                if via.startswith("import") or via == "folder":
                    continue
                stem_name = Path(path).stem
                base = re.sub(strip, "", stem_name)
                base = re.sub(r"^(Store|Update|Base|Bulk)", "", base) if role != "service" else base
                bare = _strip_prefix_literal(m.table, index.prefixes)
                if base == "":
                    c["accion_en_carpeta"] += 1
                elif base.lower() == m.table.lower() and "_" in base:
                    c["{tabla}"] += 1
                elif base == m.class_name:
                    c["{ClaseModelo}"] += 1
                elif sl.norm_raw(base) == sl.norm_raw(m.table):
                    c["{CamelConPrefijo}"] += 1
                elif sl.norm_raw(base) == sl.norm_raw(bare):
                    c["{CamelSinPrefijo}"] += 1
                else:
                    c["otro"] += 1
        return c.most_common(1)[0][0] if c else "ninguno"

    axes["service_name"] = naming_style("service", r"Service$")
    axes["request_name"] = naming_style("store_request", r"Request$")
    axes["base_request"] = "clase Base abstracta" if index.files["base_request"] else "sin base"

    # sufijo del Resource mínimo
    suf: Counter[str] = Counter()
    for f in index.files["relation_resource"]:
        m = re.match(rf"^.+?({sl._RELATION_STYLE_SUFFIX})Resource$", f.class_name)
        if m:
            suf[m.group(1)] += 1
    axes["min_resource_suffix"] = suf.most_common(1)[0][0] if suf else "ninguno"
    axes["min_resource_suffix_dist"] = dict(suf)

    # rutas
    route_files = [f for f in index.files["route"]]
    kinds: Counter[str] = Counter()
    for f in route_files:
        parts = f.path.split("/")
        if f.path == "routes/api.php" or parts[-1] == "api.php":
            kinds["en línea en api.php"] += 1
        elif "modules" in parts:
            kinds["routes/modules/{tabla}.php"] += 1
        elif len(parts) > 2 and parts[1] == "api":
            kinds["routes/api/{modulo}.php"] += 1
        else:
            kinds["routes/{tabla}.php"] += 1
    routes_main = [k for k, _ in kinds.most_common() if k != "en línea en api.php"]
    axes["routes_location"] = routes_main[0] if routes_main else "en línea en api.php"
    axes["routes_location_dist"] = dict(kinds)

    reg: list[str] = []
    rsp = index.root / "app" / "Providers" / "RouteServiceProvider.php"
    if rsp.exists() and "base_path" in rsp.read_text(encoding="utf-8", errors="ignore"):
        reg.append("RouteServiceProvider")
    boot = index.root / "bootstrap" / "app.php"
    if boot.exists() and "withRouting" in boot.read_text(encoding="utf-8", errors="ignore"):
        reg.append("bootstrap/app.php")
    for cand in (index.root / "routes" / "api.php", index.root / "routes" / "api" / "api.php"):
        if cand.exists() and re.search(r"require|glob\(|base_path\(", cand.read_text(encoding="utf-8", errors="ignore")):
            reg.append("require en api.php")
            break
    axes["route_registration"] = "+".join(sorted(set(reg))) if reg else "ninguno"

    # controllers
    depth: Counter[str] = Counter()
    for f in index.files["controller"]:
        segs = [s for s in f.folders]
        after = segs[segs.index("Controllers") + 1 :] if "Controllers" in segs else []
        if any(s.lower() in ("v1", "v2") for s in after):
            depth["Api/V1"] += 1
        elif len(after) >= 2:
            depth["Api/{sub}"] += 1
        else:
            depth["Api raíz"] += 1
    axes["controllers_dir"] = depth.most_common(1)[0][0] if depth else "ninguno"

    # middleware de token
    mw: Counter[str] = Counter()
    for f in route_files:
        text = (index.root / f.path).read_text(encoding="utf-8", errors="ignore")
        if "[ApiToken::class]" in text or "ApiToken::class" in text:
            mw["[ApiToken::class]"] += 1
        if re.search(r"middleware\(\s*'ApiToken'", text):
            mw["'ApiToken'"] += 1
        if "ValidateSessionKey" in text or "session.key" in text:
            mw["ValidateSessionKey"] += 1
        if "auth:sanctum" in text:
            mw["auth:sanctum"] += 1
    axes["token_middleware"] = mw.most_common(1)[0][0] if mw else "ninguno"

    # relación de auditoría y modelo de usuario
    aud: Counter[str] = Counter()
    for m in index.models:
        for rel in m.relaciones:
            (alias,) = rel.keys()
            if alias in ("created_by", "createdBy", "create_by"):
                aud[alias] += 1
    axes["audit_relation"] = aud.most_common(1)[0][0] if aud else "ausente"
    user_names = {m.class_name for m in index.models if re.fullmatch(r"(?i)(user|users|usuario|usuarios|catalogo_usuario|siaw_usuarios)", m.class_name)}
    axes["user_model"] = sorted(user_names)[0] if user_names else "ninguno"

    # soft delete / PK / estilo de nombre de clase
    sd = Counter(m.soft_delete for m in index.models)
    axes["soft_delete"] = sd.most_common(1)[0][0] if sd else "no"

    def pk_kind(m: sl.ModelX) -> str:
        if m.pk["name"] == "pkid":
            return "pkid int"
        if m.pk["name"] not in ("id",):
            return "natural"
        if m.pk["incrementing"] is False or m.pk["keyType"] == "string":
            return "id uuid string"
        return "id auto"

    pk = Counter(pk_kind(m) for m in index.models)
    axes["pk"] = pk.most_common(1)[0][0] if pk else "id auto"

    style: Counter[str] = Counter()
    for m in index.models:
        if "_" in m.class_name and m.class_name == m.class_name.lower():
            style["snake literal"] += 1
        elif "_" not in m.class_name and m.class_name[:1].isupper():
            style["StudlyCase"] += 1
        else:
            style["mixto"] += 1
    axes["class_style"] = style.most_common(1)[0][0] if style else "StudlyCase"
    return axes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repos-root", help="carpeta donde están los repos reales si cambió su ruta (por defecto, la del manifiesto)")
    args = ap.parse_args()

    manifest = json.loads((OUT_DIR / "repos_manifest.json").read_text(encoding="utf-8"))
    per_repo: dict[str, dict] = {}
    for name, meta in manifest.items():
        path = Path(args.repos_root) / name if args.repos_root else Path(meta["path"])
        if not path.is_dir():
            print(f"Falta el repo {name} en {path}")
            return 1
        per_repo[name] = detect_axes(sl.scan_repo(path, name))
        print(f"{name}: " + ", ".join(f"{k}={v}" for k, v in per_repo[name].items() if not k.endswith("_dist")))

    axes: dict[str, dict] = {}
    for repo, values in per_repo.items():
        for axis, value in values.items():
            if axis.endswith("_dist"):
                continue
            axes.setdefault(axis, {"values": defaultdict(list)})["values"][str(value)].append(repo)
    n = len(per_repo)
    profile = {
        "generated_at": datetime.now().strftime(NOW_FMT),
        "repos": list(per_repo),
        "n_repos": n,
        "axes": {
            axis: {
                "values": {
                    v: {"repos": repos, "count": len(repos), "share": round(len(repos) / n, 3)}
                    for v, repos in sorted(spec["values"].items(), key=lambda kv: -len(kv[1]))
                }
            }
            for axis, spec in axes.items()
        },
        "per_repo": per_repo,
        "note": (
            "Cada repo aporta UN valor por eje (el modal). `share` = fracción de los repos reales que lo usan. "
            "El generador sintético muestrea con estas frecuencias y garantiza cobertura de todos los valores."
        ),
    }
    out = OUT_DIR / "variation_profile.json"
    out.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nPerfil guardado en {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
