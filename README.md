# marimo-operator

A Kubernetes operator for deploying [marimo](https://marimo.io) notebooks.

## Features

- **Git-native deployment**: Clone notebooks directly from repositories
- **Extensible sidecars**: Add SSH, git-sync, or custom containers
- **Persistent storage**: Browser edits persist across restarts
- **Resource management**: Memory, CPU, and GPU allocation per notebook

## Quickstart

```bash
# Install the operator
kubectl apply -f https://raw.githubusercontent.com/marimo-team/marimo-operator/main/deploy/install.yaml

# Deploy a notebook project
kubectl apply -f - <<EOF
apiVersion: marimo.io/v1alpha1
kind: MarimoNotebook
metadata:
  name: my-project
spec:
  source: https://github.com/marimo-team/examples.git
  storage:
    size: 1Gi
EOF

# Check status
kubectl get marimonotebooks
```

_Or_ deploy individual notebooks with the kubectl plugin:

```bash
# Install plugin
pip install kubectl-marimo  # or: kubectl krew install marimo

# Deploy a local notebook
kubectl marimo apply notebook.py

# Sync changes back
kubectl marimo sync notebook.py
```

## Usage

### Deploy from Git

```yaml
apiVersion: marimo.io/v1alpha1
kind: MarimoNotebook
metadata:
  name: my-project
spec:
  source: https://github.com/org/notebooks.git
  storage:
    size: 1Gi
```

The operator clones the repository into persistent storage and starts the marimo server.

### Add Sidecars

Sidecars run alongside marimo, sharing the same storage volume:

```yaml
apiVersion: marimo.io/v1alpha1
kind: MarimoNotebook
metadata:
  name: dev-environment
spec:
  source: https://github.com/org/notebooks.git
  storage:
    size: 5Gi
  sidecars:
    # SSH for remote access
    - name: ssh
      image: linuxserver/openssh-server:latest
      exposePort: 2222
      env:
        - name: PASSWORD_ACCESS
          value: "true"

    # Continuous git synchronization
    - name: git-sync
      image: registry.k8s.io/git-sync/git-sync:v4.2.1
      env:
        - name: GITSYNC_REPO
          value: https://github.com/org/notebooks.git
        - name: GITSYNC_ROOT
          value: /data
```

| Sidecar | Image | Use Case |
|---------|-------|----------|
| **SSH** | `linuxserver/openssh-server` | Remote shell, rsync, SSHFS mount |
| **Git Sync** | `registry.k8s.io/git-sync` | Bidirectional repo synchronization |

The `exposePort` field adds the port to the Service for external access.

### GPU Support

```yaml
spec:
  resources:
    requests:
      memory: 4Gi
    limits:
      memory: 16Gi
      nvidia.com/gpu: 1
```

### Authentication

```yaml
spec:
  auth:
    password:
      secretKeyRef:
        name: marimo-auth
        key: password
```

## kubectl Plugin

For deploying individual notebooks from local files. See [docs/PLUGIN.md](docs/PLUGIN.md) for details.

```bash
pip install kubectl-marimo
kubectl marimo apply notebook.py
kubectl marimo sync notebook.py
kubectl marimo delete notebook.py             # PVC preserved by default
kubectl marimo delete notebook.py --delete-pvc  # Also delete storage
```

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for design decisions.

## Installation

```bash
kubectl apply -f https://raw.githubusercontent.com/marimo-team/marimo-operator/main/deploy/install.yaml
```

## Development

```bash
make test          # Run tests
make docker-build  # Build operator image
make deploy        # Deploy to local Kind cluster
```

## License

Apache 2.0
