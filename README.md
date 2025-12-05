# marimo-operator

A Kubernetes operator for deploying [marimo](https://github.com/marimo-team/marimo) notebooks.

## Features

- **Cloud storage integration**: Mount S3-compatible storage (cw://, sshfs://, rsync://)
- **Persistent storage**: Browser edits persist across restarts
- **Resource management**: Memory, CPU, and GPU allocation per notebook
- **Extensible sidecars**: Add custom containers for advanced use cases

## Prerequisites

- Kubernetes cluster (v1.25+)
- `kubectl` configured with cluster access
- Cluster admin permissions (for CRD installation)

## Installation

```bash
# Option 1: Install from single manifest
kubectl apply -f https://raw.githubusercontent.com/marimo-team/marimo-operator/main/deploy/install.yaml

# Option 2: Install via kustomize
kubectl apply -k https://github.com/marimo-team/marimo-operator/config/default

# Verify installation
kubectl get pods -n marimo-operator-system
# Should show: marimo-operator-controller-manager-xxx  Running
```

## Quickstart

### Option 1: Deploy from Git

```bash
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
kubectl get marimos
```

### Option 2: Use kubectl plugin for local files

```bash
# Install plugin
pip install kubectl-marimo

# Edit a notebook interactively (deploys to cluster)
kubectl marimo edit notebook.py

# Run as read-only app
kubectl marimo run notebook.py

# Sync changes back to local file
kubectl marimo sync notebook.py
```

### Verify your notebook is running

```bash
# Check pod status
kubectl get pods

# View logs
kubectl logs <pod-name> -c marimo

# Port-forward to access
kubectl port-forward svc/my-project 2718:2718
# Open http://localhost:2718
```

## Usage

### Source vs Content

Use **`source`** for Git repositories (cloned into persistent storage):

```yaml
spec:
  source: https://github.com/org/notebooks.git
  storage:
    size: 1Gi
```

Use **`content`** for inline notebook code (via kubectl plugin or ConfigMap):

```yaml
spec:
  content: |
    import marimo
    app = marimo.App()
    @app.cell
    def _():
        return "Hello!"
```

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

By default, marimo generates an authentication token (check pod logs). To use a password:

```bash
# Create secret
kubectl create secret generic marimo-auth --from-literal=password=your-password
```

```yaml
spec:
  auth:
    password:
      secretKeyRef:
        name: marimo-auth
        key: password
```

To disable authentication (not recommended for production):

```yaml
spec:
  auth: {}
```

## Troubleshooting

```bash
# Check operator logs
kubectl logs -n marimo-operator-system -l control-plane=controller-manager

# Check notebook status
kubectl describe marimo <name>

# Check pod events
kubectl get events --field-selector involvedObject.name=<pod-name>

# Common issues:
# - "Pending" pod: Check storage class exists, PVC can be created
# - "ImagePullBackOff": Check image name and registry access
# - "CrashLoopBackOff": Check container logs for errors
```

## kubectl Plugin

For deploying individual notebooks from local files. See [plugin/README.md](plugin/README.md) for details.

```bash
pip install kubectl-marimo

# Interactive editing
kubectl marimo edit notebook.py

# Read-only app mode
kubectl marimo run notebook.py

# With S3 storage (CoreWeave)
kubectl marimo edit --source=cw://bucket/data notebook.py

# Sync changes back and clean up
kubectl marimo sync notebook.py
kubectl marimo delete notebook.py
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) - Design decisions and CRD schema
- [Plugin Guide](plugin/README.md) - kubectl-marimo usage
- [CoreWeave S3 Mounts](plugin/docs/cw-mounts.md) - S3 storage integration

## Development

```bash
make test          # Run tests
make docker-build  # Build operator image
make deploy        # Deploy to local Kind cluster
```

## License

Apache 2.0
