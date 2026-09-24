"""Construye el dataset de ESTRUCTURA: pares (modelo, archivo candidato) con features y etiqueta.

Entrada:
  - repos REALES:      datasets/structure/real/{repo}.yaml (ground truth de scan_backend_structure.py)
                       + el repo en disco (ruta de datasets/structure/repos_manifest.json)
  - repos SINTÉTICOS:  datasets/structure/synthetic/repo_NN/ (manifest.yaml = ground truth por construcción)

Salida (datasets/structure/):
  pairs.parquet                todas las filas (pairs.csv solo con --csv)
  splits.json                  repo -> rol en la evaluación (real_fold / synthetic_train / synthetic_val)
  match_dataset_resource.json  subconjunto `resource` con las 4 features legadas, en el formato exacto
                               de src/generador/_match_dataset.json (X, y, feature_names, stats)
  stats/summary.json           conteos por rol / origen / etiqueta

Fila: repo, origen, modelo, rol, candidato_path, label, via (criterio del ground truth), tipo_negativo,
      + las FEATURES de structure_lib.py.

Etiquetas
  positivo            archivo listado por el ground truth para (modelo, rol)
  negativo duro       archivos del MISMO rol de OTROS modelos del mismo repo, los HARD_NEG más parecidos
                      por nombre normalizado, más los `*_usado_en` (importan el modelo pero no son suyos)
  negativo fácil      1 archivo del mismo rol elegido al azar (semilla fija): sin él, el modelo nunca vería
                      un "esto claramente no es" y sus probabilidades saldrían mal calibradas
Solo se generan filas de un (modelo, rol) si el modelo TIENE al menos un positivo en ese rol: si no lo
tuviera, no se puede distinguir "no existe" de "existe y el scanner no lo vio".
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

import structure_lib as sl  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
STRUCT = REPO_ROOT / "datasets" / "structure"
NOW_FMT = "%d-%m-%Y %H:%M:%S"
HARD_NEG = 4
EASY_NEG = 1
SEED = 20260923
VAL_SYNTHETIC_FRACTION = 0.2  # repos sintéticos reservados como validación (nunca entrenan)


def load_truth(path: Path) -> dict[str, dict[str, set[str]]]:
    """model -> role -> {paths}  (+ '__usado__' role -> {paths}) desde un yaml/manifest."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    entries = data["models"] if isinstance(data, dict) else data
    truth: dict[str, dict[str, set[str]]] = {}
    for e in entries or []:
        roles = {r: {i["path"] for i in items} for r, items in (e.get("roles") or {}).items() if r in sl.ROLES}
        used: dict[str, set[str]] = {}
        for key, role in (("filter_usado_en", "filter"), ("service_usado_en", "service"), ("controller_usado_en", "controller")):
            if e.get(key):
                used[role] = set(e[key])
        via = {i["path"]: i.get("via", "") for items in (e.get("roles") or {}).values() for i in items}
        truth[e["model"]] = {"roles": roles, "used": used, "via": via}  # type: ignore[assignment]
    return truth


def role_consistency(index: sl.RepoIndex, truth: dict) -> tuple[int, int]:
    """(archivos del ground truth, de esos cuántos el scanner clasifica en OTRO rol). En repos
    sintéticos debe dar 0: si no, el generador y el scanner no se ponen de acuerdo."""
    role_of = {f.path: r for r, files in index.files.items() for f in files}
    total = bad = 0
    for t in truth.values():
        for role, paths in t["roles"].items():
            for p in paths:
                total += 1
                bad += int(role_of.get(p) != role)
    return total, bad


