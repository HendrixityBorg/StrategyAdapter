from __future__ import annotations

import json
import math
from decimal import Decimal
from hashlib import sha256

import numpy as np
from numpy.typing import NDArray

from psrc.contract.models import ActionKind, DataKind, StrategyKind, TrainingMode
from psrc.domain.account import AccountSnapshot
from psrc.domain.actions import Action, NoOp, Prediction, TargetPosition, TargetWeight
from psrc.domain.market import (
    BarPayload,
    BookSnapshotL2Payload,
    MarketEvent,
    QuoteL1Payload,
)
from psrc.runtime.artifacts import ArtifactManifest, ArtifactStore
from psrc.runtime.training import TrainingRequest
from psrc.strategies.common import bar_requirement, event_requirement, make_manifest

Array = NDArray[np.float64]


class _JsonModelStrategy:
    manifest = make_manifest(
        strategy_id="supervised.abstract",
        kind=StrategyKind.SUPERVISED,
        entrypoint="invalid",
        profiles=frozenset({"training.supervised.v1"}),
        data=(bar_requirement(interval="P1D", symbols=("SYNTH.DAILY",), lookback=2),),
        actions=frozenset({ActionKind.NO_OP}),
        training=TrainingMode.REQUIRED,
    )

    def __init__(self) -> None:
        self.model: dict[str, object] | None = None
        self.artifact_id: str | None = None

    def _save(
        self, request: TrainingRequest, store: ArtifactStore, model: dict[str, object]
    ) -> ArtifactManifest:
        payload = json.dumps(model, sort_keys=True, separators=(",", ":")).encode()
        artifact_id = f"sha256-{sha256(payload).hexdigest()}"
        return store.save_bytes(
            run_id=request.run_id,
            artifact_id=artifact_id,
            strategy_id=self.manifest.strategy_id,
            strategy_version=self.manifest.strategy_version,
            artifact_kind="model",
            framework="numpy-json",
            logical_name="model.json",
            media_type="application/json",
            payload=payload,
            training_dataset_id=request.dataset_id,
            seed=request.seed,
            metadata={"algorithm": str(model["algorithm"])},
        )

    def load(self, manifest: ArtifactManifest, store: ArtifactStore, *, run_id: str) -> None:
        if manifest.strategy_id != self.manifest.strategy_id:
            raise ValueError("artifact strategy_id does not match strategy")
        payload = store.load_bytes(
            run_id=run_id, strategy_id=self.manifest.strategy_id, manifest=manifest
        )["model.json"]
        value = json.loads(payload)
        if not isinstance(value, dict):
            raise ValueError("model artifact root must be an object")
        self.model = value
        self.artifact_id = manifest.artifact_id

    def _require_model(self) -> tuple[dict[str, object], str]:
        if self.model is None or self.artifact_id is None:
            raise RuntimeError("model artifact has not been loaded")
        return self.model, self.artifact_id

    @staticmethod
    def _arrays(request: TrainingRequest, dimensions: int) -> tuple[Array, Array]:
        x = np.asarray(request.features, dtype=np.float64)
        y = np.asarray(request.labels, dtype=np.float64)
        if x.ndim != 2 or x.shape[1] != dimensions or len(x) != len(y) or len(y) < 4:
            raise ValueError(
                f"expected at least four rows with {dimensions} features and aligned labels"
            )
        if not np.isfinite(x).all() or not np.isfinite(y).all():
            raise ValueError("training data contains non-finite values")
        return x, y

    @staticmethod
    def _linear_score(model: dict[str, object], features: tuple[float, ...]) -> float:
        weights = np.asarray(model["weights"], dtype=np.float64)
        intercept = float(str(model.get("intercept", 0.0)))
        return float(np.dot(weights, np.asarray(features)) + intercept)

    def on_start(self) -> None:
        pass

    def on_finish(self) -> None:
        pass


