"""Genera un dataset real de pares (Model, Resource) a partir de proyectos
Laravel reales en disco, y entrena el modelo de fábrica del matching
Modelo<->Resource (ver generador/match_learner.py). Se corre a mano cuando
hay proyectos nuevos para sumar al dataset -- no en cada build ni desde la
app en uso.

Uso:
    python scripts/build_match_dataset.py <raiz_backend_1> [<raiz_backend_2> ...]

Ground truth: no hay un dataset etiquetado a mano, así que se infiere con
reglas ESTRICTAS (no la heurística difusa de puntaje continuo que usa la
app) -- positivo solo si el Resource sigue la convención exacta de nombre
para ese Model (`{Model}Resource` / `{Model}RelationResource` /
`{Model}TinyResource`) o declara `@mixin` apuntando a él. Cualquier otro
Resource del mismo proyecto con alguna señal en común (puntaje heurístico >
0) entra como negativo "duro" -- lo que más le cuesta distinguir a un
matcher débil, y lo más parecido a lo que un desarrollador ve en pantalla al
revisar candidatos (ver ModelResourceMatchDialog en gui.py).

Sin conexión a BD no hay columnas reales para `field_jaccard` -- se
reconstruyen parseando las migraciones del propio proyecto
(`database/migrations/**/*.php`, ver migration_import.py) en vez de dejar esa
feature en cero para todo el dataset.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from generador import migration_import  # noqa: E402
from generador import model_resource_scan as mrs  # noqa: E402
from generador.match_learner import FEATURE_NAMES, MatchLearner, bundled_pretrained_path  # noqa: E402

_MAX_HARD_NEGATIVES_PER_MODEL = 3


def _load_table_columns(project_root: Path) -> dict[str, set[str]]:
    """tabla -> nombres de columna, parseando todas las migraciones del
    proyecto. Varias migraciones pueden tocar la misma tabla (create +
    alters posteriores) -- se unen todas, así el set de columnas queda lo
    más completo posible sin necesitar una conexión a BD real."""
    migrations_dir = project_root / "database" / "migrations"
    columns_by_table: dict[str, set[str]] = {}
    if not migrations_dir.is_dir():
        return columns_by_table

    for php_file in migrations_dir.rglob("*.php"):
        try:
            parsed = migration_import.parse_migration_file(php_file)
        except migration_import.MigrationParseError:
            continue
        except OSError:
            continue
        columns_by_table.setdefault(parsed.table, set()).update(c.name for c in parsed.columns)

    return columns_by_table


def _ground_truth_resources(model: "mrs.ModelInfo", resources: list["mrs.ResourceInfo"]) -> list["mrs.ResourceInfo"]:
    matches = []
    for resource in resources:
        if resource.mixin_target == model.class_name:
            matches.append(resource)
        elif resource.base_name == model.class_name:
            matches.append(resource)
    return matches


def build_dataset(project_roots: list[Path]) -> tuple[list[list[float]], list[int], dict[str, int]]:
    X: list[list[float]] = []
    y: list[int] = []
    stats = {"projects": len(project_roots), "models": 0, "positives": 0, "hard_negatives": 0}

    for root in project_roots:
        models = mrs.scan_models(root)
        resources = mrs.scan_resources(root)
        table_columns = _load_table_columns(root)
        stats["models"] += len(models)

        for model in models:
            business_columns = table_columns.get(model.class_name, set())
            positives = _ground_truth_resources(model, resources)
            positive_paths = {r.path for r in positives}

            for resource in positives:
                features = mrs.build_features(
                    resource, table=model.class_name, modulo=model.class_name, model=model, business_columns=business_columns
                )
                X.append([features[name] for name in FEATURE_NAMES])
                y.append(1)
                stats["positives"] += 1

            candidates = []
            for resource in resources:
                if resource.path in positive_paths:
                    continue
                features = mrs.build_features(
                    resource, table=model.class_name, modulo=model.class_name, model=model, business_columns=business_columns
                )
                weight = sum(features.values())
                if weight > 0:
                    candidates.append((weight, features))
            candidates.sort(key=lambda c: c[0], reverse=True)
            for _, features in candidates[:_MAX_HARD_NEGATIVES_PER_MODEL]:
                X.append([features[name] for name in FEATURE_NAMES])
                y.append(0)
                stats["hard_negatives"] += 1

    return X, y, stats


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Uso: python scripts/build_match_dataset.py <raiz_backend_1> [<raiz_backend_2> ...]")
        return 1

    roots = [Path(p) for p in argv[1:]]
    for root in roots:
        if not root.is_dir():
            print(f"No existe o no es una carpeta: {root}")
            return 1

    X, y, stats = build_dataset(roots)
    print(
        f"Dataset: {len(X)} ejemplos ({stats['positives']} positivos, {stats['hard_negatives']} negativos duros) "
        f"de {stats['models']} Models en {stats['projects']} proyecto(s)."
    )
    if not X:
        print("Nada para entrenar -- ¿las rutas apuntan a la raíz del backend (donde vive app/)?")
        return 1

    dataset_path = Path(__file__).resolve().parent.parent / "src" / "generador" / "_match_dataset.json"
    dataset_path.write_text(
        json.dumps({"X": X, "y": y, "feature_names": list(FEATURE_NAMES), "stats": stats}, indent=2),
        encoding="utf-8",
    )
    print(f"Dataset guardado en {dataset_path} (append manual la próxima vez que se sumen proyectos).")

    learner = MatchLearner()
    learner.fit_batch(X, y)
    learner.path = bundled_pretrained_path()
    learner.save()
    print(f"Modelo de fábrica entrenado y guardado en {learner.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
