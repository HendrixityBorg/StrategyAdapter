from __future__ import annotations

from typing import Literal

from pydantic import Field

from psrc.constants import CONTRACT_VERSION
from psrc.contract.models import (
    ActionKind,
    ContractModel,
    DataRequirement,
    Identifier,
    StrategyKind,
)


class PaperReference(ContractModel):
    title: str
    locator: str
    citation: str


class PaperAmbiguity(ContractModel):
    ambiguity_id: Identifier
    severity: Literal["info", "warning", "blocking"]
    statement: str
    source_excerpt_locator: str | None = None
    resolution: str | None = None
    resolved_by: Literal["paper", "operator", "experiment"] | None = None


class PaperStrategySpec(ContractModel):
    contract_version: str = CONTRACT_VERSION
    spec_id: Identifier
    reference: PaperReference
    strategy_kind: StrategyKind
    hypothesis: str
    data_requirements: tuple[DataRequirement, ...]
    output_actions: frozenset[ActionKind]
    feature_definitions: tuple[str, ...] = ()
    label_definition: str | None = None
    reward_definition: str | None = None
    execution_assumptions: tuple[str, ...]
    ambiguities: tuple[PaperAmbiguity, ...] = ()


class AgentAuditIssue(ContractModel):
    code: Identifier
    severity: Literal["warning", "error"]
    path: str
    message: str


class AgentAuditReport(ContractModel):
    contract_version: str = CONTRACT_VERSION
    spec_id: Identifier
    strategy_id: Identifier
    approved_for_compilation: bool
    issues: tuple[AgentAuditIssue, ...]
    human_review_required: bool = True
    runtime_authority_granted: Literal[False] = False
    checked_fields: frozenset[str] = Field(
        default_factory=lambda: frozenset(
            {
                "strategy_kind",
                "data_requirements",
                "output_actions",
                "training_semantics",
                "paper_ambiguities",
            }
        )
    )
