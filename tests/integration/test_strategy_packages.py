from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from psrc.cli import main
from psrc.contract.errors import ContractViolation, ErrorCode
from psrc.contract.models import SandboxMode, StrategyKind
from psrc.runtime.package import (
    discover_strategy_packages,
    export_strategy_packages,
    load_strategy,
)
from psrc.runtime.report import RunBundle
from psrc.strategies.catalog import all_examples


def test_eighteen_independent_packages_discover_and_load(tmp_path: Path) -> None:
    export_strategy_packages(tmp_path, tuple(item.manifest for item in all_examples()))
    packages = discover_strategy_packages(tmp_path)
    assert len(packages) == 18
    counts = {kind: 0 for kind in StrategyKind}
    for package in packages:
        strategy = load_strategy(package, sandbox_mode=SandboxMode.DEVELOPMENT)
        assert strategy.manifest == package.manifest
        assert package.manifest.entrypoint == "strategy.py:Strategy"
        assert (package.root / "strategy.py").is_file()
        assert (package.root / "STRATEGY_CARD.md").is_file()
        counts[StrategyKind(package.manifest.kind)] += 1
    assert set(counts.values()) == {6}


def test_strict_package_load_never_falls_back_to_host_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    export_strategy_packages(tmp_path, (all_examples()[0].manifest,))
    package = discover_strategy_packages(tmp_path)[0]
    monkeypatch.delenv("PSRC_SANDBOX_ATTESTATION", raising=False)
    with pytest.raises(ContractViolation) as raised:
        load_strategy(package, sandbox_mode=SandboxMode.STRICT_CONTAINER)
    assert raised.value.error.code == ErrorCode.SANDBOX_UNAVAILABLE
    assert raised.value.error.details["fallback_used"] is False


def test_package_source_policy_is_enforced_before_import(tmp_path: Path) -> None:
    export_strategy_packages(tmp_path, (all_examples()[0].manifest,))
    (tmp_path / all_examples()[0].manifest.strategy_id / "strategy.py").write_text(
        "import socket\n", encoding="utf-8"
    )
    package = discover_strategy_packages(tmp_path)[0]
    with pytest.raises(ContractViolation) as raised:
        load_strategy(package, sandbox_mode=SandboxMode.DEVELOPMENT)
    assert raised.value.error.code == ErrorCode.SANDBOX_POLICY_DENIED
    assert raised.value.error.details["fallback_used"] is False


def test_source_change_after_discovery_fails_before_import(tmp_path: Path) -> None:
    export_strategy_packages(tmp_path, (all_examples()[0].manifest,))
    package = discover_strategy_packages(tmp_path)[0]
    (package.root / "strategy.py").write_text("raise RuntimeError('changed')\n", encoding="utf-8")
    with pytest.raises(ContractViolation) as raised:
        load_strategy(package, sandbox_mode=SandboxMode.DEVELOPMENT)
    assert raised.value.error.code == ErrorCode.SOURCE_HASH_MISMATCH
    assert raised.value.error.details["fallback_used"] is False


def test_standalone_external_strategy_directory_executes_without_catalog(
    tmp_path: Path,
) -> None:
    generated_root = tmp_path / "generated"
    assert main(["package", "export", "--output", str(generated_root)]) == 0
    generated = next(
        package
        for package in discover_strategy_packages(generated_root)
        if package.manifest.strategy_id == "rule.sma_cross"
    )

    package_root = tmp_path / "paper-authored-strategy"
    package_root.mkdir()
    external_manifest = generated.manifest.model_copy(
        update={"strategy_id": "rule.external_standalone"}
    )
    (package_root / "strategy.yaml").write_text(
        yaml.safe_dump(
            external_manifest.model_dump(mode="json"),
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    for filename in ("dataset-manifest.json", "input-events.json"):
        (package_root / filename).write_bytes((generated.root / filename).read_bytes())

    source = f'''from psrc.contract.models import StrategyManifest
from psrc.domain.actions import TargetPosition


class Strategy:
    manifest = StrategyManifest.model_validate_json({external_manifest.model_dump_json()!r})

    def on_start(self):
        self.event_count = 0

    def on_event(self, event, account):
        del account
        self.event_count += 1
        target = "1" if self.event_count % 2 else "-1"
        return (TargetPosition(
            instrument_id=event.instrument_id,
            quantity=target,
            reason_code="signal.external_standalone",
        ),)

    def on_finish(self):
        pass
'''
    assert "psrc.strategies" not in source
    assert "psrc.examples" not in source
    (package_root / "strategy.py").write_text(source, encoding="utf-8")

    output = tmp_path / "external-run"
    assert (
        main(
            [
                "run",
                "--strategy-dir",
                str(package_root),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    bundle = RunBundle.model_validate_json((output / "bundle.json").read_text(encoding="utf-8"))
    assert bundle.strategy_manifest == external_manifest
    assert bundle.strategy_code_evidence is not None
    assert bundle.strategy_code_evidence.package_files[0].path == "strategy.py"
    assert (output / "strategy-code-evidence.json").is_file()
    assert bundle.report.execution_plan.strategy_code_evidence_sha256 is not None
    assert bundle.report.run_id == "package.rule.external_standalone"
    assert bundle.report.metrics.fills > 0