class LogisticDirectionStrategy(_JsonModelStrategy):
    manifest = make_manifest(
        strategy_id="supervised.logistic_direction",
        kind=StrategyKind.SUPERVISED,
        entrypoint="psrc.strategies.supervised:LogisticDirectionStrategy",
        profiles=frozenset({"core.bar.v1", "execution.basic.v1", "training.supervised.v1"}),
        data=(bar_requirement(interval="P1D", symbols=("SYNTH.DAILY",), lookback=2),),
        actions=frozenset({ActionKind.NO_OP, ActionKind.PREDICTION, ActionKind.TARGET_POSITION}),
        training=TrainingMode.REQUIRED,
        max_position=Decimal("1"),
    )

    def train(self, request: TrainingRequest, store: ArtifactStore) -> ArtifactManifest:
        x, y = self._arrays(request, 3)
        weights = np.zeros(3)
        intercept = 0.0
        targets = (y > 0).astype(float)
        for _ in range(200):
            logits = np.clip(x @ weights + intercept, -30, 30)
            probabilities = 1 / (1 + np.exp(-logits))
            error = probabilities - targets
            weights -= 0.1 * (x.T @ error / len(x))
            intercept -= 0.1 * float(np.mean(error))
        return self._save(
            request,
            store,
            {
                "algorithm": "logistic-gradient-descent-v1",
                "weights": weights.tolist(),
                "intercept": intercept,
            },
        )

    def on_event(self, event: MarketEvent, account: AccountSnapshot) -> tuple[Action, ...]:
        del account
        if not isinstance(event.payload, BarPayload):
            return (NoOp(reason_code="event.not_bar", explanation="requires daily bars"),)
        model, artifact_id = self._require_model()
        bar = event.payload
        features = (
            float((bar.close - bar.open) / bar.open),
            float((bar.high - bar.low) / bar.open),
            math.log1p(float(bar.volume)) / 10,
        )
        probability = 1 / (
            1 + math.exp(-max(-30.0, min(30.0, self._linear_score(model, features))))
        )
        return (
            Prediction(
                instrument_id=event.instrument_id,
                value=Decimal(str(probability)),
                horizon="P1D",
                model_artifact_id=artifact_id,
                reason_code="model.logistic_probability",
            ),
            TargetPosition(
                instrument_id=event.instrument_id,
                quantity=Decimal("1") if probability >= 0.5 else Decimal("-1"),
                reason_code="allocation.logistic_threshold",
            ),
        )


class RidgeReturnStrategy(_JsonModelStrategy):
    manifest = make_manifest(
        strategy_id="supervised.ridge_return",
        kind=StrategyKind.SUPERVISED,
        entrypoint="psrc.strategies.supervised:RidgeReturnStrategy",
        profiles=frozenset({"core.bar.v1", "execution.basic.v1", "training.supervised.v1"}),
        data=(bar_requirement(interval="PT1M", symbols=("SYNTH.TEST",), lookback=3),),
        actions=frozenset({ActionKind.NO_OP, ActionKind.PREDICTION, ActionKind.TARGET_POSITION}),
        training=TrainingMode.REQUIRED,
        max_position=Decimal("2"),
    )

    def train(self, request: TrainingRequest, store: ArtifactStore) -> ArtifactManifest:
        x, y = self._arrays(request, 3)
        design = np.column_stack([np.ones(len(x)), x])
        penalty = np.eye(design.shape[1]) * 0.2
        penalty[0, 0] = 0
        coefficients = np.linalg.solve(design.T @ design + penalty, design.T @ y)
        return self._save(
            request,
            store,
            {
                "algorithm": "ridge-closed-form-v1",
                "intercept": float(coefficients[0]),
                "weights": coefficients[1:].tolist(),
            },
        )

    def on_event(self, event: MarketEvent, account: AccountSnapshot) -> tuple[Action, ...]:
        del account
        if not isinstance(event.payload, BarPayload):
            return (NoOp(reason_code="event.not_bar", explanation="requires minute bars"),)
        model, artifact_id = self._require_model()
        bar = event.payload
        features = (
            float(bar.close / bar.open - 1),
            float((bar.high - bar.low) / bar.open),
            math.log1p(float(bar.volume)) / 10,
        )
        forecast = self._linear_score(model, features)
        target = (
            Decimal("2")
            if forecast > 0.001
            else Decimal("-2")
            if forecast < -0.001
            else Decimal("0")
        )
        return (
            Prediction(
                instrument_id=event.instrument_id,
                value=Decimal(str(forecast)),
                horizon="PT1M",
                model_artifact_id=artifact_id,
                reason_code="model.ridge_return",
            ),
            TargetPosition(
                instrument_id=event.instrument_id,
                quantity=target,
                reason_code="allocation.forecast_band",
            ),
        )


