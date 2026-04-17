# Contributing to marimo-operator

Thank you for your interest in contributing!

## Prerequisites

| Tool | Purpose |
|------|---------|
| [Go](https://go.dev) ≥ 1.22 | Operator development |
| [uv](https://docs.astral.sh/uv/) | Python plugin development |
| [kubectl](https://kubernetes.io/docs/tasks/tools/) | Cluster interaction |
| [kind](https://kind.sigs.k8s.io/) | Local Kubernetes cluster for e2e tests |
| [golangci-lint](https://golangci-lint.run/) | Go linting |

## Development Workflow

### Operator (Go)

| Command | What it does |
|---------|-------------|
| `make test` | Run unit tests with coverage |
| `make test-e2e` | Run e2e tests on a Kind cluster (creates + tears down automatically) |
| `make fmt` | Run `go fmt` |
| `make vet` | Run `go vet` |
| `make lint` | Run golangci-lint |
| `make lint-fix` | Auto-fix lint issues |
| `make build` | Build manager binary to `bin/manager` |
| `make manifests` | Regenerate CRD YAML and RBAC from type definitions |
| `make generate` | Regenerate DeepCopy methods |
| `make build-installer` | Regenerate `deploy/install.yaml` |
| `make run` | Run controller locally against current kubeconfig |

```bash
# Run a single test
go test ./internal/controller/... -run TestReconcile -v

# Run unit tests only (skip e2e)
make test
```

**Important:** After modifying types in `api/v1alpha1/`, always run `make manifests && make generate` and commit the generated files.

### Plugin (Python)

```bash
cd plugin
uv sync --dev

# Run all tests
uv run pytest tests -v

# Run a single test file
uv run pytest tests/test_deploy.py -v

# Type checking
uv run ty check kubectl_marimo
```

### Pre-commit Hooks

Install once, then hooks run automatically on `git commit`:

```bash
pip install pre-commit
pre-commit install
```

Run manually against all files:

```bash
pre-commit run --all-files
```

## Project Structure

```
marimo-operator/
├── api/v1alpha1/          # CRD type definitions (edit here, then make manifests)
├── internal/controller/   # Reconciliation logic
├── pkg/resources/         # Pod, Service, PVC, ConfigMap builders
├── pkg/config/            # Configurable default images
├── config/                # Kustomize overlays (CRD, RBAC, manager)
├── deploy/                # Generated install.yaml (do not edit by hand)
├── test/e2e/              # E2E tests (Ginkgo)
├── plugin/                # kubectl-marimo Python plugin
│   ├── kubectl_marimo/    # CLI source
│   └── tests/             # Plugin unit tests
└── examples/              # Example deployments
```

## Submitting a Pull Request

1. Fork the repo and create a branch from `main`.
2. Make your changes and add tests for new behavior.
3. Ensure `make lint` and `make test` pass (operator) and `uv run pytest` passes (plugin).
4. If you modified CRD types, run `make manifests` and commit generated files.
5. Open a PR — the template will guide you through the checklist.

Every bug fix should include a regression test that fails before the fix and passes after.

## Release Process

Releases are for maintainers only. Tags trigger the publish workflow which builds and pushes the operator image and publishes the plugin to PyPI.
