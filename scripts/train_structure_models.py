"""Entrenamiento y evaluación HONESTA del modelo de estructura (Paso 7 del prompt).

Protocolo
  - Split POR REPO, nunca por fila. Prueba = un repo REAL no visto (leave-one-real-repo-out sobre los 5).
  - En cada fold se compara, sobre el repo real de prueba:
      (1) heurística actual (`_heuristic_score` de match_learner.py, 4 features legadas)
      (2) modelo de fábrica actual (.joblib empaquetado, 4 features)  -- OJO: se entrenó con los 5 repos
          reales, así que para ESTE experimento no es held-out: se muestra como referencia, no como rival justo
      (3) modelo nuevo entrenado solo con repos reales (los otros 4)
      (4) modelo nuevo entrenado con reales + sintéticos de entrenamiento
      (3s)/(4s) "soft": igual que (3)/(4) pero SIN las features que replican el criterio con que se etiquetan
          los repos reales (carpeta {tabla}/, import, $default_filters, controller de la ruta). Mide cuánto del
          resultado depende de haber visto la regla de etiquetado.
  - La evaluación usa TODOS los candidatos del rol (no solo la muestra de negativos): top-1 = ¿el candidato
    mejor puntuado es un positivo?  Precision/recall/F1 con umbral 0.5 sobre todos los pares.
  - Diagnóstico aparte: (4) sobre los repos sintéticos de validación (solo con los pares del dataset, porque
    los esqueletos se borran). NO es un resultado principal: evaluar sobre sintéticos mide al generador.

Salida: datasets/structure/stats/results.json y results.md, y los modelos finales en
datasets/structure/models/ (con versión y fecha en el nombre). NO toca
src/generador/_match_dataset.json ni model_resource_matcher_pretrained.joblib.

Uso:  python scripts/train_structure_models.py [--seeds 3] [--repos-root <dir>]
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))

import structure_lib as sl  # noqa: E402
from build_structure_dataset import load_truth  # noqa: E402
from generador import match_learner  # noqa: E402

warnings.filterwarnings("ignore")

REPO_ROOT = Path(__file__).resolve().parent.parent
STRUCT = REPO_ROOT / "datasets" / "structure"
NOW_FMT = "%d-%m-%Y %H:%M:%S"
ALL = list(sl.FEATURES)
SOFT = [f for f in sl.FEATURES if f not in sl.DIRECT_SIGNAL_FEATURES]
LEGACY = list(sl.LEGACY_FEATURES)
# Criterios de etiquetado que equivalen a "el nombre normalizado es idéntico": ahí una regla de nombres
# ya resuelve el caso. Los grupos SIN ninguno de estos son donde el modelo tiene que aportar algo más.
EXACT_NAME_VIA = {"name_exact_full", "name_exact"}


# ─────────────────────────────── modelos ────────────────────────────────


def fit_mlp(X: np.ndarray, y: np.ndarray, seed: int):
    model = make_pipeline(
        StandardScaler(),
        MLPClassifier(hidden_layer_sizes=(32, 16), alpha=1e-4, max_iter=300, early_stopping=True, n_iter_no_change=10, random_state=seed),
    )
    model.fit(X, y)
    return model


def score_heuristic(X4: np.ndarray) -> np.ndarray:
    z = match_learner._HEURISTIC_BIAS + X4 @ np.array(match_learner._HEURISTIC_WEIGHTS)
    return 1.0 / (1.0 + np.exp(-np.clip(z, -60, 60)))


def score_factory(X4: np.ndarray) -> np.ndarray:
    payload = joblib.load(match_learner.bundled_pretrained_path())
    return payload["model"].predict_proba(X4)[:, 1]


# ─────────────────────────────── métricas ───────────────────────────────


def group_metrics(scores: np.ndarray, y: np.ndarray, group: np.ndarray, role: np.ndarray, rng: np.random.Generator) -> dict:
    """top-1 / top-3 por (modelo, rol) y precision/recall/F1 (umbral 0.5) sobre todos los pares."""
    jitter = rng.random(len(scores)) * 1e-9  # desempate reproducible: sin él, un puntaje constante "acierta" por orden de lista
    s = scores + jitter
    order = np.lexsort((-s, group))  # por grupo, de mayor a menor puntaje
    g_sorted, y_sorted, r_sorted = group[order], y[order], role[order]
    boundaries = np.flatnonzero(np.r_[True, g_sorted[1:] != g_sorted[:-1]])
    ends = np.r_[boundaries[1:], len(g_sorted)]
    per_role: dict[str, dict[str, list[int]]] = {}
    for b, e in zip(boundaries, ends):
        r = r_sorted[b]
        d = per_role.setdefault(r, {"top1": [], "top3": []})
        d["top1"].append(int(y_sorted[b] == 1))
        d["top3"].append(int(y_sorted[b : min(b + 3, e)].sum() > 0))
    pred = scores >= 0.5
    out: dict = {"by_role": {}}
    for r, d in per_role.items():
        m = role == r
        tp = int((pred[m] & (y[m] == 1)).sum())
        fp = int((pred[m] & (y[m] == 0)).sum())
        fn = int((~pred[m] & (y[m] == 1)).sum())
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        out["by_role"][r] = {
            "groups": len(d["top1"]),
            "top1": float(np.mean(d["top1"])),
            "top3": float(np.mean(d["top3"])),
            "precision": prec,
            "recall": rec,
            "f1": 2 * prec * rec / (prec + rec) if prec + rec else 0.0,
        }
    all1 = [v for d in per_role.values() for v in d["top1"]]
    all3 = [v for d in per_role.values() for v in d["top3"]]
    out["overall"] = {"groups": len(all1), "top1": float(np.mean(all1)) if all1 else 0.0, "top3": float(np.mean(all3)) if all3 else 0.0}
    return out


# ─────────────────────────────── datos de evaluación ────────────────────


def full_candidate_sets(name: str, root: Path) -> pd.DataFrame:
    """Todos los pares (modelo, candidato del mismo rol) de un repo real, para los modelos que tienen
    al menos un positivo en ese rol. Es el eval sin muestreo de negativos."""
    truth = load_truth(STRUCT / "real" / f"{name}.yaml")
    index = sl.scan_repo(root, name)
    rows: list[dict] = []
    for model in index.models:
        t = truth.get(model.class_name)
        if not t:
            continue
        for role in sl.ROLES:
            positives = t["roles"].get(role, set())
            if not positives or not any(f.path in positives for f in index.files[role]):
                continue
            exact_by_name = any(t["via"].get(p, "") in EXACT_NAME_VIA for p in positives)
            for f in index.files[role]:
                feats = sl.pair_features(index, model, f)
                rows.append(
                    {
                        "repo": name, "grupo": f"{model.class_name}|{role}", "rol": role, "label": int(f.path in positives),
                        "sin_nombre_exacto": not exact_by_name, **feats,
                    }
                )
    return pd.DataFrame(rows)


# ─────────────────────────────── main ───────────────────────────────────


def both(scores: np.ndarray, y: np.ndarray, group: np.ndarray, role: np.ndarray, hard: np.ndarray, rng: np.random.Generator) -> dict:
    """Métricas sobre todo el repo y sobre el subconjunto de grupos SIN nombre exacto."""
    out = group_metrics(scores, y, group, role, rng)
    out["hard"] = group_metrics(scores[hard], y[hard], group[hard], role[hard], rng) if hard.any() else None
    return out


def mean_metrics(runs: list[dict]) -> dict:
    """Promedia una lista de resultados (semillas) de group_metrics."""
    roles = runs[0]["by_role"].keys()
    out = {"overall": {k: float(np.mean([r["overall"][k] for r in runs])) for k in ("top1", "top3")}, "by_role": {}}
    out["overall"]["top1_std"] = float(np.std([r["overall"]["top1"] for r in runs]))
    hard_runs = [r["hard"] for r in runs if r.get("hard")]
    out["hard"] = None
    if hard_runs:
        out["hard"] = {"overall": {k: float(np.mean([h["overall"][k] for h in hard_runs])) for k in ("top1", "top3", "groups")},
                       "by_role": {role: {k: float(np.mean([h["by_role"][role][k] for h in hard_runs])) for k in ("top1", "top3")} | {"groups": hard_runs[0]["by_role"][role]["groups"]}
                                   for role in hard_runs[0]["by_role"]}}
    for role in roles:
        out["by_role"][role] = {k: float(np.mean([r["by_role"][role][k] for r in runs])) for k in ("top1", "top3", "precision", "recall", "f1")}
        out["by_role"][role]["groups"] = runs[0]["by_role"][role]["groups"]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--repos-root")
    args = ap.parse_args()

    manifest = json.loads((STRUCT / "repos_manifest.json").read_text(encoding="utf-8"))
    splits = json.loads((STRUCT / "splits.json").read_text(encoding="utf-8"))
    pairs = pd.read_parquet(STRUCT / "pairs.parquet")
    real_names = list(manifest)
    syn_train = pairs[pairs["repo"].isin(splits["synthetic_train"])]
    syn_val = pairs[pairs["repo"].isin(splits["synthetic_val"])]
    rng = np.random.default_rng(0)

    print("Calculando candidatos completos de los repos reales...")
    evals = {n: full_candidate_sets(n, Path(args.repos_root) / n if args.repos_root else Path(manifest[n]["path"])) for n in real_names}
    for n, df in evals.items():
        print(f"  {n:<24} {len(df):>7} pares, {df['grupo'].nunique():>5} grupos (modelo,rol)")

    def mats(df: pd.DataFrame, cols: list[str]) -> tuple[np.ndarray, np.ndarray]:
        return df[cols].to_numpy(dtype=float), df["label"].to_numpy(dtype=int)

    variants = {
        "3_real": (ALL, False, args.seeds),
        "4_real+sinteticos": (ALL, True, args.seeds),
        "3s_real_soft": (SOFT, False, 1),
        "4s_real+sinteticos_soft": (SOFT, True, 1),
    }
    results: dict[str, dict] = {"1_heuristica": {}, "2_fabrica_no_heldout": {}, **{k: {} for k in variants}}

    for test_name in real_names:
        ev = evals[test_name]
        group = pd.factorize(ev["grupo"])[0]
        role = ev["rol"].to_numpy()
        X4, y = mats(ev, LEGACY)
        hard = ev["sin_nombre_exacto"].to_numpy(dtype=bool)
        results["1_heuristica"][test_name] = both(score_heuristic(X4), y, group, role, hard, rng)
        results["2_fabrica_no_heldout"][test_name] = both(score_factory(X4), y, group, role, hard, rng)

        train_real = pairs[(pairs["repo"].isin(real_names)) & (pairs["repo"] != test_name)]
        for vname, (cols, with_syn, n_seeds) in variants.items():
            train = pd.concat([train_real, syn_train]) if with_syn else train_real
            Xtr, ytr = mats(train, cols)
            Xev, yev = mats(ev, cols)
            runs = [both(fit_mlp(Xtr, ytr, seed).predict_proba(Xev)[:, 1], yev, group, role, hard, rng) for seed in range(n_seeds)]
            results[vname][test_name] = mean_metrics(runs)
        line = " | ".join(f"{k.split('_')[0]}:{results[k][test_name]['overall']['top1']:.3f}" for k in results)
        hline = " | ".join(f"{k.split('_')[0]}:{(results[k][test_name].get('hard') or {'overall': {'top1': float('nan')}})['overall']['top1']:.3f}" for k in results)
        print(f"fold test={test_name:<24} top-1 todo -> {line}", flush=True)
        print(f"{'':<34} top-1 SIN nombre exacto -> {hline}", flush=True)

    # diagnóstico sobre sintéticos de validación (solo con los pares del dataset)
    Xtr, ytr = mats(pd.concat([pairs[pairs["repo"].isin(real_names)], syn_train]), ALL)
    diag_model = fit_mlp(Xtr, ytr, 0)
    Xv, yv = mats(syn_val, ALL)
    gv = pd.factorize(syn_val["repo"] + "|" + syn_val["modelo"] + "|" + syn_val["rol"])[0]
    rv = syn_val["rol"].to_numpy()
    diagnostic = {
        "nota": "Sobre pares muestreados (positivos + negativos duros/fáciles) de repos SINTÉTICOS de validación. Diagnóstico, NO resultado principal.",
        "modelo_4": group_metrics(diag_model.predict_proba(Xv)[:, 1], yv, gv, rv, rng),
        "heuristica": group_metrics(score_heuristic(syn_val[LEGACY].to_numpy(dtype=float)), yv, gv, rv, rng),
    }

    # modelos finales (todos los reales) -- NO reemplazan al de fábrica
    models_dir = STRUCT / "models"
    models_dir.mkdir(exist_ok=True)
    try:
        from generador import __version__ as app_version
    except Exception:  # noqa: BLE001
        app_version = "desconocida"
    stamp = datetime.now().strftime("%Y-%m-%d")
    saved = []
    for vname, cols, with_syn in (("real_only", ALL, False), ("real_plus_synthetic", ALL, True)):
        train = pd.concat([pairs[pairs["repo"].isin(real_names)], syn_train]) if with_syn else pairs[pairs["repo"].isin(real_names)]
        Xa, ya = mats(train, cols)
        path = models_dir / f"structure_matcher_{vname}_v1_{stamp}.joblib"
        joblib.dump({"pipeline": fit_mlp(Xa, ya, 0), "feature_names": cols, "trained_on": {"real": real_names, "synthetic": with_syn}, "serviceforge_version": app_version, "trained_at": datetime.now().strftime(NOW_FMT), "rows": int(len(train))}, path)
        saved.append(path.name)

    payload = {
        "generated_at": datetime.now().strftime(NOW_FMT),
        "serviceforge_version": app_version,
        "protocol": "leave-one-real-repo-out sobre 5 repos reales; test sobre todos los candidatos del rol",
        "seeds": args.seeds,
        "features_all": ALL,
        "features_soft": SOFT,
        "results": results,
        "diagnostic_synthetic_val": diagnostic,
        "models_saved": saved,
    }
    (STRUCT / "stats").mkdir(exist_ok=True)
    (STRUCT / "stats" / "results.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (STRUCT / "stats" / "results.md").write_text(render_markdown(payload, real_names), encoding="utf-8")
    print("\nResultados en", STRUCT / "stats" / "results.md")
    print("Modelos:", saved)
    return 0


def render_markdown(p: dict, repos: list[str]) -> str:
    res = p["results"]
    names = {
        "1_heuristica": "1. Heurística actual",
        "2_fabrica_no_heldout": "2. Modelo de fábrica (*no held-out*)",
        "3_real": "3. Nuevo, solo repos reales",
        "4_real+sinteticos": "4. Nuevo, reales + sintéticos",
        "3s_real_soft": "3s. (3) sin features de señal directa",
        "4s_real+sinteticos_soft": "4s. (4) sin features de señal directa",
    }
    lines = ["# Resultados (test sobre repos reales no vistos)", "", f"Generado {p['generated_at']} · {p['protocol']} · semillas por modelo: {p['seeds']}", ""]
    lines += ["## Top-1 por fold (¿el candidato mejor puntuado es de ese modelo?)", "", "| Modelo | " + " | ".join(repos) + " | **Promedio** |", "|---|" + "---|" * (len(repos) + 1)]
    for k, label in names.items():
        vals = [res[k][r]["overall"]["top1"] for r in repos]
        lines.append(f"| {label} | " + " | ".join(f"{v:.3f}" for v in vals) + f" | **{np.mean(vals):.3f}** |")
    lines += ["", "## Top-1 SOLO en grupos sin nombre exacto (donde una regla de nombres no alcanza)", "",
              "Son los (modelo, rol) cuyo dueño se decidió por prefijo de nombre, carpeta, `$default_filters` o el controller de la ruta, "
              "no por igualdad de nombre. Es la parte del resultado que NO se puede explicar solo con comparar nombres.", "",
              "| Modelo | " + " | ".join(repos) + " | **Promedio** |", "|---|" + "---|" * (len(repos) + 1)]
    for k, label in names.items():
        vals = [(res[k][r].get("hard") or {"overall": {"top1": float("nan")}})["overall"]["top1"] for r in repos]
        lines.append(f"| {label} | " + " | ".join(f"{v:.3f}" for v in vals) + f" | **{np.nanmean(vals):.3f}** |")
    n_hard = [(res["3_real"][r].get("hard") or {"overall": {"groups": 0}})["overall"]["groups"] for r in repos]
    n_all = [res["3_real"][r]["overall"]["groups"] if "groups" in res["3_real"][r]["overall"] else 0 for r in repos]
    lines += ["", "Grupos difíciles por fold: " + ", ".join(f"{r}={int(n)}" for r, n in zip(repos, n_hard)), ""]
    roles = [r for r in sl.ROLES if all(r in res["3_real"][repos[0]]["by_role"] for _ in [0])]
    lines += ["", "## Por rol — top-1 promedio de los 5 folds", "", "| Rol | " + " | ".join(names[k].split(".")[0] for k in names) + " |", "|---|" + "---|" * len(names)]
    for role in sl.ROLES:
        cells = []
        for k in names:
            vs = [res[k][r]["by_role"][role]["top1"] for r in repos if role in res[k][r]["by_role"]]
            cells.append(f"{np.mean(vs):.3f}" if vs else "—")
        lines.append(f"| {role} | " + " | ".join(cells) + " |")
    lines += ["", "## Por rol — precision / recall / F1 (umbral 0.5, todos los pares) del modelo 4", "", "| Rol | precision | recall | F1 | grupos (modelo×rol) |", "|---|---|---|---|---|"]
    for role in sl.ROLES:
        rows = [res["4_real+sinteticos"][r]["by_role"][role] for r in repos if role in res["4_real+sinteticos"][r]["by_role"]]
        if rows:
            lines.append(f"| {role} | {np.mean([x['precision'] for x in rows]):.3f} | {np.mean([x['recall'] for x in rows]):.3f} | {np.mean([x['f1'] for x in rows]):.3f} | {sum(x['groups'] for x in rows)} |")
    d = p["diagnostic_synthetic_val"]
    lines += ["", "## Diagnóstico sobre sintéticos de validación (NO es resultado principal)", "", f"{d['nota']}", "",
              f"- Modelo 4: top-1 = {d['modelo_4']['overall']['top1']:.3f}, top-3 = {d['modelo_4']['overall']['top3']:.3f}",
              f"- Heurística: top-1 = {d['heuristica']['overall']['top1']:.3f}, top-3 = {d['heuristica']['overall']['top3']:.3f}", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
