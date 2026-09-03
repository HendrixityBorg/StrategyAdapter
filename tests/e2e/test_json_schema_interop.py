from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from psrc.authoring.audit import audit_manifest
from psrc.authoring.models import PaperReference, PaperStrategySpec
from psrc.cli import main
from psrc.contract.errors import ContractError, ErrorCode, ErrorStage
from psrc.contract.models import StrategyManifest
from psrc.runtime.report import FailureReport


def _references(value: Any) -> tuple[str, ...]:
    if isinstance(value, dict):
        own = (value["$ref"],) if isinstance(value.get("$ref"), str) else ()
        return own + tuple(
            reference for item in value.values() for reference in _references(item)
        )
    if isinstance(value, list):
        return tuple(reference for item in value for reference in _references(item))
    return ()


def test_all_public_schemas_validate_real_documents_without_a_registry(
    tmp_path: Path,
) -> None:
    schemas = tmp_path / "schemas"
    packages = tmp_path / "packages"
    run_output = tmp_path / "run"
    assert main(["schema", "export", "--output", str(schemas)]) == 0
    assert main(["package", "export", "--output", str(packages)]) == 0
    assert (
        main(
            [
                "run",
                "--strategy-dir",
                str(packages / "supervised.ridge_return"),
                "--output",
                str(run_output),
            ]
        )
        == 0
    )

    bundle = json.loads((run_output / "bundle.json").read_text(encoding="utf-8"))
    report = bundle["report"]
    strategy = StrategyManifest.model_validate(bundle["strategy_manifest"])
    paper_spec = PaperStrategySpec(
        spec_id="paper.external-schema-validation",
        reference=PaperReference(
            title="Independent schema validation fixture",
            locator="fixture://external-schema-validation",
            citation="StrategyAdapter interoperability fixture",
        ),
        strategy_kind=strategy.kind,
        hypothesis="A structured external strategy document is independently validatable.",
        data_requirements=strategy.data_requirements,
        output_actions=strategy.action_requirements.allowed,
        label_definition="One-step signed return.",
        execution_assumptions=("Closed bars only.",),
    )
    agent_audit = audit_manifest(paper_spec, strategy)
    now = datetime.now(UTC)
    error = ContractError(
        run_id="schema.external-failure",
        stage=ErrorStage.BACKTEST,
        code=ErrorCode.BACKTEST_FAILED,
        message="Independent validation fixture",
    )
    failure = FailureReport(
        run_id=error.run_id,
        started_at=now,
        finished_at=now,
        error=error,
    )

    samples: dict[str, object] = {
        "strategy-manifest": bundle["strategy_manifest"],
        "dataset-manifest": bundle["dataset_manifest"],
        "engine-capabilities": bundle["engine_capabilities"],
        "run-policy": bundle["run_policy"],
        "execution-plan": report["execution_plan"],
        "contract-error": error.model_dump(mode="json"),
        "artifact-manifest": report["artifacts"][0],
        "training-request": bundle["training_request"],
        "run-report": report,
        "failure-report": failure.model_dump(mode="json"),
        "unified-run-report": report,
        "run-bundle": bundle,
        "run-input-evidence": bundle["input_evidence"],
        "strategy-code-evidence": bundle["strategy_code_evidence"],
        "market-event": bundle["input_evidence"]["source_events"][0],
        "account-snapshot": report["account_snapshots"][0],
        "action": report["decisions"][0]["actions"][0],
        "fill": report["fills"][0],
        "decision-record": report["decisions"][0],
        "runtime-log-record": report["logs"][0],
        "paper-strategy-spec": paper_spec.model_dump(mode="json"),
        "agent-audit-report": agent_audit.model_dump(mode="json"),
    }
    catalog = json.loads((schemas / "catalog.json").read_text(encoding="utf-8"))
    assert set(samples) == set(catalog["schemas"])

    for name, filename in catalog["schemas"].items():
        schema = json.loads((schemas / filename).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        assert all(reference.startswith("#/$defs/") for reference in _references(schema))
        Draft202012Validator(schema).validate(samples[name])
