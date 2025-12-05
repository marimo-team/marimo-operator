#!/bin/bash
# Test script for kubectl-marimo plugin
# Usage: ./scripts/test-plugin.sh
# Tests CLI commands with --dry-run to verify YAML generation

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PLUGIN_DIR="$PROJECT_DIR/plugin"
EXAMPLES_DIR="$PROJECT_DIR/examples"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() { echo -e "${GREEN}[PASS]${NC} $1"; }
info() { echo -e "${BLUE}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[FAIL]${NC} $1"; }

PASSED=0
FAILED=0

# Create temp directory for test files
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

# Create test notebook
cat > "$TMPDIR/test.py" << 'EOF'
import marimo

app = marimo.App()

@app.cell
def hello():
    return "Hello, World!"

if __name__ == "__main__":
    app.run()
EOF

# Create test notebook with frontmatter
cat > "$TMPDIR/with-frontmatter.py" << 'EOF'
# /// script
# dependencies = ["marimo", "pandas"]
# ///
# [tool.marimo.k8s]
# storage = "5Gi"
# image = "custom:latest"

import marimo

app = marimo.App()

@app.cell
def hello():
    return "Hello!"

if __name__ == "__main__":
    app.run()
EOF

# Create markdown notebook
cat > "$TMPDIR/notebook.md" << 'EOF'
---
title: test-markdown
storage: 2Gi
auth: none
env:
  DEBUG: "true"
  API_KEY:
    secret: my-secret
    key: api-key
mounts:
  - cw://bucket/data
---

# Test Notebook

```python {.marimo}
print("hello")
```
EOF

run_test() {
    local name="$1"
    local cmd="$2"
    local check="$3"

    info "Testing: $name"

    output=$(cd "$PLUGIN_DIR" && uv run $cmd 2>&1) || {
        error "$name - command failed"
        echo "$output"
        FAILED=$((FAILED + 1))
        return 1
    }

    if echo "$output" | grep -q -- "$check"; then
        log "$name"
        PASSED=$((PASSED + 1))
    else
        error "$name - expected '$check' in output"
        echo "$output"
        FAILED=$((FAILED + 1))
    fi
}

yaml_contains() {
    local name="$1"
    local cmd="$2"
    shift 2
    local checks=("$@")

    info "Testing: $name"

    output=$(cd "$PLUGIN_DIR" && uv run $cmd 2>&1) || {
        error "$name - command failed"
        echo "$output"
        FAILED=$((FAILED + 1))
        return 1
    }

    local all_pass=true
    for check in "${checks[@]}"; do
        if ! echo "$output" | grep -q "$check"; then
            error "$name - expected '$check' in output"
            all_pass=false
        fi
    done

    if $all_pass; then
        log "$name"
        PASSED=$((PASSED + 1))
    else
        echo "$output"
        FAILED=$((FAILED + 1))
    fi
}

echo ""
echo "=============================================="
echo "  kubectl-marimo Plugin Tests"
echo "=============================================="
echo ""

# Test 1: Help command
run_test "CLI help" "kubectl-marimo --help" "Deploy marimo notebooks"

# Test 2: Edit command exists
run_test "edit command help" "kubectl-marimo edit --help" "Create or edit notebooks"

# Test 3: Run command exists
run_test "run command help" "kubectl-marimo run --help" "Run a notebook as a read-only"

# Test 4: Basic edit dry-run
yaml_contains "edit dry-run (basic)" \
    "kubectl-marimo edit $TMPDIR/test.py --dry-run" \
    "apiVersion: marimo.io/v1alpha1" \
    "kind: MarimoNotebook" \
    "mode: edit" \
    "storage:"

# Test 5: Run mode
yaml_contains "run dry-run (mode=run)" \
    "kubectl-marimo run $TMPDIR/test.py --dry-run" \
    "mode: run"

# Test 6: Source flag adds mounts
yaml_contains "edit with --source" \
    "kubectl-marimo edit --source=cw://bucket/data $TMPDIR/test.py --dry-run" \
    "mounts:" \
    "cw://bucket/data"

# Test 7: Frontmatter parsing (Python)
yaml_contains "frontmatter parsing (Python)" \
    "kubectl-marimo edit $TMPDIR/with-frontmatter.py --dry-run" \
    "storage:" \
    "size: 5Gi" \
    "image: custom:latest"

# Test 8: Frontmatter parsing (Markdown with env)
yaml_contains "frontmatter parsing (Markdown + env)" \
    "kubectl-marimo edit $TMPDIR/notebook.md --dry-run" \
    "name: test-markdown" \
    "storage:" \
    "size: 2Gi" \
    "auth: {}" \
    "env:" \
    "DEBUG" \
    "mounts:"

# Test 9: Namespace option
yaml_contains "namespace option" \
    "kubectl-marimo edit -n staging $TMPDIR/test.py --dry-run" \
    "namespace: staging"

# Test 10: Default storage (1Gi)
yaml_contains "default storage is 1Gi" \
    "kubectl-marimo edit $TMPDIR/test.py --dry-run" \
    "size: 1Gi"

# Test 11: Sync command exists
run_test "sync command help" "kubectl-marimo sync --help" "Pull changes from pod"

# Test 12: Delete command exists
run_test "delete command help" "kubectl-marimo delete --help" "delete cluster resources"

# Test 13: Status command exists
run_test "status command help" "kubectl-marimo status --help" "List active notebook"

# Test 14: Headless flag exists
run_test "headless flag (edit)" "kubectl-marimo edit --help" "--headless"
run_test "headless flag (run)" "kubectl-marimo run --help" "--headless"

echo ""
echo "=============================================="
echo "  Results: $PASSED passed, $FAILED failed"
echo "=============================================="
echo ""

if [ $FAILED -gt 0 ]; then
    exit 1
fi

exit 0
