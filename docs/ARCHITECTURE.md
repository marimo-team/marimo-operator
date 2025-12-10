# Architecture

This document describes the design decisions and architecture of the marimo-operator.

## Overview

The marimo-operator is a Kubernetes operator that manages `MarimoNotebook` custom resources. For each notebook, it creates:

- **PVC**: Persistent storage for notebook files (preserved on CR deletion)
- **Pod**: Runs marimo server with init container and optional sidecars
- **Service**: Exposes marimo port (and sidecar ports)

```
┌─────────────────────────────────────────────────────────────┐
│                    MarimoNotebook CR                         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Operator Controller                       │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│     PVC     │       │     Pod     │       │   Service   │
│ (preserved) │       │  + sidecars │       │   (ports)   │
└─────────────┘       └─────────────┘       └─────────────┘
```

## CRD Schema

### MarimoNotebookSpec

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `image` | string | No | Container image (default: `ghcr.io/marimo-team/marimo:latest`) |
| `port` | int32 | No | Server port (default: 2718) |
| `source` | string | Yes | Git URL for notebook content |
| `storage` | StorageSpec | No | PVC configuration |
| `resources` | ResourcesSpec | No | CPU/memory/GPU requests and limits |
| `auth` | AuthSpec | No | Authentication configuration |
| `sidecars` | []SidecarSpec | No | Additional containers |
| `podOverrides` | PodSpec | No | Strategic merge patch for Pod customization |

### Source

The `source` field specifies where to fetch notebook content:

```yaml
spec:
  source: https://github.com/org/notebooks.git
```

The operator uses an init container to clone the repository into the PVC.

### Storage

Storage configuration for the PVC:

```yaml
spec:
  storage:
    size: 1Gi
    storageClassName: standard  # optional
```

The init container clones `source` into the PVC, and marimo serves from there.

**PVC Preservation**: PVCs are **not** deleted when the MarimoNotebook CR is deleted. This preserves user data by default. Explicit deletion requires `--delete-pvc` flag via the plugin or manual PVC deletion.

### Sidecars

Additional containers that run alongside marimo, sharing the PVC volume:

**SSH access:**
```yaml
spec:
  sidecars:
    - name: sshd
      image: linuxserver/openssh-server:latest
      exposePort: 2222
      env:
        - name: PASSWORD_ACCESS
          value: "true"
```

**Git sync:**
```yaml
spec:
  sidecars:
    - name: git-sync
      image: registry.k8s.io/git-sync/git-sync:v4.2.1
      env:
        - name: GITSYNC_REPO
          value: https://github.com/user/notebooks.git
```

The `exposePort` field adds the port to the Service for external access.

### MarimoNotebookStatus

| Field | Type | Description |
|-------|------|-------------|
| `phase` | string | Current state: Pending, Running, Failed |
| `url` | string | Internal service URL |
| `sourceHash` | string | Hash of source URL + ref |
| `podName` | string | Name of the created Pod |
| `serviceName` | string | Name of the created Service |
| `conditions` | []Condition | Standard Kubernetes conditions |

## Reconciliation

### Controller Flow

1. **Validate Spec**: Ensure `source` is set
2. **Ensure PVC**: Create if `storage` is specified (no owner reference)
3. **Ensure Pod**: Create with init container (clones source), marimo container, sidecars
4. **Ensure Service**: Expose marimo port and sidecar `exposePort`s
5. **Update Status**: Set phase, URL, source hash, conditions

### Pod Structure

```
┌─────────────────────────────────────────────────────────────┐
│                          Pod                                 │
├─────────────────────────────────────────────────────────────┤
│  Init Container: git-clone                                  │
│  - Clones source repo to /data (if empty)                   │
├─────────────────────────────────────────────────────────────┤
│  Container: marimo                                          │
│  - Serves notebooks from /data                              │
│  - Port: 2718 (default)                                     │
├─────────────────────────────────────────────────────────────┤
│  Sidecar: ssh (optional)                                    │
│  - Shares /data volume                                      │
│  - Port: 2222                                               │
├─────────────────────────────────────────────────────────────┤
│  Sidecar: git-sync (optional)                               │
│  - Watches /data for changes                                │
│  - Syncs to/from repo                                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                      ┌─────────────┐
                      │     PVC     │
                      │   /data     │
                      └─────────────┘
```

### Pod Update Strategy

The operator uses a **recreate** strategy for pod updates:

1. On spec change, delete the existing Pod
2. Create a new Pod with updated spec
3. Init container skips clone if PVC already has content

### Owner References

Pod and Service have owner references to the MarimoNotebook CR (garbage collected on delete).

PVC does **not** have an owner reference (preserved on delete). This is intentional - user data should not be accidentally deleted.

## Plugin Architecture

The `kubectl-marimo` plugin handles local notebook deployment:

1. Reads local notebook files (`.py`, `.md`)
2. Uploads content to a ConfigMap
3. Generates `MarimoNotebook` CR referencing the ConfigMap
4. Tracks deployments in swap files (`.notebook.marimo`)

See [PLUGIN.md](PLUGIN.md) for distribution details.

### Swap Files

The plugin creates a swap file (e.g., `.notebook.py.marimo`) that tracks:

```json
{
  "name": "notebook",
  "namespace": "default",
  "appliedAt": "2025-01-01T00:00:00Z",
  "originalFile": "notebook.py",
  "fileHash": "sha256:abc123"
}
```

This enables:
- `kubectl marimo sync` to find the deployed resource
- `kubectl marimo delete` to clean up resources
- Hash comparison for conflict detection

## Design Decisions

### Why source-based content?

Real projects have multiple files. Git URLs are the natural unit of deployment:

1. Clone via init container
2. Sidecars like git-sync enable bidirectional sync
3. Plugin handles local files via ConfigMap upload

### Why preserve PVCs?

User data is precious. Accidental deletion is worse than orphaned PVCs:

1. PVCs have no owner reference (not garbage collected)
2. Explicit `--delete-pvc` required for full cleanup
3. PVC can be reattached to new CR with same name

### Why recreate pods?

Kubernetes Pods are largely immutable. Rather than complex in-place updates:

1. Recreate is explicit and predictable
2. Init container skips clone if data exists
3. PVC preserves user changes across restarts

### Why cluster-scoped?

A single operator installation manages all namespaces:

1. Simpler deployment (one `kubectl apply`)
2. Consistent behavior across namespaces
3. Centralized logging and metrics

### Why Python plugin?

Target users (marimo users) already have Python:

1. Can import marimo's file parsers
2. `uv`/`uvx` provides fast installation
3. Single source of truth (no version drift)
4. Krew compatibility via Go shim

### Why configurable default images?

All auto-generated sidecars use images configurable via operator environment variables:

| Env Var | Default | Usage |
|---------|---------|-------|
| `DEFAULT_INIT_IMAGE` | `busybox:1.36` | copy-content init container |
| `GIT_IMAGE` | `alpine/git:latest` | git clone sidecar |
| `ALPINE_IMAGE` | `alpine:latest` | sshfs + file:// mount sidecars |
| `S3FS_IMAGE` | `ghcr.io/marimo-team/marimo-operator/s3fs:latest` | cw:// mount sidecar |
| `S3_ENDPOINT` | `https://cwobject.com` | S3 endpoint for cw:// mounts |

Benefits:
1. Air-gapped clusters can use internal registries
2. Security teams can mandate approved images
3. No hardcoded third-party dependencies
4. Users can always override via `spec.sidecars` for full control
