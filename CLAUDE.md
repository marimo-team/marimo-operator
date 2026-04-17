# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Test Commands

### Operator (Go)

```bash
make test             # Unit tests with coverage
make test-e2e         # E2E tests on Kind cluster (creates cluster automatically)
make fmt              # go fmt
make vet              # go vet
make lint             # golangci-lint
make lint-fix         # Auto-fix lint issues
make build            # Build manager binary to bin/manager
make manifests        # Regenerate CRD YAML and RBAC from types
make generate         # Regenerate DeepCopy methods
make build-installer  # Regenerate deploy/install.yaml
```

### Plugin (Python)

```bash
cd plugin
uv sync --dev                        # Install dev dependencies
uv run pytest tests -v               # Run all tests
uv run pytest tests/test_deploy.py   # Run single test file
uv run ty check kubectl_marimo       # Static type checking
```

## Architecture

marimo-operator is a Kubernetes operator (Go, controller-runtime) that manages `MarimoNotebook` custom resources, plus a Python kubectl plugin (`kubectl-marimo`) for deploying individual local notebooks.

### Operator (Go)

For each `MarimoNotebook` CR the controller creates:
- **PVC** — persistent storage, **intentionally has no owner reference** (not GC'd on CR delete; requires explicit `--delete-pvc`)
- **Pod** — init container clones `spec.source` git repo into `/data`, then marimo container serves from there; sidecars share the same PVC volume
- **Service** — exposes marimo port (default 2718) and any sidecar `exposePort`s

Pod updates use a **recreate** strategy (delete + recreate); init container skips clone if `/data` already has content, preserving edits across restarts.

Key files:
- `api/v1alpha1/marimonotebook_types.go` — CRD schema (all spec fields with defaults)
- `internal/controller/marimonotebook_controller.go` — reconciliation loop
- `pkg/resources/pod.go` — Pod construction (init container, sidecars, mounts)
- `pkg/config/images.go` — configurable default images via env vars

Configurable default images (set as env vars on the operator deployment):

| Env Var | Default | Purpose |
|---------|---------|---------|
| `DEFAULT_INIT_IMAGE` | `busybox:1.36` | copy-content init container |
| `GIT_IMAGE` | `alpine/git:latest` | git clone |
| `ALPINE_IMAGE` | `alpine:latest` | sshfs/rsync sidecars |
| `S3FS_IMAGE` | `ghcr.io/marimo-team/marimo-operator/s3fs:latest` | cw:// mounts |
| `S3_ENDPOINT` | `https://cwobject.com` | CoreWeave S3 endpoint |

### Plugin (Python)

`kubectl-marimo` reads local `.py`/`.md` notebooks, uploads content to a ConfigMap, creates the `MarimoNotebook` CR, then port-forwards for interactive access. State is tracked in swap files (`.notebook.py.marimo`).

Key files:
- `plugin/kubectl_marimo/deploy.py` — orchestrates edit/run flows
- `plugin/kubectl_marimo/resources.py` — builds MarimoNotebook CR from frontmatter
- `plugin/kubectl_marimo/formats/` — parsers for `.py` (inline TOML) and `.md` (YAML frontmatter)
- `plugin/kubectl_marimo/swap.py` — tracks deployed notebooks for sync/delete

Notebook configuration is embedded in frontmatter:

```python
# /// script
# dependencies = ["marimo", "torch"]
#
# [tool.marimo.k8s]
# storage = "5Gi"
#
# [tool.marimo.k8s.resources]
# limits."nvidia.com/gpu" = 1
# ///
```

## CoreWeave (CKS) Specifics

### GPU Workloads

Use `podOverrides.nodeSelector` to target GPU node pools:

```yaml
spec:
  resources:
    limits:
      nvidia.com/gpu: 2
  podOverrides:
    nodeSelector:
      compute.coreweave.com/node-pool: gpu-node-pool
```

Or via notebook frontmatter:
```python
# [tool.marimo.k8s.resources]
# limits."nvidia.com/gpu" = 2
```

See `plugin/nccl-all-reduce.yaml` for a multi-GPU NCCL all-reduce benchmark example.

### CoreWeave Object Storage (`cw://`)

`cw://` mounts attach CoreWeave S3 buckets via an s3fs sidecar (FUSE). The plugin auto-creates the `cw-credentials` secret from `~/.s3cfg`.

**Setup:**
```bash
# 1. Create access policy, bucket, and token via cwic
cwic cwobject policy create -f cw-policy.json
cwic cwobject mb my-bucket
cwic cwobject token create --name marimo-s3 --duration Permanent

# 2. Configure ~/.s3cfg
cat > ~/.s3cfg << EOF
[default]
access_key = CWXXXXXXXXXX
secret_key = cwXXXXXXXXXXXX
host_base = cwobject.com
host_bucket = %(bucket)s.cwobject.com
use_https = True
EOF

# 3. Deploy with mount (auto-creates cw-credentials secret)
kubectl marimo edit --source=cw://my-bucket notebook.py
```

Credentials are read from `~/.s3cfg` sections in priority order: `[namespace]` > `[marimo]` > `[default]`. This allows per-namespace credentials in multi-tenant clusters.

For LOTA-optimized access from GPU nodes, override the S3 endpoint:
```bash
kubectl set env deployment/marimo-operator-controller-manager \
  -n marimo-operator-system \
  S3_ENDPOINT=http://cwlota.com
```

Mounted buckets are accessible at `/home/marimo/notebooks/mounts/cw-0/` (cw-1/, cw-2/ for additional mounts).

See `plugin/docs/cw-mounts.md` for full setup, multi-tenancy, and troubleshooting.
