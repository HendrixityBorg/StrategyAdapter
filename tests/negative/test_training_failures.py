from __future__ import annotations

from pathlib import Path

import pytest

from psrc.adapters.base import BacktestAdapter
from psrc.adapters.reference import ReferenceEngine, capabilities
from psrc.contract.compiler import compile_run
from psrc.contract.errors import ContractViolation, ErrorCode
from psrc.contract.models import ExecutionPlan, RunPolicy, SandboxMode
from psrc.domain.market import MarketEvent
from psrc.runtime.artifacts import ArtifactStore
from psrc.runtime.orchestrator import run_trainable
from psrc.runtime.report import RunReport
from psrc.runtime.strategy import RuntimeStrategy
from psrc.runtime.training import TrainingRequest
from psrc.strategies.catalog import supervised_examples


def test_invalid_training_shape_is_structured_failure(tmp_path: Path) -> None:
    example = supervised_examples()[0]
    strategy = example.factory()
    plan = compile_run(
        run_id="test.training-failure",
        strategy=strategy.manifest,
        dataset=example.dataset,
        engine=capabilities(),
        policy=RunPolicy(required_sandbox=SandboxMode.DEVELOPMENT),
    )
    invalid = TrainingRequest(
        run_id="train.invalid",
        dataset_id="synthetic.invalid",
        seed=7,
        features=((1.0,), (2.0,)),
        labels=(1.0, -1.0),
    )
    with pytest.raises(ContractViolation) as raised:
        run_trainable(
            plan=plan,
            strategy=strategy,
            training=invalid,
            events=example.events,
            engine=ReferenceEngine(),
            store=ArtifactStore(tmp_path / "artifacts"),
            sandbox_mode=SandboxMode.DEVELOPMENT,
        )
    assert raised.value.error.code == ErrorCode.TRAINING_FAILED
    assert raised.value.error.cause_chain


def test_trainable_engine_crash_is_backtest_failure(tmp_path: Path) -> None:
    example = supervised_examples()[0]
    strategy = example.factory()
    plan = compile_run(
        run_id="test.trainable-backtest-failure",
        strategy=strategy.manifest,
        dataset=example.dataset,
        engine=capabilities(),
        policy=RunPolicy(required_sandbox=SandboxMode.DEVELOPMENT),
    )

    class FailingAdapter:
        def run(
            self,
            *,
            plan: ExecutionPlan,
            strategy: RuntimeStrategy,
            events: tuple[MarketEvent, ...],
            sandbox_mode: SandboxMode,
        ) -> RunReport:
            del plan, strategy, events, sandbox_mode
            raise RuntimeError("synthetic engine crash")

    adapter: BacktestAdapter = FailingAdapter()
    with pytest.raises(ContractViolation) as raised:
        run_trainable(
            plan=plan,
            strategy=strategy,
            training=example.training,
            events=example.events,
            engine=adapter,
            store=ArtifactStore(tmp_path / "artifacts"),
            sandbox_mode=SandboxMode.DEVELOPMENT,
        )
    assert raised.value.error.code == ErrorCode.BACKTEST_FAILED
    assert raised.value.error.stage == "backtest"
