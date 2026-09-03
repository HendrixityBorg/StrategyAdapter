from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from psrc.contract.models import (
    DataKind,
    DatasetManifest,
    StrategyManifest,
    Timeframe,
    TimeframeMode,
)
from psrc.domain.market import MarketEvent
from psrc.examples.sma_cross import SmaCrossStrategy
from psrc.examples.synthetic import (
    cross_sectional_daily_bars,
    daily_bars,
    l1_quotes,
    l2_books,
    manifest_for_events,
    minute_bar_manifest,
    minute_bars,
    pair_daily_bars,
    twap_bars,
)
from psrc.runtime.strategy import RuntimeStrategy
from psrc.runtime.training import RLTransition, TrainableRuntimeStrategy, TrainingRequest
from psrc.strategies.reinforcement_learning import (
    ContextualBanditExecutionStrategy,
    DoubleQBookInventoryStrategy,
    DynaQPairsStrategy,
    LinearActorCriticAllocationStrategy,
    SarsaTrendStrategy,
    TabularQInventoryStrategy,
)
from psrc.strategies.rule import (
    DonchianBreakoutStrategy,
    L1MicropriceStrategy,
    L2ImbalanceMakerStrategy,
    PairsZScoreStrategy,
    TwapExecutionStrategy,
)
from psrc.strategies.supervised import (
    CrossSectionalRankerStrategy,
    GaussianVolumeBreakoutStrategy,
    L1AdverseSelectionStrategy,
    L2FillProbabilityStrategy,
    LogisticDirectionStrategy,
    RidgeReturnStrategy,
)


@dataclass(frozen=True)
class StrategyExample:
    manifest: StrategyManifest
    factory: Callable[[], RuntimeStrategy]
    events: tuple[MarketEvent, ...]
    dataset: DatasetManifest


@dataclass(frozen=True)
class TrainableExample:
    manifest: StrategyManifest
    factory: Callable[[], TrainableRuntimeStrategy]
    events: tuple[MarketEvent, ...]
    dataset: DatasetManifest
    training: TrainingRequest


def _example(
    factory: Callable[[], RuntimeStrategy],
    events: tuple[MarketEvent, ...],
    *,
    dataset_id: str,
    stream_id: str,
    kind: DataKind,
    timeframe: Timeframe,
    fields: frozenset[str],
) -> StrategyExample:
    instance = factory()
    return StrategyExample(
        manifest=instance.manifest,
        factory=factory,
        events=events,
        dataset=manifest_for_events(
            dataset_id=dataset_id,
            stream_id=stream_id,
            kind=kind,
            timeframe=timeframe,
            fields=fields,
            events=events,
        ),
    )


def rule_examples() -> tuple[StrategyExample, ...]:
    minute = minute_bars()
    daily = daily_bars()
    pairs = pair_daily_bars()
    quotes = l1_quotes()
    books = l2_books()
    twap = twap_bars()
    bar_fields = frozenset({"open", "high", "low", "close", "volume"})
    return (
        StrategyExample(
            manifest=SmaCrossStrategy.manifest,
            factory=SmaCrossStrategy,
            events=minute,
            dataset=minute_bar_manifest(minute),
        ),
        _example(
            DonchianBreakoutStrategy,
            daily,
            dataset_id="synthetic.daily-bars",
            stream_id="bars",
            kind=DataKind.BAR,
            timeframe=Timeframe(mode=TimeframeMode.BAR, interval="P1D"),
            fields=bar_fields,
        ),
        _example(
            PairsZScoreStrategy,
            pairs,
            dataset_id="synthetic.pair-bars",
            stream_id="bars",
            kind=DataKind.BAR,
            timeframe=Timeframe(mode=TimeframeMode.BAR, interval="P1D"),
            fields=bar_fields,
        ),
        _example(
            L1MicropriceStrategy,
            quotes,
            dataset_id="synthetic.l1-quotes",
            stream_id="quotes",
            kind=DataKind.QUOTE_L1,
            timeframe=Timeframe(mode=TimeframeMode.EVENT),
            fields=frozenset({"bid_price", "bid_size", "ask_price", "ask_size"}),
        ),
        _example(
            L2ImbalanceMakerStrategy,
            books,
            dataset_id="synthetic.l2-books",
            stream_id="book",
            kind=DataKind.BOOK_SNAPSHOT_L2,
            timeframe=Timeframe(mode=TimeframeMode.EVENT),
            fields=frozenset({"bids.price", "bids.size", "asks.price", "asks.size"}),
        ),
        _example(
            TwapExecutionStrategy,
            twap,
            dataset_id="synthetic.twap-bars",
            stream_id="bars",
            kind=DataKind.BAR,
            timeframe=Timeframe(mode=TimeframeMode.BAR, interval="PT1M"),
            fields=bar_fields,
        ),
    )


