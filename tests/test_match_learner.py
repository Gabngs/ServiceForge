from generador import match_learner as ml
from generador.match_learner import FEATURE_NAMES, MatchLearner

_STRONG = {"name_similarity": 0.95, "field_jaccard": 0.8, "mixin_match": 1.0, "same_namespace": 1.0}
_WEAK = {"name_similarity": 0.05, "field_jaccard": 0.0, "mixin_match": 0.0, "same_namespace": 0.0}


def _separable_dataset(n: int = 40):
    """Dataset sintético linealmente separable -- suficiente para que el MLP
    converja a algo sensato en los tests, sin necesitar datos reales."""
    X: list[list[float]] = []
    y: list[int] = []
    for i in range(n):
        strong = [0.9, 0.7, float(i % 2), 1.0]
        weak = [0.05, 0.0, 0.0, 0.0]
        X.append(strong)
        y.append(1)
        X.append(weak)
        y.append(0)
    return X, y


def test_fresh_learner_is_not_fitted_and_uses_heuristic_prior():
    learner = MatchLearner()
    assert not learner.is_fitted
    assert learner.score(_STRONG) > 0.9
    assert learner.score(_WEAK) < 0.1


def test_first_update_fits_the_model(tmp_path):
    learner = MatchLearner(path=tmp_path / "learner.joblib")
    assert not learner.is_fitted

    learner.update(_STRONG, label=1.0)

    assert learner.is_fitted
    assert learner.example_count == 1


def test_update_persists_and_reloads(tmp_path):
    path = tmp_path / "learner.joblib"
    learner = MatchLearner(path=path)
    learner.update(_STRONG, label=1.0)
    learner.update(_WEAK, label=0.0)

    reloaded = MatchLearner.load(path)

    assert reloaded.is_fitted
    assert reloaded.example_count == 2
    assert reloaded.score(_STRONG) == learner.score(_STRONG)


def test_fit_batch_produces_a_working_classifier(tmp_path):
    X, y = _separable_dataset()
    learner = MatchLearner(path=tmp_path / "learner.joblib")

    learner.fit_batch(X, y)

    assert learner.is_fitted
    assert learner.example_count == len(X)
    assert learner.score({"name_similarity": 0.9, "field_jaccard": 0.7, "mixin_match": 0.0, "same_namespace": 1.0}) > 0.5
    assert learner.score({"name_similarity": 0.05, "field_jaccard": 0.0, "mixin_match": 0.0, "same_namespace": 0.0}) < 0.5


def test_load_falls_back_to_bundled_pretrained_when_no_user_file(tmp_path, monkeypatch):
    bundled_path = tmp_path / "bundled.joblib"
    X, y = _separable_dataset()
    factory_learner = MatchLearner(path=bundled_path)
    factory_learner.fit_batch(X, y)
    factory_learner.save()

    monkeypatch.setattr(ml, "bundled_pretrained_path", lambda: bundled_path)

    user_path = tmp_path / "does-not-exist-yet.joblib"
    loaded = MatchLearner.load(user_path)

    # Usa los pesos del modelo de fábrica (no arranca en frío) pero futuros
    # updates se guardan en la ruta del usuario, no en la de fábrica.
    assert loaded.is_fitted
    assert loaded.example_count == len(X)
    assert loaded.path == user_path


def test_load_prefers_users_own_file_over_bundled(tmp_path, monkeypatch):
    bundled_path = tmp_path / "bundled.joblib"
    X, y = _separable_dataset()
    factory_learner = MatchLearner(path=bundled_path)
    factory_learner.fit_batch(X, y)
    factory_learner.save()
    monkeypatch.setattr(ml, "bundled_pretrained_path", lambda: bundled_path)

    user_path = tmp_path / "user.joblib"
    user_learner = MatchLearner(path=user_path)
    user_learner.update(_STRONG, label=1.0)  # un solo ejemplo propio -> example_count=1

    loaded = MatchLearner.load(user_path)

    assert loaded.example_count == 1  # el del usuario, no los 80 del de fábrica


def test_load_ignores_bundled_file_with_mismatched_feature_schema(tmp_path, monkeypatch):
    bundled_path = tmp_path / "bundled.joblib"
    import joblib

    joblib.dump({"model": object(), "example_count": 5, "feature_names": ["otra_cosa"]}, bundled_path)
    monkeypatch.setattr(ml, "bundled_pretrained_path", lambda: bundled_path)

    loaded = MatchLearner.load(tmp_path / "user.joblib")

    assert not loaded.is_fitted
    assert loaded.example_count == 0


def test_load_ignores_corrupted_user_file(tmp_path, monkeypatch):
    # Sin esto, cae al modelo de fábrica REAL empaquetado con la app (ver
    # bundled_pretrained_path) -- que es justamente el fallback correcto en
    # producción, pero no lo que este test quiere aislar.
    monkeypatch.setattr(ml, "bundled_pretrained_path", lambda: tmp_path / "no-bundled-here.joblib")

    path = tmp_path / "learner.joblib"
    path.write_bytes(b"not a valid joblib file")

    loaded = MatchLearner.load(path)

    assert not loaded.is_fitted
    assert loaded.example_count == 0


