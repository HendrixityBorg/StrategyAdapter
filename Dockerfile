FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH=/app/.venv/bin:$PATH \
    PSRC_STRICT_SANDBOX=1 \
    PSRC_SANDBOX_ATTESTATION=strict-container-v1

WORKDIR /app

COPY pyproject.toml uv.lock README.md CHANGELOG.md LICENSE /app/
COPY src /app/src
RUN python -m pip install --no-cache-dir uv==0.12.7 \
    && uv sync --frozen --extra dev --extra adapters

COPY spec /app/spec
COPY docs /app/docs
COPY schemas /app/schemas
COPY tests /app/tests
COPY strategies /app/strategies
COPY engine_profiles /app/engine_profiles
COPY scripts /app/scripts
COPY ACCEPTANCE_MATRIX.yaml Makefile Dockerfile .dockerignore /app/

RUN mkdir -p /psrc/data /psrc/artifacts /psrc/reports \
    && chown -R 65532:65532 /psrc

USER 65532:65532

ENTRYPOINT ["psrc"]
