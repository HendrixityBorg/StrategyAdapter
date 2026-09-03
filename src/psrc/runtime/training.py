from __future__ import annotations

from typing import Protocol

from pydantic import Field

from psrc.contract.models import ContractModel, Identifier
from psrc.runtime.artifacts import ArtifactManifest, ArtifactStore
from psrc.runtime.strategy import RuntimeStrategy


class RLTransition(ContractModel):
    episode_id: Identifier
    step: int = Field(ge=0)
    state: tuple[float, ...]
    action: int = Field(ge=0)
    reward: float
    next_state: tuple[float, ...]
    next_action: int | None = Field(default=None, ge=0)
    terminated: bool
    truncated: bool = False


class TrainingRequest(ContractModel):
    run_id: Identifier
    dataset_id: Identifier
    seed: int
    features: tuple[tuple[float, ...], ...] = ()
    labels: tuple[float, ...] = ()
    transitions: tuple[RLTransition, ...] = ()
    metadata: dict[str, str] = Field(default_factory=dict)


class TrainableStrategy(Protocol):
    def train(self, request: TrainingRequest, store: ArtifactStore) -> ArtifactManifest: ...

    def load(self, manifest: ArtifactManifest, store: ArtifactStore, *, run_id: str) -> None: ...


class TrainableRuntimeStrategy(RuntimeStrategy, TrainableStrategy, Protocol):
    pass
