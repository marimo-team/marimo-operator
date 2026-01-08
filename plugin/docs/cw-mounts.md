# CoreWeave S3 Mounts (`cw://`)

Mount CoreWeave Object Storage buckets in your marimo notebooks using `cw://` URIs.

## Prerequisites

- `cwic` CLI authenticated to your CoreWeave organization
- `s3cmd` installed (used by cwic for bucket operations)
- kubectl-marimo plugin installed
- marimo-operator running in your cluster

## Setup

### 1. Create an Access Policy

Before creating buckets or tokens, you need an organization-level access policy that grants S3 permissions.

```bash
# Create policy JSON file
cat > cw-policy.json << 'EOF'
{
  "name": "marimo-s3-policy",
  "version": "v1alpha1",
  "statements": [
    {
      "name": "marimo-bucket-access",
      "effect": "Allow",
      "actions": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "resources": ["*"],
      "principals": []
    }
  ]
}
EOF

# Create the policy
cwic cwobject policy create -f cw-policy.json
```

> **Note**: You'll add principals (token identities) to this policy after creating tokens.

### 2. Create a Bucket

Create your bucket in the appropriate region:

```bash
cwic cwobject mb my-notebook-data
```

> **Note**: If you get `AccessDenied`, ensure your policy includes `s3:CreateBucket` or create the bucket via the CoreWeave console.

### 3. Create an Access Token

```bash
# Create a permanent token (or use --duration 86400 for 24h)
cwic cwobject token create --name marimo-s3 --duration Permanent
```

Save the output:
```
Access Key ID:   CWXXXXXXXXXX
Secret Key:      cwXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
Principal Name:  coreweave/uXXXXXXXXXXXXXXXXXXXXX
```

### 4. Add Principal to Policy

Update your policy to include the token's principal:

```bash
# Get current policy
cwic cwobject policy get

# Update policy JSON to add principal, then re-apply
cwic cwobject policy create -f cw-policy.json
```

### 5. Configure s3cmd

```bash
cat > ~/.s3cfg << EOF
[default]
access_key = CWXXXXXXXXXX
secret_key = cwXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
host_base = cwobject.com
host_bucket = %(bucket)s.cwobject.com
use_https = True
EOF

# Verify access
s3cmd ls s3://my-notebook-data/
```

### 6. Kubernetes Secret (automatic)

The `kubectl-marimo` plugin automatically creates the `cw-credentials` secret from your `~/.s3cfg` when you use `cw://` mounts:

```bash
# This auto-creates the secret if needed
kubectl marimo edit --source=cw://my-bucket notebook.py
```

To create manually:

```bash
kubectl create secret generic cw-credentials \
  --from-literal=AWS_ACCESS_KEY_ID=CWXXXXXXXXXX \
  --from-literal=AWS_SECRET_ACCESS_KEY=cwXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

### Multi-Tenancy

Secrets are namespace-scoped in Kubernetes. For multi-tenant clusters:

1. Each team gets their own namespace
2. Create `cw-credentials` in each namespace with team-specific S3 tokens
3. The operator automatically uses the secret from the MarimoNotebook's namespace

Example setup for two teams:

```bash
# Team Alpha - their own S3 token
kubectl create secret generic cw-credentials -n team-alpha \
  --from-literal=AWS_ACCESS_KEY_ID=TEAM_ALPHA_KEY \
  --from-literal=AWS_SECRET_ACCESS_KEY=TEAM_ALPHA_SECRET

# Team Beta - different S3 token
kubectl create secret generic cw-credentials -n team-beta \
  --from-literal=AWS_ACCESS_KEY_ID=TEAM_BETA_KEY \
  --from-literal=AWS_SECRET_ACCESS_KEY=TEAM_BETA_SECRET