def _training(strategy_id: str, dimensions: int) -> TrainingRequest:
    rows: list[tuple[float, ...]] = []
    labels: list[float] = []
    for index in range(18):
        base = (index - 8.5) / 10
        row = tuple(
            base * (feature + 1) + ((index + feature) % 3 - 1) * 0.05
            for feature in range(dimensions)
        )
        rows.append(row)
        labels.append(1.0 if sum(row) + (0.15 if index % 4 == 0 else -0.05) > 0 else -1.0)
    return TrainingRequest(
        run_id=f"train.{strategy_id}",
        dataset_id="synthetic.training-matrix",
        seed=7,
        features=tuple(rows),
        labels=tuple(labels),
        metadata={"split": "chronological-synthetic-v1"},
    )


def supervised_examples() -> tuple[TrainableExample, ...]:
    daily = daily_bars()
    minute = minute_bars()
    twap = twap_bars()
    quotes = l1_quotes()
    books = l2_books()
    cross_section = cross_sectional_daily_bars()
    bar_fields = frozenset({"open", "high", "low", "close", "volume"})

    def build(
        factory: Callable[[], TrainableRuntimeStrategy],
        events: tuple[MarketEvent, ...],
        *,
        dataset_id: str,
        stream_id: str,
        kind: DataKind,
        timeframe: Timeframe,
        fields: frozenset[str],
        dimensions: int,
    ) -> TrainableExample:
        strategy = factory()
        return TrainableExample(
            manifest=strategy.manifest,
            factory=factory,
            events=events,
            dataset=manifest_for_events(
                dataset_id=dataset_id,
                stream_id=stream_id,
                kind=kind,
                timeframe=timeframe,
                fields=fields,
                events=events,
            ),
            training=_training(strategy.manifest.strategy_id, dimensions),
        )

    return (
        build(
            LogisticDirectionStrategy,
            daily,
            dataset_id="synthetic.daily-bars",
            stream_id="bars",
            kind=DataKind.BAR,
            timeframe=Timeframe(mode=TimeframeMode.BAR, interval="P1D"),
            fields=bar_fields,
            dimensions=3,
        ),
        build(
            RidgeReturnStrategy,
            minute,
            dataset_id="synthetic.minute-bars",
            stream_id="bars",
            kind=DataKind.BAR,
            timeframe=Timeframe(mode=TimeframeMode.BAR, interval="PT1M"),
            fields=bar_fields,
            dimensions=3,
        ),
        build(
            GaussianVolumeBreakoutStrategy,
            twap,
            dataset_id="synthetic.twap-bars",
            stream_id="bars",
            kind=DataKind.BAR,
            timeframe=Timeframe(mode=TimeframeMode.BAR, interval="PT1M"),
            fields=bar_fields,
            dimensions=2,
        ),
        build(
            L1AdverseSelectionStrategy,
            quotes,
            dataset_id="synthetic.l1-quotes",
            stream_id="quotes",
            kind=DataKind.QUOTE_L1,
            timeframe=Timeframe(mode=TimeframeMode.EVENT),
            fields=frozenset({"bid_price", "bid_size", "ask_price", "ask_size"}),
            dimensions=3,
        ),
        build(
            L2FillProbabilityStrategy,
            books,
            dataset_id="synthetic.l2-books",
            stream_id="book",
            kind=DataKind.BOOK_SNAPSHOT_L2,
            timeframe=Timeframe(mode=TimeframeMode.EVENT),
            fields=frozenset({"bids.price", "bids.size", "asks.price", "asks.size"}),
            dimensions=3,
        ),
        build(
            CrossSectionalRankerStrategy,
            cross_section,
            dataset_id="synthetic.cross-sectional-bars",
            stream_id="bars",
            kind=DataKind.BAR,
            timeframe=Timeframe(mode=TimeframeMode.BAR, interval="P1D"),
            fields=bar_fields,
            dimensions=3,
        ),
    )


