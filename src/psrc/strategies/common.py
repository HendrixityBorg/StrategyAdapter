from __future__ import annotations

from decimal import Decimal

from psrc.contract.models import (
    ActionKind,
    ActionRequirements,
    DataKind,
    DataRequirement,
    LifecycleRequirements,
    ResourcePolicy,
    SandboxMode,
    StrategyKind,
    StrategyManifest,
    Timeframe,
    TimeframeMode,
    TrainingMode,
)


def make_manifest(
    *,
    strategy_id: str,
    kind: StrategyKind,
    entrypoint: str,
    profiles: frozenset[str],
    data: tuple[DataRequirement, ...],
    actions: frozenset[ActionKind],
    training: TrainingMode,
    max_position: Decimal | None = Decimal("10"),
    max_order: Decimal | None = Decimal("10"),
) -> StrategyManifest:
    return StrategyManifest(
        strategy_id=strategy_id,
        strategy_version="1.0.0",
        kind=kind,
        entrypoint=entrypoint,
        required_profiles=profiles,
        lifecycle=LifecycleRequirements(
            training=training, state_checkpointing=kind != StrategyKind.RULE
        ),
        data_requirements=data,
        action_requirements=ActionRequirements(
            allowed=actions,
            max_abs_position=max_position,
            max_order_quantity=max_order,
        ),
        resources=ResourcePolicy(sandbox=SandboxMode.DEVELOPMENT),
        deterministic=True,
        seed=7,
    )


def bar_requirement(
    *,
    interval: str,
    symbols: tuple[str, ...],
    lookback: int,
    stream_id: str = "bars",
) -> DataRequirement:
    return DataRequirement(
        stream_id=stream_id,
        kind=DataKind.BAR,
        timeframe=Timeframe(mode=TimeframeMode.BAR, interval=interval),
        symbols=symbols,
        required_fields=frozenset({"open", "high", "low", "close", "volume"}),
        lookback=lookback,
    )


def event_requirement(
    *,
    stream_id: str,
    kind: DataKind,
    symbols: tuple[str, ...],
    fields: frozenset[str],
    depth: int | None = None,
) -> DataRequirement:
    return DataRequirement(
        stream_id=stream_id,
        kind=kind,
        timeframe=Timeframe(mode=TimeframeMode.EVENT),
        symbols=symbols,
        required_fields=fields,
        lookback=1,
        depth=depth,
    )