def test_feature_names_length_matches_model_input():
    learner = MatchLearner()
    assert len(FEATURE_NAMES) == 4
    assert learner._vector(_STRONG) == [_STRONG[name] for name in FEATURE_NAMES]


# ── StructureLearner: el modelo entrenado con el dataset de estructura ──────────────────────────


def _structure_features(**overrides):
    from generador import structure_scan

    features = {name: 0.0 for name in structure_scan.FEATURES}
    features.update(overrides)
    return features


def test_structure_learner_has_its_own_schema_and_paths(tmp_path, monkeypatch):
    from generador import structure_scan
    from generador.match_learner import StructureLearner, default_structure_learner_path

    assert len(StructureLearner().feature_names) == len(structure_scan.FEATURES) == 25
    assert len(MatchLearner().feature_names) == 4  # el legado no cambió
    monkeypatch.setenv("APPDATA", str(tmp_path))
    # lo que aprende el modelo nuevo no pisa el archivo del modelo viejo (tiene otro esquema)
    assert default_structure_learner_path() != ml.default_learner_path()


def test_structure_learner_score_uses_the_scaler_and_stays_a_probability():
    from generador.match_learner import StructureLearner

    learner = StructureLearner.load()  # el de fábrica empaquetado
    strong = _structure_features(name_similarity=1, name_sim_norm=1, name_contains=1, role_service=1, dominant_root=1, subfolder_share=0.8, has_columns=1)
    weak = _structure_features(name_similarity=0.1, name_sim_norm=0.1, role_service=1)

    assert 0.0 <= learner.score(weak) < learner.score(strong) <= 1.0
    assert learner.score(weak) < 0.2


def test_structure_learner_learns_online_and_persists_with_its_scaler(tmp_path):
    from generador.match_learner import StructureLearner

    path = tmp_path / "structure.joblib"
    learner = StructureLearner.load(path)
    assert learner.example_count > 0 and learner.path == path  # arranca del de fábrica, guarda en el del usuario

    borderline = _structure_features(name_similarity=0.5, name_sim_norm=0.5, role_controller=1, subfolder_share=0.3)
    before = learner.score(borderline)
    for _ in range(5):
        learner.update(borderline, label=1.0)

    reloaded = StructureLearner.load(path)
    assert reloaded.scaler is not None
    assert reloaded.score(borderline) == learner.score(borderline)
    assert reloaded.score(borderline) > before


def test_structure_learner_ignores_a_user_file_with_the_old_four_feature_schema(tmp_path):
    from generador.match_learner import StructureLearner

    old = MatchLearner(path=tmp_path / "old.joblib")
    old.update(_STRONG, label=1.0)  # un archivo del modelo legado (4 features) en la ruta del nuevo
    old.save()

    loaded = StructureLearner.load(tmp_path / "old.joblib")

    assert list(loaded.feature_names) != list(FEATURE_NAMES)
    assert loaded.example_count > 1  # cayó al modelo de fábrica del nuevo esquema, no al archivo viejo


def test_structure_learner_fit_batch_fits_the_scaler():
    from generador import structure_scan
    from generador.match_learner import StructureLearner

    names = structure_scan.FEATURES
    X = [[0.9 if n == "name_sim_norm" else 0.0 for n in names] if i % 2 == 0 else [0.05 if n == "name_sim_norm" else 0.0 for n in names] for i in range(40)]
    y = [1 if i % 2 == 0 else 0 for i in range(40)]

    learner = StructureLearner()
    learner.fit_batch(X, y)

    assert learner.is_fitted and learner.scaler is not None
    assert learner.score(_structure_features(name_sim_norm=0.9)) > 0.5 > learner.score(_structure_features(name_sim_norm=0.05))


def test_make_partial_fit_ready_lets_an_early_stopped_model_learn_online():
    """Regresión: un MLP entrenado en lote con early_stopping=True rompía partial_fit (el aprendizaje
    online de la app) -- y dejaba best_loss_ vacío. Los pesos no deben cambiar."""
    import numpy as np
    from sklearn.neural_network import MLPClassifier

    from generador.match_learner import make_partial_fit_ready

    rng = np.random.default_rng(0)
    X = rng.random((200, 3))
    y = (X[:, 0] > 0.5).astype(int)
    mlp = MLPClassifier(hidden_layer_sizes=(4,), early_stopping=True, max_iter=200, random_state=0).fit(X, y)
    before = mlp.predict_proba(X[:5]).copy()

    make_partial_fit_ready(mlp)

    assert np.array_equal(mlp.predict_proba(X[:5]), before)  # no toca los pesos
    mlp.partial_fit(X[:1], y[:1])  # antes: ValueError / TypeError
    make_partial_fit_ready(mlp)  # idempotente sobre un modelo que ya está listo