class GaussianVolumeBreakoutStrategy(_JsonModelStrategy):
    manifest = make_manifest(
        strategy_id="supervised.gaussian_volume_breakout",
        kind=StrategyKind.SUPERVISED,
        entrypoint="psrc.strategies.supervised:GaussianVolumeBreakoutStrategy",
        profiles=frozenset({"core.bar.v1", "execution.basic.v1", "training.supervised.v1"}),
        data=(bar_requirement(interval="PT1M", symbols=("SYNTH.TWAP",), lookback=2),),
        actions=frozenset({ActionKind.NO_OP, ActionKind.PREDICTION, ActionKind.TARGET_POSITION}),
        training=TrainingMode.REQUIRED,
        max_position=Decimal("1"),
    )

    def train(self, request: TrainingRequest, store: ArtifactStore) -> ArtifactManifest:
        x, y = self._arrays(request, 2)
        labels = (y > 0).astype(int)
        if set(labels.tolist()) != {0, 1}:
            raise ValueError("Gaussian classifier requires both label classes")
        classes: dict[str, object] = {}
        for label in (0, 1):
            subset = x[labels == label]
            classes[str(label)] = {
                "mean": subset.mean(axis=0).tolist(),
                "variance": (subset.var(axis=0) + 1e-6).tolist(),
                "prior": float(len(subset) / len(x)),
            }
        return self._save(
            request,
            store,
            {"algorithm": "gaussian-naive-bayes-v1", "classes": classes},
        )

    def on_event(self, event: MarketEvent, account: AccountSnapshot) -> tuple[Action, ...]:
        del account
        if not isinstance(event.payload, BarPayload):
            return (NoOp(reason_code="event.not_bar", explanation="requires minute bars"),)
        model, artifact_id = self._require_model()
        bar = event.payload
        features = np.asarray(
            [math.log1p(float(bar.volume)) / 10, float((bar.high - bar.low) / bar.open)]
        )
        scores: dict[int, float] = {}
        classes = model["classes"]
        assert isinstance(classes, dict)
        for label in (0, 1):
            parameters = classes[str(label)]
            assert isinstance(parameters, dict)
            mean = np.asarray(parameters["mean"])
            variance = np.asarray(parameters["variance"])
            scores[label] = float(
                math.log(float(parameters["prior"]))
                - 0.5 * np.sum(np.log(2 * math.pi * variance) + (features - mean) ** 2 / variance)
            )
        probability = 1 / (1 + math.exp(scores[0] - scores[1]))
        return (
            Prediction(
                instrument_id=event.instrument_id,
                value=Decimal(str(probability)),
                horizon="PT5M",
                model_artifact_id=artifact_id,
                reason_code="model.gaussian_breakout_probability",
            ),
            TargetPosition(
                instrument_id=event.instrument_id,
                quantity=Decimal("1") if probability > 0.55 else Decimal("0"),
                reason_code="allocation.breakout_probability",
            ),
        )


