from __future__ import annotations

import json
from pathlib import Path

from psrc.authoring.audit import audit_manifest
from psrc.authoring.models import PaperAmbiguity, PaperReference, PaperStrategySpec
from psrc.cli import main
from psrc.contract.models import StrategyKind
from psrc.examples.sma_cross import SmaCrossStrategy


def _spec(*, blocking: bool) -> PaperStrategySpec:
    manifest = SmaCrossStrategy.manifest
    return PaperStrategySpec(
        spec_id="paper.sma-demo",
        reference=PaperReference(
            title="Synthetic moving-average demonstration",
            locator="docs://synthetic/sma",
            citation="PSRC synthetic example",
        ),
        strategy_kind=StrategyKind.RULE,
        hypothesis="Short-window strength relative to long-window strength predicts direction.",
        data_requirements=manifest.data_requirements,
        output_actions=manifest.action_requirements.allowed,
        execution_assumptions=("Signals use closed bars only.",),
        ambiguities=(
            PaperAmbiguity(
                ambiguity_id="fill-timing",
                severity="blocking" if blocking else "info",
                statement="The paper does not define fill timing.",
                resolution=None if blocking else "Use next-event execution.",
                resolved_by=None if blocking else "operator",
            ),
        ),
    )


def test_authoring_agent_cannot_hide_blocking_ambiguity() -> None:
    report = audit_manifest(_spec(blocking=True), SmaCrossStrategy.manifest)
    assert report.approved_for_compilation is False
    assert report.runtime_authority_granted is False
    assert {issue.code for issue in report.issues} == {"AUTHORING_AMBIGUITY_UNRESOLVED"}


def test_resolved_spec_can_be_promoted_to_normal_compiler_review() -> None:
    report = audit_manifest(_spec(blocking=False), SmaCrossStrategy.manifest)
    assert report.approved_for_compilation is True
    assert report.issues == ()


def test_authoring_audit_is_available_as_machine_readable_cli(tmp_path: Path) -> None:
    spec_path = tmp_path / "paper-spec.json"
    manifest_path = tmp_path / "strategy-manifest.json"
    output = tmp_path / "agent-audit-report.json"
    spec_path.write_text(_spec(blocking=False).model_dump_json(indent=2), encoding="utf-8")
    manifest_path.write_text(
        SmaCrossStrategy.manifest.model_dump_json(indent=2), encoding="utf-8"
    )
    assert (
        main(
            [
                "author",
                "audit",
                "--spec",
                str(spec_path),
                "--manifest",
                str(manifest_path),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["approved_for_compilation"] is True
    assert payload["runtime_authority_granted"] is False


def test_authoring_cli_fails_closed_on_blocking_ambiguity(tmp_path: Path) -> None:
    spec_path = tmp_path / "blocked-spec.json"
    manifest_path = tmp_path / "strategy-manifest.json"
    output = tmp_path / "agent-audit-report.json"
    spec_path.write_text(_spec(blocking=True).model_dump_json(indent=2), encoding="utf-8")
    manifest_path.write_text(
        SmaCrossStrategy.manifest.model_dump_json(indent=2), encoding="utf-8"
    )
    assert (
        main(
            [
                "author",
                "audit",
                "--spec",
                str(spec_path),
                "--manifest",
                str(manifest_path),
                "--output",
                str(output),
            ]
        )
        == 4
    )
    assert json.loads(output.read_text())["approved_for_compilation"] is False
