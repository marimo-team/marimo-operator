#!/bin/bash
# Test script for marimo-operator examples
# Usage: ./scripts/test-examples.sh [example-name]
# Examples: basic, ssh-sidecar, git-sync-sidecar

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
EXAMPLES_DIR="$PROJECT_DIR/examples"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

cleanup() {
    log "Cleaning up..."
    # Kill port-forward if running
    if [ -n "$PF_PID" ] && kill -0 "$PF_PID" 2>/dev/null; then
        kill "$PF_PID" 2>/dev/null || true
    fi
    # Delete the notebook
    if [ -n "$NOTEBOOK_NAME" ]; then
        kubectl delete marimo "$NOTEBOOK_NAME" -n default --ignore-not-found 2>/dev/null || true
    fi
}

trap cleanup EXIT

wait_for_pod() {
    local name=$1
    local timeout=${2:-120}
    log "Waiting for pod $name to be ready (timeout: ${timeout}s)..."

    local count=0
    while [ $count -lt $timeout ]; do
        local phase=$(kubectl get pod "$name" -n default -o jsonpath='{.status.phase}' 2>/dev/null || echo "")
        if [ "$phase" = "Running" ]; then
            # Check if all containers are ready
            local ready=$(kubectl get pod "$name" -n default -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "")
            if [ "$ready" = "True" ]; then
                log "Pod $name is ready!"
                return 0
            fi
        fi
        sleep 2
        count=$((count + 2))
        echo -n "."
    done
    echo ""
    error "Timeout waiting for pod $name"
    kubectl describe pod "$name" -n default 2>/dev/null || true
    return 1
}

test_example() {
    local example=$1
    local yaml_file="$EXAMPLES_DIR/$example/notebook.yaml"

    if [ ! -f "$yaml_file" ]; then
        error "Example not found: $yaml_file"
        return 1
    fi

    log "Testing example: $example"
    log "Applying $yaml_file..."

    # Get notebook name from yaml
    NOTEBOOK_NAME=$(grep -E '^\s+name:' "$yaml_file" | head -1 | awk '{print $2}')
    log "Notebook name: $NOTEBOOK_NAME"

    # Apply the example
    kubectl apply -f "$yaml_file"

    # Wait for pod
    if ! wait_for_pod "$NOTEBOOK_NAME" 180; then
        error "Pod failed to start"
        kubectl logs "$NOTEBOOK_NAME" -n default --all-containers 2>/dev/null || true
        return 1
    fi

    # Get marimo port from the service
    local marimo_port=$(kubectl get svc "$NOTEBOOK_NAME" -n default -o jsonpath='{.spec.ports[?(@.name=="http")].port}' 2>/dev/null || echo "2718")
    log "Marimo port: $marimo_port"

    # Start port-forward
    local local_port=8888
    log "Starting port-forward: localhost:$local_port -> $NOTEBOOK_NAME:$marimo_port"
    kubectl port-forward "svc/$NOTEBOOK_NAME" "$local_port:$marimo_port" -n default &
    PF_PID=$!
    sleep 2

    # Check if port-forward is working
    if ! kill -0 "$PF_PID" 2>/dev/null; then
        error "Port-forward failed to start"
        return 1
    fi

    log "Port-forward started (PID: $PF_PID)"

    # Show status
    log ""
    log "Marimo status:"
    kubectl get marimo "$NOTEBOOK_NAME" -n default -o wide

    log ""
    log "Pod status:"
    kubectl get pod "$NOTEBOOK_NAME" -n default -o wide

    # Check if there are sidecar ports
    local sidecar_ports=$(kubectl get svc "$NOTEBOOK_NAME" -n default -o jsonpath='{.spec.ports[?(@.name!="http")].port}' 2>/dev/null || echo "")
    if [ -n "$sidecar_ports" ]; then
        log ""
        log "Sidecar ports available: $sidecar_ports"
        log "You can port-forward sidecars separately if needed"
    fi

    echo ""
    echo "=============================================="
    echo ""
    echo "  Marimo notebook is ready!"
    echo ""
    echo "  Open in browser: http://localhost:$local_port"
    echo ""
    echo "=============================================="
    echo ""
    echo "Press Ctrl+C to stop and cleanup..."

    # Wait for user interrupt
    wait "$PF_PID" 2>/dev/null || true
}

# Main
if [ -z "$1" ]; then
    log "Available examples:"
    for dir in "$EXAMPLES_DIR"/*/; do
        example=$(basename "$dir")
        echo "  - $example"
    done
    echo ""
    echo "Usage: $0 <example-name>"
    echo "Example: $0 basic"
    exit 0
fi

# Check prerequisites
if ! kubectl cluster-info &>/dev/null; then
    error "Cannot connect to Kubernetes cluster"
    exit 1
fi

if ! kubectl get crd marimos.marimo.io &>/dev/null; then
    error "Marimo CRD not installed. Run: make install"
    exit 1
fi

test_example "$1"
