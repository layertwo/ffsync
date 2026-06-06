#!/usr/bin/env bash
# Regenerate pydantic models from smithy.
#
# Local dev: runs `smithy build` (CLI, brew install smithy-cli) and emits
# OpenAPI under smithy/build/smithy/, then runs datamodel-codegen.
#
# CI: set SMITHY_BUILD_DIR to a directory of pre-built smithy openapi/<svc>/
# artifacts (e.g. the output of `./gradlew smithyBuild`). The smithy build
# step is then skipped.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SMITHY_DIR="$REPO_ROOT/smithy"
SMITHY_BUILD_DIR="${SMITHY_BUILD_DIR:-$SMITHY_DIR/build/smithy}"
GENERATED_DIR="$REPO_ROOT/lambda/src/shared/generated"

# datamodel-codegen ships in the lambda dev dep group. The caller is expected
# to have installed it (e.g. `uv sync --group dev` locally, or
# `uv pip install --group dev .` in CI) so it's on PATH.
if ! command -v datamodel-codegen >/dev/null; then
  # Fall back to running through uv if we're in a project venv.
  if command -v uv >/dev/null; then
    DMG=(uv run --quiet datamodel-codegen)
  else
    echo "datamodel-codegen not found on PATH and uv not installed."
    echo "Run 'uv sync --group dev' from lambda/ first."
    exit 1
  fi
else
  DMG=(datamodel-codegen)
fi

if ! ls "$SMITHY_BUILD_DIR"/*/openapi/*.openapi.json >/dev/null 2>&1; then
  command -v smithy >/dev/null || {
    echo "smithy CLI not found (brew install smithy-cli), and no prebuilt"
    echo "artifacts at $SMITHY_BUILD_DIR. Set SMITHY_BUILD_DIR to a directory"
    echo "of openapi/<svc>/*.openapi.json files, or install the smithy CLI."
    exit 1
  }
  echo "==> smithy build"
  (cd "$SMITHY_DIR" && rm -rf build && smithy build)
fi

# Stage all per-service OpenAPI files into a single input directory so
# datamodel-codegen can produce all modules in one pass — which also lets
# it dedup shared shapes into a generated `shared.py`. The input filename
# stem drives the output module name (dots → underscores).
STAGE_DIR="$(mktemp -d -t ffsync-openapi-XXXXXX)"
trap 'rm -rf "$STAGE_DIR"' EXIT
for svc in storage auth token profile; do
  Svc="$(tr '[:lower:]' '[:upper:]' <<< "${svc:0:1}")${svc:1}"
  cp "$SMITHY_BUILD_DIR/${svc}/openapi/${Svc}Service.openapi.json" \
     "$STAGE_DIR/${svc}_models.json"
done

rm -rf "$GENERATED_DIR"
mkdir -p "$GENERATED_DIR"

echo "==> codegen: $STAGE_DIR -> $GENERATED_DIR"
(cd "$REPO_ROOT/lambda" && "${DMG[@]}" \
  --input "$STAGE_DIR" \
  --input-file-type openapi \
  --output "$GENERATED_DIR" \
  --output-model-type pydantic_v2.BaseModel \
  --formatters isort black \
  --use-default \
  --use-standard-collections \
  --use-union-operator \
  --use-double-quotes \
  --allow-extra-fields \
  --snake-case-field \
  --use-annotated \
  --target-python-version 3.14 \
  --base-class src.shared._codegen_base.GeneratedBaseModel \
  --collapse-root-models \
  --collapse-reuse-models \
  --skip-root-model \
  --reuse-model \
  --reuse-scope tree \
  --use-type-alias \
  --disable-timestamp)

echo "==> done"
