from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field

from psrc.constants import CONTRACT_VERSION
from psrc.contract.models import ContractModel, Identifier


class ErrorStage(StrEnum):
    DISCOVERY = "discovery"
    VALIDATION = "validation"
    CAPABILITY_NEGOTIATION = "capability_negotiation"
    INITIALIZATION = "initialization"
    TRAINING = "training"
    ARTIFACT = "artifact"
    INFERENCE = "inference"
    ACTION_VALIDATION = "action_validation"
    BACKTEST = "backtest"
    SANDBOX = "sandbox"
    REPORTING = "reporting"


class ErrorCode(StrEnum):
    CONTRACT_VERSION_UNSUPPORTED = "CONTRACT_VERSION_UNSUPPORTED"
    MANIFEST_INVALID = "MANIFEST_INVALID"
    LIFECYCLE_TRANSITION_INVALID = "LIFECYCLE_TRANSITION_INVALID"
    DATA_STREAM_MISSING = "DATA_STREAM_MISSING"
    DATA_FIELD_MISSING = "DATA_FIELD_MISSING"
    DATA_TIMEFRAME_MISMATCH = "DATA_TIMEFRAME_MISMATCH"
    DATA_ORDERING_INVALID = "DATA_ORDERING_INVALID"
    DATA_HASH_MISMATCH = "DATA_HASH_MISMATCH"
    SOURCE_HASH_MISMATCH = "SOURCE_HASH_MISMATCH"
    COMPATIBILITY_TRANSFORM_FAILED = "COMPATIBILITY_TRANSFORM_FAILED"
    SYMBOL_MAPPING_FAILED = "SYMBOL_MAPPING_FAILED"
    ENGINE_CAPABILITY_UNSUPPORTED = "ENGINE_CAPABILITY_UNSUPPORTED"
    ENGINE_DEPENDENCY_MISSING = "ENGINE_DEPENDENCY_MISSING"
    ARTIFACT_NOT_FOUND = "ARTIFACT_NOT_FOUND"
    ARTIFACT_HASH_MISMATCH = "ARTIFACT_HASH_MISMATCH"
    ACTION_INVALID = "ACTION_INVALID"
    ORDER_REJECTED = "ORDER_REJECTED"
    TRAINING_FAILED = "TRAINING_FAILED"
    INFERENCE_FAILED = "INFERENCE_FAILED"
    BACKTEST_FAILED = "BACKTEST_FAILED"
    SANDBOX_UNAVAILABLE = "SANDBOX_UNAVAILABLE"
    SANDBOX_POLICY_DOWNGRADE = "SANDBOX_POLICY_DOWNGRADE"
    SANDBOX_POLICY_DENIED = "SANDBOX_POLICY_DENIED"
    SANDBOX_TIMEOUT = "SANDBOX_TIMEOUT"
    SANDBOX_RESOURCE_EXHAUSTED = "SANDBOX_RESOURCE_EXHAUSTED"
    SANDBOX_EXECUTION_FAILED = "SANDBOX_EXECUTION_FAILED"


class ContractError(ContractModel):
    contract_version: str = CONTRACT_VERSION
    run_id: Identifier
    stage: ErrorStage
    code: ErrorCode
    message: str
    retryable: bool = False
    strategy_id: Identifier | None = None
    engine_id: Identifier | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    cause_chain: tuple[str, ...] = ()


class ContractViolation(Exception):
    def __init__(self, error: ContractError) -> None:
        super().__init__(f"{error.code}: {error.message}")
        self.error = error
