.PHONY: bootstrap lint test schema packages examples failures adapters compatibility acceptance check verify container-build verify-container

EVIDENCE_DIR ?= reports/generated
HOST_UID := $(shell id -u)
HOST_GID := $(shell id -g)

bootstrap:
	uv sync --frozen --extra dev --extra adapters

lint:
	uv run ruff check .
	uv run mypy src tests

test:
	mkdir -p $(EVIDENCE_DIR)
	uv run pytest -q --junitxml=$(EVIDENCE_DIR)/junit.xml --cov=psrc --cov-report=json:$(EVIDENCE_DIR)/coverage.json --cov-fail-under=90

schema:
	uv run psrc schema export --output schemas/generated

packages:
	uv run psrc package export --output strategies

examples:
	uv run psrc demo all --output $(EVIDENCE_DIR)/runs/all

failures:
	uv run psrc demo failures --output $(EVIDENCE_DIR)/runs/failures

adapters:
	uv run psrc demo adapters --output $(EVIDENCE_DIR)/runs/adapters

compatibility:
	uv run psrc demo compatibility --output $(EVIDENCE_DIR)/runs/compatibility

acceptance:
	uv run psrc verify --matrix ACCEPTANCE_MATRIX.yaml --evidence-root $(EVIDENCE_DIR) --output $(EVIDENCE_DIR)/acceptance-report.json

check: lint test schema

verify: bootstrap lint schema packages test examples failures adapters compatibility acceptance

container-build:
	docker build --tag psrc-verifier:local .

verify-container: container-build
	mkdir -p $(EVIDENCE_DIR)
	docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges:true --pids-limit 64 --memory 1g --cpus 2 --user $(HOST_UID):$(HOST_GID) --tmpfs /tmp:rw,noexec,nosuid,nodev,size=256m --mount type=bind,src=$(abspath $(EVIDENCE_DIR)),dst=/psrc/reports --entrypoint bash psrc-verifier:local /app/scripts/verify-container.sh /psrc/reports