def _rl_training(strategy_id: str) -> TrainingRequest:
    transitions: list[RLTransition] = []
    for index in range(30):
        state = (
            float(index % 5 - 2),
            float((index // 2) % 5 - 2),
            float((index // 3) % 5 - 2),
        )
        action = index % 3
        next_state = (
            float((index + 1) % 5 - 2),
            float(((index + 1) // 2) % 5 - 2),
            float(((index + 1) // 3) % 5 - 2),
        )
        preferred = int(max(0, min(2, round(state[0]) + 1)))
        reward = 1.0 if action == preferred else -0.4 - abs(action - preferred) * 0.1
        transitions.append(
            RLTransition(
                episode_id=f"episode:{index // 10}",
                step=index % 10,
                state=state,
                action=action,
                reward=reward,
                next_state=next_state,
                next_action=(index + 1) % 3,
                terminated=index % 10 == 9,
            )
        )
    return TrainingRequest(
        run_id=f"train.{strategy_id}",
        dataset_id="synthetic.rl-transitions",
        seed=7,
        transitions=tuple(transitions),
        metadata={
            "observation_space": "Box(3)",
            "action_space": "Discrete(3)",
            "reward": "preferred-action-minus-distance-v1",
        },
    )


def reinforcement_learning_examples() -> tuple[TrainableExample, ...]:
    daily = daily_bars()
    minute = minute_bars()
    twap = twap_bars()
    books = l2_books()
    pairs = pair_daily_bars()
    bar_fields = frozenset({"open", "high", "low", "close", "volume"})

    def build(
        factory: Callable[[], TrainableRuntimeStrategy],
        events: tuple[MarketEvent, ...],
        *,
        dataset_id: str,
        stream_id: str,
        kind: DataKind,
        timeframe: Timeframe,
        fields: frozenset[str],
    ) -> TrainableExample:
        strategy = factory()
        return TrainableExample(
            manifest=strategy.manifest,
            factory=factory,
            events=events,
            dataset=manifest_for_events(
                dataset_id=dataset_id,
                stream_id=stream_id,
                kind=kind,
                timeframe=timeframe,
                fields=fields,
                events=events,
            ),
            training=_rl_training(strategy.manifest.strategy_id),
        )

    return (
        build(
            TabularQInventoryStrategy,
            daily,
            dataset_id="synthetic.daily-bars",
            stream_id="bars",
            kind=DataKind.BAR,
            timeframe=Timeframe(mode=TimeframeMode.BAR, interval="P1D"),
            fields=bar_fields,
        ),
        build(
            SarsaTrendStrategy,
            minute,
            dataset_id="synthetic.minute-bars",
            stream_id="bars",
            kind=DataKind.BAR,
            timeframe=Timeframe(mode=TimeframeMode.BAR, interval="PT1M"),
            fields=bar_fields,
        ),
        build(
            ContextualBanditExecutionStrategy,
            twap,
            dataset_id="synthetic.twap-bars",
            stream_id="bars",
            kind=DataKind.BAR,
            timeframe=Timeframe(mode=TimeframeMode.BAR, interval="PT1M"),
            fields=bar_fields,
        ),
        build(
            DoubleQBookInventoryStrategy,
            books,
            dataset_id="synthetic.l2-books",
            stream_id="book",
            kind=DataKind.BOOK_SNAPSHOT_L2,
            timeframe=Timeframe(mode=TimeframeMode.EVENT),
            fields=frozenset({"bids.price", "bids.size", "asks.price", "asks.size"}),
        ),
        build(
            DynaQPairsStrategy,
            pairs,
            dataset_id="synthetic.pair-bars",
            stream_id="bars",
            kind=DataKind.BAR,
            timeframe=Timeframe(mode=TimeframeMode.BAR, interval="P1D"),
            fields=bar_fields,
        ),
        build(
            LinearActorCriticAllocationStrategy,
            daily,
            dataset_id="synthetic.daily-bars",
            stream_id="bars",
            kind=DataKind.BAR,
            timeframe=Timeframe(mode=TimeframeMode.BAR, interval="P1D"),
            fields=bar_fields,
        ),
    )


def all_examples() -> tuple[StrategyExample | TrainableExample, ...]:
    return rule_examples() + supervised_examples() + reinforcement_learning_examples()
