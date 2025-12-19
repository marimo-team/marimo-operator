# kubectl-marimo

Deploy marimo notebooks to Kubernetes.

## Installation

```bash
# With uv (recommended)
uv tool install kubectl-marimo

# With uvx (no install)
uvx kubectl-marimo edit notebook.py

# With pip
pip install kubectl-marimo
```

## Quick Start

```bash
# Edit a notebook interactively
kubectl marimo edit notebook.py

# Run as read-only app
kubectl marimo run notebook.py

# With cloud storage
kubectl marimo edit --source=cw://my-bucket/data notebook.py

# Sync changes back
kubectl marimo sync notebook.py

# Delete deployment
kubectl marimo delete notebook.py

# List active deployments
kubectl marimo status
```

## Commands

### edit

Create or edit notebooks in the cluster (interactive mode).

```bash
kubectl marimo edit [OPTIONS] [FILE]
```

Options:
- `-n, --namespace` - Kubernetes namespace (default: "default")
- `--source` - Data source URI (cw://, sshfs://, rsync://)
- `--dry-run` - Print YAML without applying
- `-f, --force` - Overwrite without prompting

Examples:
```bash
# Edit existing notebook
kubectl marimo edit notebook.py

# Edit with S3 data mounted
kubectl marimo edit --source=cw://bucket/data notebook.py

# Edit in staging namespace
kubectl marimo edit -n staging notebook.py
```

### run

Run a notebook as a read-only application.

```bash
kubectl marimo run [OPTIONS] FILE
```

Options: Same as `edit`

Examples:
```bash
# Run notebook as app
kubectl marimo run dashboard.py

# Run with data source
kubectl marimo run --source=cw://bucket/reports dashboard.py
```

### sync

Pull changes from pod back to local file.

```bash
kubectl marimo sync [OPTIONS] FILE
```

Options:
- `-n, --namespace` - Kubernetes namespace
- `-f, --force` - Overwrite local file without prompting

### delete

Delete notebook deployment from cluster.

```bash
kubectl marimo delete [OPTIONS] FILE
```

Options:
- `-n, --namespace` - Kubernetes namespace
- `--delete-pvc` - Also delete PersistentVolumeClaim (PVC is preserved by default)
- `--no-sync` - Delete without syncing changes back

### status

List active notebook deployments.

```bash
kubectl marimo status [DIRECTORY]
```

## Configuration

Configure deployments via frontmatter in your notebook.

### Markdown (.md)

```yaml
---
title: my-analysis
image: ghcr.io/marimo-team/marimo:latest
storage: 5Gi
env:
  DEBUG: "true"
  API_KEY:
    secret: my-secret
    key: api-key
mounts:
  - cw://my-bucket/data
---
```

### Python (.py)

```python
# /// script
# dependencies = ["marimo", "pandas"]
# ///
# [tool.marimo.k8s]
# image = "ghcr.io/marimo-team/marimo:latest"
# storage = "5Gi"
#
# [tool.marimo.k8s.env]
# DEBUG = "true"
```

### Frontmatter Fields

| Field | Description | Default |
|-------|-------------|---------|
| title | Resource name | filename |
| image | Container image | ghcr.io/marimo-team/marimo:latest |
| port | Server port | 2718 |
| storage | PVC size | none (ephemeral) |
| auth | Set to "none" to disable | token auth |
| env | Environment variables | none |
| mounts | Data source URIs | none |

### Environment Variables

Inline values:
```yaml
env:
  DEBUG: "true"
  LOG_LEVEL: "info"
```

From Kubernetes secrets:
```yaml
env:
  API_KEY:
    secret: my-secret
    key: api-key
  DB_PASSWORD:
    secret: db-credentials
    key: password
```

### Mount URIs

| Scheme | Description | Example |
|--------|-------------|---------|
| cw:// | CoreWeave Object Storage | cw://bucket/path |
| sshfs:// | SSH filesystem mount | sshfs://user@host:/path |
| rsync:// | Local directory sync | rsync://./data:/notebooks |

Local `rsync://` URIs sync a directory to the pod via `kubectl cp`. Remote URIs (`rsync://user@host:/path`) create a sidecar for continuous sync.

## Requirements

- Kubernetes cluster with marimo-operator installed
- kubectl configured to access the cluster
