#!/usr/bin/env bash
set -euo pipefail
uv version --directory plugin --no-sync "$1"
python3 scripts/release-metadata.py --sync
