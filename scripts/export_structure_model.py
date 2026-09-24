"""Empaqueta con la app un modelo de estructura entrenado (Paso posterior a train_structure_models.py).

Convierte el Pipeline (StandardScaler + MLP) de `datasets/structure/models/` al formato de
`generador.match_learner.StructureLearner` y lo escribe como
`src/generador/structure_matcher_pretrained.joblib`, que es el que carga la app (y `generador.spec`
incluye en el .exe). Reemplaza el modelo de fábrica del matching: es una decisión explícita, no
un efecto secundario del entrenamiento, por eso vive en su propio script.

Por defecto usa `real_only` (el mejor en repos reales NO vistos: top-1 0.980 frente a 0.972 con
sintéticos, ver datasets/structure/README.md §5).

Uso:  python scripts/export_structure_model.py [--variant real_only|real_plus_synthetic] [--source <archivo.joblib>]
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import joblib

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from generador import structure_scan  # noqa: E402
from generador.match_learner import StructureLearner, bundled_structure_path, make_partial_fit_ready  # noqa: E402

MODELS_DIR = Path(__file__).resolve().parent.parent / "datasets" / "structure" / "models"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--variant", default="real_only", choices=["real_only", "real_plus_synthetic"])
    ap.add_argument("--source", help="modelo .joblib concreto (por defecto, el más reciente de la variante)")
    args = ap.parse_args()

    source = Path(args.source) if args.source else max(MODELS_DIR.glob(f"structure_matcher_{args.variant}_v*.joblib"), default=None)
    if source is None or not source.exists():
        print(f"No encontré un modelo '{args.variant}' en {MODELS_DIR}")
        return 1

    payload = joblib.load(source)
    if list(payload["feature_names"]) != list(structure_scan.FEATURES):
        print("El modelo se entrenó con otro conjunto de features que el actual de structure_scan.py: hay que reentrenar.")
        return 1

    scaler, mlp = payload["pipeline"].steps[0][1], payload["pipeline"].steps[-1][1]
    # Se entrenó en lote con early_stopping; la app aprende ONLINE de cada confirmación del
    # desarrollador (StructureLearner.update -> partial_fit), que no lo admite. No cambia los pesos.
    make_partial_fit_ready(mlp)
    learner = StructureLearner(path=bundled_structure_path(), model=mlp, scaler=scaler, example_count=int(payload.get("rows", 0)))
    learner.save()
    print(f"Modelo de estructura empaquetado: {learner.path}")
    print(f"  origen: {source.name} · {payload.get('rows')} filas · entrenado {payload.get('trained_at')}")
    print(f"  exportado {datetime.now().strftime('%d-%m-%Y %H:%M:%S')} · {len(structure_scan.FEATURES)} features")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
