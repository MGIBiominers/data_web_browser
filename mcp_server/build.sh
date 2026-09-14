#!/bin/bash
# Build the Lambda deployment package into build/. Run this before
# `terraform apply` (or `terraform plan`) in infra/ -- Terraform only zips
# whatever's already here, it does not run pip for you.
#
# Uses a manylinux-targeted pip install even on a Mac dev machine:
# pydantic-core (an mcp/pydantic dependency) is a compiled wheel, and a
# naive `pip install -r requirements.txt` on macOS/arm64 would bundle a
# binary incompatible with Lambda's runtime, failing only at cold start.
set -euo pipefail
cd "$(dirname "$0")"

rm -rf build
mkdir -p build

pip install \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 3.12 \
  --only-binary=:all: \
  -r requirements.txt \
  -t build/

cp *.py run.sh build/
rm -f build/conftest.py  # test-only, not needed in the deployment package
cp -r tools build/tools
cp -r resources build/resources
rm -rf build/tools/tests build/tools/__pycache__ build/resources/__pycache__

echo "Built mcp_server/build/ -- run 'terraform apply' from infra/ next."
