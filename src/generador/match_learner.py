"""El "modelo" que aprende a reconocer qué Resource ya existente corresponde
a qué Model, a partir de las correcciones del desarrollador -- ver
conversación sobre matching Modelo↔Resource. Es un SOPORTE para
`model_resource_scan.py` (que hace la lectura/extracción de features,
determinística), no la base de la generación: nunca decide QUÉ se genera,
solo ayuda a puntuar candidatos para no crear un Resource duplicado cuando ya
existe uno con otro nombre. Nunca decide sola: cada actualización viene de
una confirmación explícita del desarrollador (ver `update()`), jamás de una
inferencia propia -- así no se vuelve errática por su cuenta.

Es una red neuronal real (`sklearn.neural_network.MLPClassifier`, con una
capa oculta) en vez de un modelo lineal -- PyTorch/TensorFlow quedaron
afuera a propósito: para 4 features de entrada y el volumen de confirmaciones
que un desarrollador junta en la práctica, no hacen falta, y le suman al
.exe empaquetado (PyInstaller) cientos de MB de más sin ninguna ganancia real
de capacidad. scikit-learn es la opción liviana que igual da capas ocultas
de verdad + `partial_fit` para aprender online, un ejemplo a la vez.

Por qué el modelo de fábrica importa tanto acá: entrenar `partial_fit` desde
pesos aleatorios con una sola confirmación del usuario da un paso de
gradiente prácticamente ruidoso (predicciones erráticas hasta juntar
bastantes ejemplos) -- exactamente lo que se quiere evitar. Por eso
`scripts/build_match_dataset.py` arma un dataset real (Model/Resource ya
existentes en proyectos Laravel reales del propio desarrollador) y entrena
un modelo de fábrica que se empaqueta con la app (`model_resource_matcher_pretrained.joblib`)
como punto de partida ya razonable -- el aprendizaje online en vivo parte de
ahí y lo va afinando, nunca arranca de cero en la máquina del usuario.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path

import joblib
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

from . import structure_scan

# Orden fijo -- tiene que coincidir siempre con las keys que arma
# model_resource_scan.py.
FEATURE_NAMES: tuple[str, ...] = (
    "name_similarity",  # 0..1 -- similitud de texto entre nombre de tabla/módulo y nombre del Resource
    "field_jaccard",  # 0..1 -- solapamiento entre columnas de negocio y keys de toArray()
    "mixin_match",  # 0 o 1 -- el docblock del Resource declara @mixin apuntando a este Model
    "same_namespace",  # 0 o 1 -- Resource y Model viven bajo el mismo prefijo de negocio
)

_HIDDEN_LAYER_SIZES = (6,)  # una capa oculta chica -- 4 features de entrada, no hace falta más

# Prior heurístico -- se usa ÚNICAMENTE mientras no hay ningún modelo
# entrenado (ni de fábrica ni online) para consultar, por ejemplo en tests o
# en una instalación sin el .joblib empaquetado. En cuanto hay un modelo
# entrenado (aunque sea el de fábrica), manda siempre él.
_HEURISTIC_WEIGHTS = (2.0, 2.5, 3.5, 0.8)
_HEURISTIC_BIAS = -2.6


def _heuristic_score(features: dict[str, float]) -> float:
    z = _HEURISTIC_BIAS
    for name, weight in zip(FEATURE_NAMES, _HEURISTIC_WEIGHTS):
        z += weight * features.get(name, 0.0)
    if z < -60:
        return 0.0
    if z > 60:
        return 1.0
    return 1.0 / (1.0 + math.exp(-z))


def _new_model() -> MLPClassifier:
    return MLPClassifier(
        hidden_layer_sizes=_HIDDEN_LAYER_SIZES,
        activation="relu",
        solver="adam",
        learning_rate_init=0.05,
        random_state=0,
    )


@dataclass
class MatchLearner:
    """Red neuronal chica (MLP de 1 capa oculta) persistida en disco. Un
    `score()` por candidato (Model, Resource) a partir de sus features; un
    `update()` por cada confirmación/corrección del desarrollador -- nunca
    hace falta reentrenar desde cero, cada corrección es un paso de
    aprendizaje inmediato (`partial_fit`) que se guarda al toque."""

    path: Path | None = None
    model: MLPClassifier = field(default_factory=_new_model)
    example_count: int = 0
    # Esquema de entrada de ESTA instancia (por defecto, las 4 features legadas) y, si el modelo se
    # entrenó con features de escalas distintas, el StandardScaler ya ajustado. Sin escalador el
    # comportamiento es el de siempre.
    feature_names: tuple[str, ...] = FEATURE_NAMES
    scaler: StandardScaler | None = None

    @property
    def is_fitted(self) -> bool:
        return hasattr(self.model, "classes_")

    # Ganchos para que una subclase con otro esquema reuse `load`/`_load_from` sin duplicarlos.
    @classmethod
    def _expected_features(cls) -> tuple[str, ...]:
        return FEATURE_NAMES

    @classmethod
    def _default_path(cls) -> Path:
        return default_learner_path()

    @classmethod
    def _bundled_path(cls) -> Path:
        return bundled_pretrained_path()

    @classmethod
    def load(cls, path: Path | None = None) -> "MatchLearner":
        path = path or cls._default_path()

        # 1) ajustes propios del usuario en esta máquina, si ya confirmó
        #    algo antes (gana siempre sobre el de fábrica).
        if path.exists():
            learner = cls._load_from(path, save_path=path)
            if learner is not None:
                return learner

        # 2) sin ajustes propios todavía -- el modelo de fábrica (entrenado
        #    con proyectos Laravel reales, ver scripts/build_match_dataset.py)
        #    si viene empaquetado con la app, en vez de arrancar en frío con
        #    una red recién inicializada (que predice básicamente ruido).
        bundled = cls._bundled_path()
        if bundled.exists():
            learner = cls._load_from(bundled, save_path=path)
            if learner is not None:
                return learner

        # 3) ni lo uno ni lo otro (instalación sin el .joblib empaquetado,
        #    tests, etc.) -- `score()` cae al prior heurístico hasta que
        #    haya al menos una confirmación real.
        return cls(path=path)

    @classmethod
    def _load_from(cls, source: Path, *, save_path: Path) -> "MatchLearner | None":
        try:
            payload = joblib.load(source)
        except Exception:  # noqa: BLE001 -- archivo corrupto/versión de sklearn distinta
            return None
        expected = cls._expected_features()
        if list(payload.get("feature_names", [])) != list(expected):
            # Esquema de features distinto -- el modelo cargado no
            # corresponde a la misma entrada, mejor arrancar de cero que
            # puntuar con una red que espera otra cosa.
            return None
        return cls(
            path=save_path,
            model=payload["model"],
            example_count=int(payload.get("example_count", 0)),
            feature_names=tuple(expected),
            scaler=payload.get("scaler"),
        )

    def save(self) -> None:
        path = self.path or default_learner_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"model": self.model, "example_count": self.example_count, "feature_names": list(self.feature_names)}
        if self.scaler is not None:
            payload["scaler"] = self.scaler
        joblib.dump(payload, path)

    def _vector(self, features: dict[str, float]) -> list[float]:
        return [features.get(name, 0.0) for name in self.feature_names]

    def _model_input(self, features: dict[str, float]):
        x = [self._vector(features)]
        return self.scaler.transform(x) if self.scaler is not None else x

    def score(self, features: dict[str, float]) -> float:
        """Probabilidad (0..1) de que el candidato sea el match correcto."""
        if not self.is_fitted:
            return _heuristic_score(features)
        return float(self.model.predict_proba(self._model_input(features))[0][1])

    def update(self, features: dict[str, float], label: float, *, save: bool = True) -> None:
        """Un paso de aprendizaje online (label=1.0 confirmado como
        correcto, label=0.0 mostrado como candidato pero descartado por el
        desarrollador) -- y persiste el resultado al toque, así no se pierde
        entre sesiones ("que no pierda lo que ya sabe"). Nunca se llama sola:
        siempre en respuesta a una confirmación explícita (ver gui.py)."""
        make_partial_fit_ready(self.model)
        x = self._model_input(features)
        y = [1 if label >= 0.5 else 0]
        if not self.is_fitted:
            self.model.partial_fit(x, y, classes=[0, 1])
        else:
            self.model.partial_fit(x, y)
        self.example_count += 1
        if save:
            self.save()

    def fit_batch(self, X: list[list[float]], y: list[int]) -> None:
        """Entrena de una sola vez sobre un dataset completo -- lo usa
        `scripts/build_match_dataset.py` para armar el modelo de fábrica, NO
        el flujo en vivo de la app (que aprende online con `update()`, un
        ejemplo a la vez, nunca en lote)."""
        self.model.fit(X, y)
        self.example_count = len(X)


def make_partial_fit_ready(model: MLPClassifier) -> None:
    """Deja utilizable con `partial_fit` a un MLP que se entrenó en lote con `early_stopping=True`.

    Ese modo solo tiene sentido al entrenar de una vez (`fit`), pero scikit-learn no admite
    `partial_fit` con él activo y, además, deja `best_loss_` vacío (que `partial_fit` sí necesita).
    Los pesos no se tocan: solo se reponen los contadores que el modo online espera. Sin esto, el
    aprendizaje online (cada confirmación del desarrollador) fallaría con un modelo de fábrica que
    se haya entrenado con early stopping. No hace nada con un modelo que ya está listo."""
    if getattr(model, "early_stopping", False):
        model.set_params(early_stopping=False)
    if hasattr(model, "loss_curve_") and getattr(model, "best_loss_", 0) is None:
        model.best_loss_ = float(min(model.loss_curve_)) if model.loss_curve_ else float("inf")
        model.validation_scores_ = None
        model._no_improvement_count = 0


_STRUCTURE_HIDDEN_LAYER_SIZES = (32, 16)


def _new_structure_model() -> MLPClassifier:
    return MLPClassifier(
        hidden_layer_sizes=_STRUCTURE_HIDDEN_LAYER_SIZES,
        activation="relu",
        solver="adam",
        alpha=1e-4,
        random_state=0,
    )


@dataclass
class StructureLearner(MatchLearner):
    """El modelo entrenado con el dataset de estructura (`datasets/structure/`, ver su README): la
    misma red de `MatchLearner` pero con las 25 features de `structure_scan.FEATURES`, que reconoce el
    rol de un archivo (Filter, Resource, Requests, Service, Controller, rutas...) respecto de un modelo
    aunque el proyecto use otras carpetas y nombres. Mismo contrato que `MatchLearner` (`score`,
    `update`, `save`, `load`), así que `find_candidates` y la GUI lo usan sin cambios.

    Aprende online igual que el anterior, pero guarda lo aprendido en OTRO archivo del usuario
    (`structure_matcher.joblib`): el del modelo viejo tiene 4 features y no le sirve a este."""

    model: MLPClassifier = field(default_factory=_new_structure_model)
    feature_names: tuple[str, ...] = structure_scan.FEATURES

    @classmethod
    def _expected_features(cls) -> tuple[str, ...]:
        return structure_scan.FEATURES

    @classmethod
    def _default_path(cls) -> Path:
        return default_structure_learner_path()

    @classmethod
    def _bundled_path(cls) -> Path:
        return bundled_structure_path()

    def fit_batch(self, X: list[list[float]], y: list[int]) -> None:
        self.scaler = StandardScaler().fit(X)
        self.model.fit(self.scaler.transform(X), y)
        self.example_count = len(X)


def default_structure_learner_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "ServiceForge" / "structure_matcher.joblib"


def bundled_structure_path() -> Path:
    """Modelo de estructura entrenado de fábrica, empaquetado con la app (ver
    scripts/export_structure_model.py y generador.spec). Solo lectura: lo que aprende la app en uso
    va a `default_structure_learner_path()`."""
    return Path(__file__).parent / "structure_matcher_pretrained.joblib"


def default_learner_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "ServiceForge" / "model_resource_matcher.joblib"


def bundled_pretrained_path() -> Path:
    """Modelo entrenado de fábrica, empaquetado con la app (ver
    scripts/build_match_dataset.py y generador.spec) -- copia de lectura,
    nunca se sobreescribe desde la app en uso (los ajustes del usuario van a
    `default_learner_path()`, aparte)."""
    return Path(__file__).parent / "model_resource_matcher_pretrained.joblib"