```

For RBAC lockdown, limit each team's Role to only access secrets in their namespace. The plugin prompts for confirmation in interactive terminals before creating secrets; in CI/CD (non-TTY) it creates automatically.

### Secret Persistence

Once created, the `cw-credentials` secret persists in the namespace until explicitly deleted. The plugin will reuse an existing secret without prompting.

To update credentials (e.g., after rotating tokens):

```bash
# Delete the existing secret
kubectl delete secret cw-credentials -n <namespace>

# The plugin will prompt to create a new one on next deploy
kubectl marimo edit --source=cw://bucket notebook.py
```

Or replace directly:

```bash
kubectl delete secret cw-credentials -n <namespace>
kubectl create secret generic cw-credentials -n <namespace> \
  --from-literal=AWS_ACCESS_KEY_ID=NEW_KEY \
  --from-literal=AWS_SECRET_ACCESS_KEY=NEW_SECRET
```

### Credential Section Priority

The plugin reads credentials from `~/.s3cfg`, trying sections in order:

1. `[namespace]` - if deploying to a specific namespace (e.g., `[team-alpha]`)
2. `[marimo]` - marimo-specific credentials
3. `[default]` - standard s3cmd credentials

This allows namespace-specific or marimo-specific credentials:

```ini
[default]
access_key = GENERAL_KEY
secret_key = GENERAL_SECRET

[marimo]
access_key = MARIMO_KEY
secret_key = MARIMO_SECRET

[team-alpha]
access_key = TEAM_ALPHA_KEY
secret_key = TEAM_ALPHA_SECRET
```

When deploying with `kubectl marimo edit -n team-alpha ...`, the plugin will use `[team-alpha]` credentials if present.

## Usage

### URI Format

```
cw://bucket[/path][:mount_point]
```

| Example | Description |
|---------|-------------|
| `cw://mybucket` | Mount bucket root |
| `cw://mybucket/data` | Mount `/data` subdirectory |
| `cw://mybucket/data:/mnt/s3` | Custom mount point |

### Via CLI

```bash
kubectl marimo edit notebook.py --source=cw://my-notebook-data
```

### Via Header

```python
# /// script
# dependencies = ["marimo"]
# [tool.marimo.k8s]
# mounts = ["cw://my-notebook-data"]
# ///
```

### Access in Notebook

Files are mounted at `/home/marimo/notebooks/mounts/cw-0/`:

```python
import os

mount_path = "/home/marimo/notebooks/mounts/cw-0"
files = os.listdir(mount_path)
print(f"Files in S3: {files}")

# Read a file
with open(f"{mount_path}/data.csv") as f:
    content = f.read()
```

## S3 Endpoints

The default endpoint is `https://cwobject.com` which works from all nodes.

Override with the `S3_ENDPOINT` environment variable in the operator deployment:

```bash
# For LOTA-optimized access from GPU nodes (optional)
kubectl set env deployment/marimo-operator-controller-manager \
  -n marimo-operator-system \
  S3_ENDPOINT=http://cwlota.com
```

| Endpoint | Use Case |
|----------|----------|
| `https://cwobject.com` | Default, works everywhere |
| `http://cwlota.com` | LOTA-optimized (GPU nodes only) |

## How It Works

The `cw://` mount creates an s3fs sidecar container that:

1. Runs alongside your marimo container
2. Uses FUSE to mount the S3 bucket as a filesystem
3. Shares the mount via a shared volume

Features:
- Full read/write support
- Symlink support (unlike mountpoint-s3)
- In-place file editing

## Troubleshooting

### AccessDenied errors

1. Verify token is active: `cwic cwobject token get --name marimo-s3`
2. Check policy includes your principal: `cwic cwobject policy get`
3. Ensure policy has required actions for your operation

### Bucket not found

- Check bucket exists: `s3cmd ls s3://bucket-name/`
- Verify bucket region matches your cluster

### Mount not appearing in pod

- Check sidecar logs: `kubectl logs <pod> -c cw-0`
- Verify secret exists: `kubectl get secret cw-credentials`
- Check credentials are correct in secret

### FUSE device not found

The s3fs sidecar requires privileged mode to access `/dev/fuse`. Ensure you're using operator version with the privileged security context fix.
