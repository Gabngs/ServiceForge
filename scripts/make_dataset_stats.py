"""Gráficos y tablas del dataset de estructura, para la dataset card y la presentación.

Lee datasets/structure/{pairs.parquet, variation_profile.json, synthetic_index.json, stats/summary.json,
stats/results.json} y escribe PNG en datasets/structure/stats/ y CSV en stats/tables/.

Uso:  python scripts/make_dataset_stats.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import structure_lib as sl  # noqa: E402

STRUCT = Path(__file__).resolve().parent.parent / "datasets" / "structure"
STATS = STRUCT / "stats"
TABLES = STATS / "tables"

C_REAL, C_SYN = "#1f6f8b", "#e0a030"
C_POS, C_NEG = "#2a9d5c", "#b8b8b8"

plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 130, "axes.titlesize": 11})


def save(fig, name: str) -> None:
    fig.tight_layout()
    fig.savefig(STATS / name, bbox_inches="tight")
    plt.close(fig)
    print("  ", name)


def main() -> int:
    STATS.mkdir(exist_ok=True)
    TABLES.mkdir(exist_ok=True)
    df = pd.read_parquet(STRUCT / "pairs.parquet")
    manifest = json.loads((STRUCT / "repos_manifest.json").read_text(encoding="utf-8"))
    roles = [r for r in sl.ROLES if r in set(df["rol"])]

    # 1) filas por rol y origen
    t = df.pivot_table(index="rol", columns="origen", values="label", aggfunc="count", fill_value=0).reindex(roles)
    t.to_csv(TABLES / "filas_por_rol_origen.csv")
    fig, ax = plt.subplots(figsize=(8, 3.8))
    bottom = np.zeros(len(t))
    for col, color in (("real", C_REAL), ("sintetico", C_SYN)):
        if col in t:
            ax.bar(t.index, t[col], bottom=bottom, label=col, color=color)
            bottom += t[col].to_numpy()
    ax.set_title("Filas por rol y origen")
    ax.set_ylabel("pares (modelo, archivo)")
    ax.tick_params(axis="x", rotation=30)
    ax.legend(frameon=False)
    save(fig, "01_filas_por_rol_origen.png")

    # 2) balance positivos / negativos
    bal = df.assign(clase=np.where(df["label"] == 1, "positivo", "neg_" + df["tipo_negativo"])).pivot_table(index="origen", columns="clase", values="label", aggfunc="count", fill_value=0)
    bal.to_csv(TABLES / "balance_clases.csv")
    fig, ax = plt.subplots(figsize=(7, 3.4))
    bal.plot(kind="barh", stacked=True, ax=ax, color=[C_POS, "#7d8ca3", "#a9b4c4", "#d5dbe5"][: bal.shape[1]])
    ax.set_title("Balance de clases (positivos vs. negativos duros / usado_en / fáciles)")
    ax.set_xlabel("filas")
    ax.legend(frameon=False, fontsize=8)
    save(fig, "02_balance_clases.png")

    # 3) criterio con el que se asignó el ground truth (repos reales)
    via = df[(df["label"] == 1) & (df["origen"] == "real")]["via"].value_counts()
    via.to_csv(TABLES / "criterio_ground_truth_real.csv")
    fig, ax = plt.subplots(figsize=(7, 3.4))
    ax.barh(via.index[::-1], via.values[::-1], color=C_REAL)
    ax.set_title("Repos reales: ¿con qué criterio se asignó cada archivo a su modelo?")
    ax.set_xlabel("positivos")
    save(fig, "03_criterio_ground_truth.png")

    # 4) modelos y filas por repo
    fig, ax = plt.subplots(figsize=(9, 3.6))
    per_repo = df.groupby(["repo", "origen"]).size().reset_index(name="n")
    per_repo = per_repo.sort_values(["origen", "n"], ascending=[False, False])
    ax.bar(per_repo["repo"], per_repo["n"], color=[C_REAL if o == "real" else C_SYN for o in per_repo["origen"]])
    ax.set_title("Filas por repo (azul = real, ámbar = sintético)")
    ax.tick_params(axis="x", rotation=90, labelsize=6)
    save(fig, "04_filas_por_repo.png")

    # 5) distribución de ejes: real vs sintético
    prof = json.loads((STRUCT / "variation_profile.json").read_text(encoding="utf-8"))
    syn_path = STRUCT / "synthetic_index.json"
    if syn_path.exists():
        syn = json.loads(syn_path.read_text(encoding="utf-8"))["repos"]
        axes = ["layout", "requests_dir", "sublevel", "routes_location", "controllers_dir", "language", "pk", "token_middleware"]
        # ejes que el perfil de repos reales no mide pero que se conocen: los 5 son Laravel clásico y en español
        known_real = {"layout": "classic", "language": "es"}
        fig, axs = plt.subplots(2, 4, figsize=(14, 6))
        for ax, axis in zip(axs.ravel(), axes):
            real_vals = pd.Series([r.get(axis, known_real.get(axis)) for r in prof["per_repo"].values()]).value_counts(normalize=True)
            syn_vals = pd.Series([r["axes"].get(axis) for r in syn.values()]).value_counts(normalize=True)
            if axis == "token_middleware":
                pass
            cats = sorted(set(real_vals.index) | set(syn_vals.index), key=str)
            x = np.arange(len(cats))
            ax.bar(x - 0.2, [real_vals.get(c, 0) for c in cats], 0.4, color=C_REAL, label="real (5)")
            ax.bar(x + 0.2, [syn_vals.get(c, 0) for c in cats], 0.4, color=C_SYN, label=f"sintético ({len(syn)})")
            ax.set_xticks(x)
            ax.set_xticklabels([str(c)[:14] for c in cats], rotation=40, ha="right", fontsize=7)
            ax.set_title(axis, fontsize=9)
            ax.set_ylim(0, 1)
        axs[0, 0].legend(frameon=False, fontsize=7)
        fig.suptitle("Ejes de variación: los sintéticos cubren estilos que los repos reales no tienen")
        save(fig, "05_ejes_real_vs_sintetico.png")

    # 6) separación de las features principales (positivos vs. negativos)
    feats = ["name_sim_norm", "name_similarity", "subfolder_share", "field_jaccard"]
    fig, axs = plt.subplots(1, len(feats), figsize=(13, 3.2))
    for ax, f in zip(axs, feats):
        ax.hist(df[df["label"] == 0][f], bins=20, alpha=0.7, color=C_NEG, label="negativo", density=True)
        ax.hist(df[df["label"] == 1][f], bins=20, alpha=0.7, color=C_POS, label="positivo", density=True)
        ax.set_title(f, fontsize=9)
    axs[0].legend(frameon=False, fontsize=8)
    fig.suptitle("Qué tan bien separa cada feature a positivos de negativos")
    save(fig, "06_features_positivos_vs_negativos.png")

    # 7) resultados
    res_path = STATS / "results.json"
    if res_path.exists():
        res = json.loads(res_path.read_text(encoding="utf-8"))["results"]
        repos = list(manifest)
        keys = [("1_heuristica", "heurística actual", "#8a8a8a"), ("3_real", "nuevo (solo reales)", "#4c78a8"), ("4_real+sinteticos", "nuevo (reales+sintéticos)", "#2a9d5c"),
                ("4s_real+sinteticos_soft", "nuevo sin señal directa", "#e0a030")]
        fig, ax = plt.subplots(figsize=(11, 4))
        w = 0.2
        x = np.arange(len(roles))
        for i, (k, label, color) in enumerate(keys):
            vals = [np.mean([res[k][r]["by_role"][role]["top1"] for r in repos if role in res[k][r]["by_role"]] or [0]) for role in roles]
            ax.bar(x + (i - 1.5) * w, vals, w, label=label, color=color)
        ax.set_xticks(x)
        ax.set_xticklabels(roles, rotation=25)
        ax.set_ylim(0, 1.05)
        ax.set_ylabel("top-1 (promedio de 5 folds)")
        ax.set_title("Resultado en repos reales NO vistos (leave-one-real-repo-out)")
        ax.legend(frameon=False, ncol=4, fontsize=8)
        save(fig, "07_resultados_top1_por_rol.png")

        # 8) el resultado completo vs. el subconjunto donde una regla de nombres no alcanza
        allkeys = [("1_heuristica", "heurística actual"), ("2_fabrica_no_heldout", "fábrica (no held-out)"), ("3_real", "nuevo, solo reales"),
                   ("4_real+sinteticos", "nuevo, reales+sint."), ("3s_real_soft", "3 sin señal directa"), ("4s_real+sinteticos_soft", "4 sin señal directa")]
        full = [np.mean([res[k][r]["overall"]["top1"] for r in repos]) for k, _ in allkeys]
        hard = [np.mean([res[k][r]["hard"]["overall"]["top1"] for r in repos if res[k][r].get("hard")]) for k, _ in allkeys]
        fig, ax = plt.subplots(figsize=(10, 3.8))
        x = np.arange(len(allkeys))
        ax.bar(x - 0.2, full, 0.4, color="#4c78a8", label="todos los grupos")
        ax.bar(x + 0.2, hard, 0.4, color="#e07b39", label="solo grupos SIN nombre exacto")
        for xi, (a, b) in enumerate(zip(full, hard)):
            ax.text(xi - 0.2, a + 0.01, f"{a:.2f}", ha="center", fontsize=8)
            ax.text(xi + 0.2, b + 0.01, f"{b:.2f}", ha="center", fontsize=8)
        ax.set_xticks(x)
        ax.set_xticklabels([l for _, l in allkeys], rotation=15, fontsize=8)
        ax.set_ylim(0, 1.1)
        ax.set_ylabel("top-1 (promedio de 5 folds)")
        ax.set_title("Cuánto del resultado sobrevive cuando el nombre NO alcanza")
        ax.legend(frameon=False, fontsize=8)
        save(fig, "08_todo_vs_sin_nombre_exacto.png")

    print("Listo:", STATS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