def rows_for_repo(name: str, origin: str, root: Path, truth: dict, rng: random.Random) -> tuple[list[dict], sl.RepoIndex]:
    index = sl.scan_repo(root, name)
    rows: list[dict] = []
    for model in index.models:
        t = truth.get(model.class_name)
        if not t:
            continue
        for role in sl.ROLES:
            positives: set[str] = t["roles"].get(role, set())
            if not positives:
                continue
            candidates = index.files[role]
            by_path = {f.path: f for f in candidates}
            pos_files = [by_path[p] for p in positives if p in by_path]
            if not pos_files:
                continue
            others = [f for f in candidates if f.path not in positives]
            # negativos duros: los más parecidos por nombre normalizado
            ranked = sorted(others, key=lambda f: -max((sl._sim(f.norm, n) for n in model.norms), default=0.0))
            hard = ranked[:HARD_NEG]
            used_files = [by_path[p] for p in t["used"].get(role, set()) if p in by_path and p not in positives]
            hard_paths = {f.path for f in hard}
            hard += [f for f in used_files if f.path not in hard_paths]
            easy_pool = [f for f in others if f.path not in {h.path for h in hard}]
            easy = rng.sample(easy_pool, k=min(EASY_NEG, len(easy_pool)))

            def emit(f: sl.FileX, label: int, neg_kind: str) -> None:
                feats = sl.pair_features(index, model, f)
                rows.append(
                    {
                        "repo": name, "origen": origin, "modelo": model.class_name, "rol": role, "candidato_path": f.path,
                        "label": label, "via": t["via"].get(f.path, "") if label else "", "tipo_negativo": neg_kind, **feats,
                    }
                )

            for f in pos_files:
                emit(f, 1, "")
            usado_paths = {f.path for f in used_files}
            for f in hard:
                emit(f, 0, "usado_en" if f.path in usado_paths else "duro")
            for f in easy:
                emit(f, 0, "facil")
    return rows, index


