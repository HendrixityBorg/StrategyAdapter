from __future__ import annotations

from psrc.authoring.models import AgentAuditIssue, AgentAuditReport, PaperStrategySpec
from psrc.contract.models import StrategyKind, StrategyManifest, TrainingMode


def audit_manifest(spec: PaperStrategySpec, manifest: StrategyManifest) -> AgentAuditReport:
    """Deterministically audit agent-authored metadata before runtime compilation."""
    issues: list[AgentAuditIssue] = []
    if spec.strategy_kind != manifest.kind:
        issues.append(
            AgentAuditIssue(
                code="AUTHORING_KIND_MISMATCH",
                severity="error",
                path="kind",
                message="Paper spec and strategy manifest declare different strategy kinds",
            )
        )
    if spec.data_requirements != manifest.data_requirements:
        issues.append(
            AgentAuditIssue(
                code="AUTHORING_DATA_CONTRACT_MISMATCH",
                severity="error",
                path="data_requirements",
                message="Paper-derived data contract changed before compilation",
            )
        )
    if not spec.output_actions.issuperset(manifest.action_requirements.allowed):
        issues.append(
            AgentAuditIssue(
                code="AUTHORING_ACTION_EXPANSION",
                severity="error",
                path="action_requirements.allowed",
                message="Manifest requests actions not justified by the paper spec",
            )
        )
    trainable = manifest.kind != StrategyKind.RULE
    training_required = manifest.lifecycle.training == TrainingMode.REQUIRED
    if trainable != training_required:
        issues.append(
            AgentAuditIssue(
                code="AUTHORING_TRAINING_MISMATCH",
                severity="error",
                path="lifecycle.training",
                message="Strategy kind and training lifecycle are inconsistent",
            )
        )
    if manifest.kind == StrategyKind.SUPERVISED and spec.label_definition is None:
        issues.append(
            AgentAuditIssue(
                code="AUTHORING_LABEL_UNSPECIFIED",
                severity="error",
                path="label_definition",
                message="A supervised paper spec must define its training label",
            )
        )
    if manifest.kind == StrategyKind.REINFORCEMENT_LEARNING and spec.reward_definition is None:
        issues.append(
            AgentAuditIssue(
                code="AUTHORING_REWARD_UNSPECIFIED",
                severity="error",
                path="reward_definition",
                message="An RL paper spec must define its reward",
            )
        )
    for ambiguity in spec.ambiguities:
        if ambiguity.severity == "blocking" and ambiguity.resolution is None:
            issues.append(
                AgentAuditIssue(
                    code="AUTHORING_AMBIGUITY_UNRESOLVED",
                    severity="error",
                    path=f"ambiguities.{ambiguity.ambiguity_id}",
                    message=ambiguity.statement,
                )
            )
    return AgentAuditReport(
        spec_id=spec.spec_id,
        strategy_id=manifest.strategy_id,
        approved_for_compilation=not any(issue.severity == "error" for issue in issues),
        issues=tuple(issues),
    )