class L1AdverseSelectionStrategy(_JsonModelStrategy):
    manifest = make_manifest(
        strategy_id="supervised.l1_adverse_selection",
        kind=StrategyKind.SUPERVISED,
        entrypoint="psrc.strategies.supervised:L1AdverseSelectionStrategy",
        profiles=frozenset({"event.l1.v1", "execution.basic.v1", "training.supervised.v1"}),
        data=(
            event_requirement(
                stream_id="quotes",
                kind=DataKind.QUOTE_L1,
                symbols=("SYNTH.L1",),
                fields=frozenset({"bid_price", "bid_size", "ask_price", "ask_size"}),
            ),
        ),
        actions=frozenset({ActionKind.NO_OP, ActionKind.PREDICTION, ActionKind.TARGET_POSITION}),
        training=TrainingMode.REQUIRED,
        max_position=Decimal("1"),
    )

    def train(self, request: TrainingRequest, store: ArtifactStore) -> ArtifactManifest:
        x, y = self._arrays(request, 3)
        labels = np.where(y > 0, 1.0, -1.0)
        weights = np.zeros(3)
        intercept = 0.0
        for _ in range(20):
            for row, label in zip(x, labels, strict=True):
                if label * (float(row @ weights) + intercept) <= 0:
                    weights += 0.05 * label * row
                    intercept += 0.05 * label
        return self._save(
            request,
            store,
            {
                "algorithm": "online-perceptron-v1",
                "weights": weights.tolist(),
                "intercept": intercept,
            },
        )

    def on_event(self, event: MarketEvent, account: AccountSnapshot) -> tuple[Action, ...]:
        del account
        if not isinstance(event.payload, QuoteL1Payload):
            return (NoOp(reason_code="event.not_l1", explanation="requires L1 quotes"),)
        model, artifact_id = self._require_model()
        quote = event.payload
        total = max(quote.bid_size + quote.ask_size, Decimal("1"))
        features = (
            float((quote.bid_size - quote.ask_size) / total),
            float((quote.ask_price - quote.bid_price) / quote.bid_price),
            float((quote.bid_price + quote.ask_price) / 2 / Decimal("100") - 1),
        )
        margin = self._linear_score(model, features)
        return (
            Prediction(
                instrument_id=event.instrument_id,
                value=Decimal(str(margin)),
                horizon="PT1S",
                model_artifact_id=artifact_id,
                reason_code="model.perceptron_adverse_selection",
            ),
            TargetPosition(
                instrument_id=event.instrument_id,
                quantity=Decimal("-1") if margin > 0 else Decimal("1"),
                reason_code="allocation.avoid_adverse_side",
            ),
        )


class L2FillProbabilityStrategy(_JsonModelStrategy):
    manifest = make_manifest(
        strategy_id="supervised.l2_fill_probability",
        kind=StrategyKind.SUPERVISED,
        entrypoint="psrc.strategies.supervised:L2FillProbabilityStrategy",
        profiles=frozenset({"event.l2.v1", "execution.basic.v1", "training.supervised.v1"}),
        data=(
            event_requirement(
                stream_id="book",
                kind=DataKind.BOOK_SNAPSHOT_L2,
                symbols=("SYNTH.L2",),
                fields=frozenset({"bids.price", "bids.size", "asks.price", "asks.size"}),
                depth=3,
            ),
        ),
        actions=frozenset({ActionKind.NO_OP, ActionKind.PREDICTION, ActionKind.TARGET_POSITION}),
        training=TrainingMode.REQUIRED,
        max_position=Decimal("1"),
    )

    def train(self, request: TrainingRequest, store: ArtifactStore) -> ArtifactManifest:
        x, y = self._arrays(request, 3)
        target = (y > 0).astype(float)
        weights = np.zeros(3)
        for _ in range(160):
            probability = 1 / (1 + np.exp(-np.clip(x @ weights, -30, 30)))
            gradient = x.T @ (probability - target) / len(x) + 0.02 * np.sign(weights)
            weights -= 0.08 * gradient
        return self._save(
            request,
            store,
            {
                "algorithm": "l1-regularized-logistic-v1",
                "weights": weights.tolist(),
                "intercept": 0.0,
            },
        )

    def on_event(self, event: MarketEvent, account: AccountSnapshot) -> tuple[Action, ...]:
        del account
        if not isinstance(event.payload, BookSnapshotL2Payload):
            return (NoOp(reason_code="event.not_l2", explanation="requires L2 book"),)
        model, artifact_id = self._require_model()
        book = event.payload
        bid_depth = sum(level.size for level in book.bids)
        ask_depth = sum(level.size for level in book.asks)
        total = max(bid_depth + ask_depth, Decimal("1"))
        features = (
            float((bid_depth - ask_depth) / total),
            float((book.asks[0].price - book.bids[0].price) / book.bids[0].price),
            float((book.bids[0].size + book.asks[0].size) / total),
        )
        probability = 1 / (
            1 + math.exp(-max(-30.0, min(30.0, self._linear_score(model, features))))
        )
        return (
            Prediction(
                instrument_id=event.instrument_id,
                value=Decimal(str(probability)),
                horizon="PT500MS",
                model_artifact_id=artifact_id,
                reason_code="model.limit_fill_probability",
            ),
            TargetPosition(
                instrument_id=event.instrument_id,
                quantity=Decimal("1") if probability > 0.5 else Decimal("-1"),
                reason_code="allocation.fill_probability",
            ),
        )