def cleanup_synthetic(syn_dir: Path, out: Path) -> None:
    """Los esqueletos sintéticos son EFÍMEROS: sirven para escanear y sacar features; una vez que las
    filas están en pairs.*, no aportan nada y se regeneran idénticos con la misma semilla. Se conserva
    solo el índice (ejes elegidos por repo + semilla), que documenta cómo se armó cada uno."""
    import shutil

    unexpected = [p.name for p in syn_dir.iterdir() if not (p.name.startswith("repo_") or p.name == "_index.json")]
    if unexpected:  # guarda: solo se borra una carpeta que contiene únicamente lo que generó el generador
        print(f"No borro {syn_dir}: hay contenido ajeno ({unexpected[:3]}).")
        return
    index_file = syn_dir / "_index.json"
    if index_file.exists():
        shutil.copy2(index_file, out / "synthetic_index.json")
    shutil.rmtree(syn_dir)
    print(f"Esqueletos sintéticos borrados ({syn_dir}); conservado: {out / 'synthetic_index.json'}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repos-root", help="carpeta con los repos reales si cambió su ruta (por defecto la del manifiesto)")
    ap.add_argument("--synthetic-dir", default=str(STRUCT / "synthetic"))
    ap.add_argument("--out-dir", default=str(STRUCT))
    ap.add_argument("--csv", action="store_true", help="además del parquet, escribir pairs.csv (pesa ~23 MB)")
    ap.add_argument("--keep-synthetic", action="store_true", help="no borrar los esqueletos sintéticos al terminar (por defecto se borran)")
    args = ap.parse_args()

    out = Path(args.out_dir)
    manifest = json.loads((STRUCT / "repos_manifest.json").read_text(encoding="utf-8"))
    rng = random.Random(SEED)
    all_rows: list[dict] = []
    repo_info: dict[str, dict] = {}

    for name, meta in manifest.items():
        root = Path(args.repos_root) / name if args.repos_root else Path(meta["path"])
        truth = load_truth(STRUCT / "real" / f"{name}.yaml")
        rows, index = rows_for_repo(name, "real", root, truth, rng)
        all_rows += rows
        repo_info[name] = {"origen": "real", "models": len(index.models), "rows": len(rows)}
        print(f"real       {name:<24} {len(index.models):>4} modelos  {len(rows):>6} filas")

    syn_dir = Path(args.synthetic_dir)
    syn_repos = sorted(p for p in syn_dir.glob("repo_*") if (p / "manifest.yaml").exists())
    consistency = {"files": 0, "mismatched": 0}
    for repo in syn_repos:
        truth = load_truth(repo / "manifest.yaml")
        rows, index = rows_for_repo(repo.name, "sintetico", repo, truth, rng)
        n_files, n_bad = role_consistency(index, truth)
        consistency["files"] += n_files
        consistency["mismatched"] += n_bad
        all_rows += rows
        repo_info[repo.name] = {"origen": "sintetico", "models": len(index.models), "rows": len(rows)}
    print(f"sintetico  {len(syn_repos)} repos  {sum(1 for r in all_rows if r['origen'] == 'sintetico'):>6} filas")

    df = pd.DataFrame(all_rows)
    df["label"] = df["label"].astype(int)

    # splits por REPO (nunca por fila): real -> fold de leave-one-real-repo-out; sintético -> train / val
    syn_names = [p.name for p in syn_repos]
    split_rng = random.Random(SEED)
    val = set(split_rng.sample(syn_names, k=max(1, round(len(syn_names) * VAL_SYNTHETIC_FRACTION)))) if syn_names else set()
    splits = {
        "protocol": "leave-one-real-repo-out: en cada fold se prueba en UN repo real no visto y se entrena con los demás reales (+ sintéticos train)",
        "real_folds": {name: {"test": name, "train_real": [n for n in manifest if n != name]} for name in manifest},
        "synthetic_train": [n for n in syn_names if n not in val],
        "synthetic_val": sorted(val),
        "note": "Los sintéticos NUNCA se usan como test principal: evaluar sobre ellos mediría al generador, no a los proyectos.",
        "seed": SEED,
    }
    (out / "splits.json").write_text(json.dumps(splits, indent=2, ensure_ascii=False), encoding="utf-8")
    df["split_hint"] = df["repo"].map(lambda r: "real" if r in manifest else ("synthetic_val" if r in val else "synthetic_train"))

    out.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out / "pairs.parquet", index=False)
    if args.csv:  # 23 MB de texto que duplican al parquet: solo si se pide
        df.to_csv(out / "pairs.csv", index=False, float_format="%.5f")

    # subconjunto compatible con src/generador/_match_dataset.json (solo `resource`, 4 features legadas)
    res = df[df["rol"] == "resource"]
    compat = {
        "X": res[list(sl.LEGACY_FEATURES)].values.tolist(),
        "y": res["label"].tolist(),
        "feature_names": list(sl.LEGACY_FEATURES),
        "stats": {"projects": int(res["repo"].nunique()), "models": int(res["modelo"].nunique()), "positives": int(res["label"].sum()), "hard_negatives": int((res["label"] == 0).sum())},
    }
    (out / "match_dataset_resource.json").write_text(json.dumps(compat, indent=2), encoding="utf-8")

    stats_dir = out / "stats"
    stats_dir.mkdir(exist_ok=True)
    summary = {
        "generated_at": datetime.now().strftime(NOW_FMT),
        "rows": len(df),
        "positives": int(df["label"].sum()),
        "negatives": int((df["label"] == 0).sum()),
        "by_origin": {k: int(v) for k, v in df["origen"].value_counts().items()},
        "by_role": {k: int(v) for k, v in df["rol"].value_counts().items()},
        "by_split": {k: int(v) for k, v in df["split_hint"].value_counts().items()},
        "by_negative_kind": {k: int(v) for k, v in df[df["label"] == 0]["tipo_negativo"].value_counts().items()},
        "by_via": {k: int(v) for k, v in df[df["label"] == 1]["via"].value_counts().items()},
        "repos": repo_info,
        "features": list(sl.FEATURES),
        "synthetic_role_consistency": consistency,
    }
    (stats_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"consistencia generador<->scanner (sintéticos): {consistency['files'] - consistency['mismatched']}/{consistency['files']} archivos en el rol esperado")

    if not args.keep_synthetic and syn_repos:
        cleanup_synthetic(syn_dir, out)
    print(f"\n{len(df)} filas: {summary['positives']} positivas / {summary['negatives']} negativas -> {out}")
    print("por rol:", summary["by_role"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
