from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from psrc.cli import main
from psrc.runtime.report import RunBundle
from psrc.sandbox.container import DockerSandbox


def test_cli_builds_complete_reproduction_bundle(tmp_path: Path, capsys: object) -> None:
    del capsys
    repository = Path(__file__).parents[2]
    schemas = tmp_path / "schemas"
    packages = tmp_path / "packages"
    evidence = tmp_path / "evidence"

    assert main(["schema", "export", "--output", str(schemas)]) == 0
    assert len(json.loads((schemas / "catalog.json").read_text())["schemas"]) >= 20
    assert main(["package", "export", "--output", str(packages)]) == 0
    assert len(list(packages.glob("*/strategy.yaml"))) == 18
    assert len(list(packages.glob("*/strategy.py"))) == 18
    assert len(list(packages.glob("*/input-events.json"))) == 18

    sample_manifest = packages / "rule.sma_cross/strategy.yaml"
    assert main(["validate", "strategy-manifest", str(sample_manifest)]) == 0
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("strategy_id: broken\n", encoding="utf-8")
    assert main(["validate", "strategy-manifest", str(invalid)]) == 2

    assert main(["demo", "sma", "--output", str(evidence / "runs/sma")]) == 0
    bundle_payload = json.loads((evidence / "runs/sma/bundle.json").read_text(encoding="utf-8"))
    RunBundle.model_validate(bundle_payload)
    tampered_input = json.loads(
        (evidence / "runs/sma/bundle.json").read_text(encoding="utf-8")
    )
    tampered_input["input_evidence"]["source_events"][0]["payload"]["close"] = "999"
    with pytest.raises(ValidationError):
        RunBundle.model_validate(tampered_input)
    bundle_payload["report"]["execution_plan"]["strategy_id"] = "rule.mismatched"
    with pytest.raises(ValidationError):
        RunBundle.model_validate(bundle_payload)
    assert (
        main(
            [
                "run",
                "--strategy-dir",
                str(packages / "rule.sma_cross"),
                "--output",
                str(evidence / "runs/single-package"),
            ]
        )
        == 0
    )
    package_bundle_path = evidence / "runs/single-package/bundle.json"
    package_bundle = json.loads(package_bundle_path.read_text(encoding="utf-8"))
    assert package_bundle["strategy_code_evidence"]["package_files"]
    assert package_bundle["report"]["execution_plan"][
        "strategy_code_evidence_sha256"
    ]
    package_bundle["strategy_code_evidence"]["package_files"][0]["sha256"] = "f" * 64
    with pytest.raises(ValidationError):
        RunBundle.model_validate(package_bundle)
    assert (
        main(
            [
                "demo",
                "all",
                "--output",
                str(evidence / "runs/all"),
                "--strategies-root",
                str(packages),
            ]
        )
        == 0
    )
    assert main(["demo", "failures", "--output", str(evidence / "runs/failures")]) == 0
    assert main(["demo", "adapters", "--output", str(evidence / "runs/adapters")]) == 0
    assert (
        main(["demo", "compatibility", "--output", str(evidence / "runs/compatibility")])
        == 0
    )

    (evidence / "junit.xml").write_text(
        '<testsuites><testsuite tests="100" failures="0" errors="0" skipped="0"/></testsuites>',
        encoding="utf-8",
    )
    (evidence / "coverage.json").write_text(
        json.dumps({"totals": {"percent_covered": 90}}), encoding="utf-8"
    )
    acceptance_report = evidence / "acceptance-report.json"
    assert (
        main(
            [
                "verify",
                "--matrix",
                str(repository / "ACCEPTANCE_MATRIX.yaml"),
                "--evidence-root",
                str(evidence),
                "--output",
                str(acceptance_report),
            ]
        )
        == 0
    )
    assert json.loads(acceptance_report.read_text(encoding="utf-8"))["status"] == "passed"


def test_verification_cli_fails_closed_when_evidence_is_absent(tmp_path: Path) -> None:
    repository = Path(__file__).parents[2]
    output = tmp_path / "failed-verification.json"
    assert (
        main(
            [
                "verify",
                "--matrix",
                str(repository / "ACCEPTANCE_MATRIX.yaml"),
                "--evidence-root",
                str(tmp_path / "absent"),
                "--output",
                str(output),
            ]
        )
        == 1
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["verifier_policy"].startswith("generated evidence only")


def test_package_cli_require_strict_never_downgrades(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    packages = tmp_path / "packages"
    output = tmp_path / "output"
    assert main(["package", "export", "--output", str(packages)]) == 0
    monkeypatch.setattr(
        DockerSandbox, "current_process_attested", classmethod(lambda cls: False)
    )
    assert (
        main(
            [
                "run",
                "--strategy-dir",
                str(packages / "rule.sma_cross"),
                "--output",
                str(output),
                "--require-strict",
            ]
        )
        == 3
    )
    assert not output.exists()
