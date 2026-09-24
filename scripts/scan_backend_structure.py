"""Escanea un backend Laravel y escribe el mapeo modelo -> archivos (ground truth).

Reescribe, como script versionado, el scanner temporal que produjo los anexos
YAML de docs/dataset/estructura-siaw.md y estructura-sireh.md (esa herramienta
no quedó en el repo). Solo LEE el repo escaneado: no lo modifica.

Uso:
    python scripts/scan_backend_structure.py --repo <ruta> [--repo <ruta2> ...]
        [--name <nombre>] [--out-dir datasets/structure/real]
    python scripts/scan_backend_structure.py --repo <ruta> --compare-annex docs/dataset/estructura-siaw.md

Salida por repo (`{out-dir}/{nombre}.yaml`): una lista de modelos con el MISMO
formato que los anexos (`filter`, `resources`, `requests`, `service`,
`controller`, `routes`, `*_usado_en`) más `roles:`, que separa cada archivo por
rol y guarda el CRITERIO con el que se le asignó dueño (`via`):

    declared         el modelo lo declara ($default_filters)
    name_exact       nombre normalizado idéntico
    name_stem        idéntico salvo singular/plural
    name_prefix      el nombre del archivo empieza por el del modelo (prefijo más largo gana)
    folder           vive en una carpeta `{tabla}/`
    route_controller (rutas) importa un controller que es del modelo
    import_single    importa exactamente un modelo (señal secundaria, solo si nada anterior aplicó)

y `{out-dir}/../repos_manifest.json` (nombre, ruta, commit, versiones, conexiones).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

import structure_lib as sl  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "datasets" / "structure" / "real"
NOW_FMT = "%d-%m-%Y %H:%M:%S"

_ROLE_TO_ANNEX_KEY = {
    "filter": "filter",
    "resource": "resources",
    "relation_resource": "resources",
    "base_request": "requests",
    "store_request": "requests",
    "update_request": "requests",
    "request_trait": "requests",
    "other_request": "requests",
    "service": "service",
    "controller": "controller",
    "route": "routes",
}


def _git(repo: Path, *args: str) -> str:
    try:
        out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=30)
        return out.stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def _config_connections(text: str) -> list[str]:
    """Claves de primer nivel del array `connections` de config/database.php
    (balanceando corchetes, sin depender de la indentación)."""
    m = re.search(r"['\"]connections['\"]\s*=>\s*\[", text)
    if not m:
        return []
    depth, i, names = 1, m.end(), []
    while i < len(text) and depth:
        c = text[i]
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
        elif c in "'\"" and depth == 1:
            j = text.find(c, i + 1)
            key = text[i + 1 : j]
            if re.match(r"\s*=>\s*\[", text[j + 1 : j + 12]):
                names.append(key)
            i = j
        i += 1
    # si un `[` dentro de un comentario/expresión desbalancea el conteo, el escaneo se
    # "escapa" del bloque: `options` (opción de PDO) nunca es una conexión de primer nivel
    if "options" in names:
        names = names[: names.index("options")]
    return names


def repo_meta(repo: Path, name: str, n_models: int) -> dict:
    composer = {}
    try:
        composer = json.loads((repo / "composer.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    require = composer.get("require", {})
    connections: list[str] = []
    db_cfg = repo / "config" / "database.php"
    if db_cfg.exists():
        text = db_cfg.read_text(encoding="utf-8", errors="ignore")
        connections = _config_connections(text)
    return {
        "name": name,
        "path": str(repo.resolve()),
        "commit": _git(repo, "rev-parse", "--short", "HEAD"),
        "branch": _git(repo, "branch", "--show-current"),
        "dirty_files": len([l for l in _git(repo, "status", "--porcelain").splitlines() if l.strip()]),
        "laravel": require.get("laravel/framework", ""),
        "php": require.get("php", ""),
        "connections": connections,
        "models": n_models,
        "scanned_at": datetime.now().strftime(NOW_FMT),
    }


def build_manifest(index: sl.RepoIndex) -> list[dict]:
    owners = sl.assign_owners(index)
    usado = sl.usado_en(index, owners)
    entries: list[dict] = []
    for m in sorted(index.models, key=lambda x: x.class_name.lower()):
        entry: dict = {
            "model": m.class_name,
            "path": m.path,
            "connection": m.connection,
            "table": m.table,
            "pk": m.pk,
            "soft_delete": m.soft_delete,
            "has_factory": m.has_factory,
            "auditoria": m.auditoria,
        }
        if m.default_filters:
            entry["default_filters"] = m.default_filters
        if m.relaciones:
            entry["relaciones"] = m.relaciones
        roles = owners[m.class_name]
        by_key: dict[str, list[str]] = {}
        for role, items in roles.items():
            by_key.setdefault(_ROLE_TO_ANNEX_KEY[role], []).extend(p for p, _ in items)
        for key in ("filter", "resources", "requests", "service", "controller", "routes"):
            if key in by_key:
                entry[key] = sorted(set(by_key[key]))
        used_by_key: dict[str, list[str]] = {}
        for role, paths in usado[m.class_name].items():
            key = _ROLE_TO_ANNEX_KEY[role]
            used_by_key.setdefault(key, []).extend(paths)
        for key, paths in sorted(used_by_key.items()):
            entry[f"{key}_usado_en"] = sorted(set(paths))
        entry["roles"] = {
            role: [{"path": p, "via": via} for p, via in sorted(items)] for role, items in sorted(roles.items()) if items
        }
        entries.append(entry)
    return entries


def write_yaml(path: Path, entries: list[dict], header: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(entries, sort_keys=False, allow_unicode=True, width=200, default_flow_style=None)
    path.write_text(header + body, encoding="utf-8")


def load_annex(md_path: Path) -> list[dict]:
    text = md_path.read_text(encoding="utf-8")
    tail = text.split("## Anexo", 1)[-1]
    m = re.search(r"```yaml\n(.*?)\n```", tail, re.S)
    if not m:
        raise SystemExit(f"No encontré el bloque ```yaml del anexo en {md_path}")
    return yaml.safe_load(m.group(1))


def compare(scan: list[dict], annex: list[dict]) -> str:
    by_scan = {e["model"]: e for e in scan}
    by_annex = {e["model"]: e for e in annex}
    common = sorted(set(by_scan) & set(by_annex))
    lines = [
        f"Modelos: escaneo={len(by_scan)}  anexo={len(by_annex)}  en común={len(common)}",
        f"  solo en anexo ({len(set(by_annex) - set(by_scan))}): {sorted(set(by_annex) - set(by_scan))[:8]}",
        f"  solo en escaneo ({len(set(by_scan) - set(by_annex))}): {sorted(set(by_scan) - set(by_annex))[:8]}",
        "",
        f"{'campo':<12}{'TP':>6}{'FP':>6}{'FN':>6}{'precision':>11}{'recall':>9}{'modelos idénticos':>20}",
    ]
    for key in ("filter", "resources", "requests", "service", "controller", "routes"):
        tp = fp = fn = same = 0
        for name in common:
            a = set(by_annex[name].get(key) or [])
            s = set(by_scan[name].get(key) or [])
            tp += len(a & s)
            fp += len(s - a)
            fn += len(a - s)
            same += int(a == s)
        prec = tp / (tp + fp) if tp + fp else 1.0
        rec = tp / (tp + fn) if tp + fn else 1.0
        lines.append(f"{key:<12}{tp:>6}{fp:>6}{fn:>6}{prec:>11.3f}{rec:>9.3f}{f'{same}/{len(common)}':>20}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", action="append", required=True, help="raíz del backend Laravel (repetible)")
    ap.add_argument("--name", help="nombre (solo con un --repo); por defecto, el de la carpeta")
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT))
    ap.add_argument("--compare-annex", help="anexo .md contra el cual comparar (no escribe salida)")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    manifest_path = out_dir.parent / "repos_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}

    for repo_arg in args.repo:
        repo = Path(repo_arg)
        if not (repo / "app").is_dir():
            print(f"No parece un backend Laravel (falta app/): {repo}")
            return 1
        name = args.name if args.name and len(args.repo) == 1 else repo.name
        index = sl.scan_repo(repo, name=name)
        entries = build_manifest(index)
        print(f"{name}: {len(index.models)} modelos, archivos por rol: " + ", ".join(f"{r}={len(v)}" for r, v in index.files.items()))

        if args.compare_annex:
            print(compare(entries, load_annex(Path(args.compare_annex))))
            continue

        meta = repo_meta(repo, name, len(index.models))
        meta["prefixes"] = index.prefixes
        meta["files_by_role"] = {r: len(v) for r, v in index.files.items()}
        manifest[name] = meta
        header = (
            f"# Ground truth de {name} -- generado por scripts/scan_backend_structure.py\n"
            f"# commit {meta['commit']} ({meta['branch']}), {meta['scanned_at']}. Formato: ver docs del script.\n"
        )
        write_yaml(out_dir / f"{name}.yaml", entries, header)
        print(f"  -> {out_dir / (name + '.yaml')}")

    if not args.compare_annex:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Manifiesto de repos: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