class CrossSectionalRankerStrategy(_JsonModelStrategy):
    manifest = make_manifest(
        strategy_id="supervised.cross_sectional_ranker",
        kind=StrategyKind.SUPERVISED,
        entrypoint="psrc.strategies.supervised:CrossSectionalRankerStrategy",
        profiles=frozenset({"core.bar.v1", "portfolio.batch.v1", "training.supervised.v1"}),
        data=(
            bar_requirement(
                interval="P1D",
                symbols=("SYNTH.XS-A", "SYNTH.XS-B", "SYNTH.XS-C"),
                lookback=2,
            ),
        ),
        actions=frozenset({ActionKind.NO_OP, ActionKind.PREDICTION, ActionKind.TARGET_WEIGHT}),
        training=TrainingMode.REQUIRED,
        max_position=None,
    )

    def __init__(self) -> None:
        super().__init__()
        self.symbols = ("SYNTH.XS-A", "SYNTH.XS-B", "SYNTH.XS-C")
        self.current: dict[str, tuple[object, tuple[float, ...]]] = {}

    def train(self, request: TrainingRequest, store: ArtifactStore) -> ArtifactManifest:
        x, y = self._arrays(request, 3)
        ordering = np.argsort(y)
        group = max(1, len(y) // 3)
        bottom = x[ordering[:group]].mean(axis=0)
        top = x[ordering[-group:]].mean(axis=0)
        weights = top - bottom
        norm = float(np.linalg.norm(weights))
        if norm == 0:
            raise ValueError("ranker training produced a zero discriminant")
        weights /= norm
        return self._save(
            request,
            store,
            {
                "algorithm": "top-bottom-centroid-ranker-v1",
                "weights": weights.tolist(),
                "intercept": 0.0,
            },
        )

    def on_start(self) -> None:
        self.current.clear()

    def on_event(self, event: MarketEvent, account: AccountSnapshot) -> tuple[Action, ...]:
        del account
        if not isinstance(event.payload, BarPayload):
            return (NoOp(reason_code="event.not_bar", explanation="requires daily bars"),)
        model, artifact_id = self._require_model()
        bar = event.payload
        features = (
            float(bar.close / bar.open - 1),
            float((bar.high - bar.low) / bar.open),
            math.log1p(float(bar.volume)) / 10,
        )
        self.current[event.instrument_id] = (event.available_time, features)
        if any(symbol not in self.current for symbol in self.symbols):
            return (
                NoOp(reason_code="cross_section.awaiting_symbols", explanation="batch incomplete"),
            )
        if len({self.current[symbol][0] for symbol in self.symbols}) != 1:
            return (NoOp(reason_code="cross_section.not_synchronized", explanation="times differ"),)
        scores = {
            symbol: self._linear_score(model, self.current[symbol][1]) for symbol in self.symbols
        }
        ranked = sorted(scores, key=lambda symbol: scores[symbol])
        weights = {ranked[0]: Decimal("-0.5"), ranked[1]: Decimal("0"), ranked[2]: Decimal("0.5")}
        actions: list[Action] = []
        for symbol in self.symbols:
            actions.extend(
                (
                    Prediction(
                        instrument_id=symbol,
                        value=Decimal(str(scores[symbol])),
                        horizon="P1D",
                        model_artifact_id=artifact_id,
                        reason_code="model.cross_section_score",
                    ),
                    TargetWeight(
                        instrument_id=symbol,
                        weight=weights[symbol],
                        reason_code="allocation.long_short_rank",
                    ),
                )
            )
        return tuple(actions)
