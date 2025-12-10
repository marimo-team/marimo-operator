# S3/CW Storage Example

Mount S3-compatible storage (like CloudWatch) for data analysis.

## Prerequisites

Create a secret with your S3 credentials:

```bash
kubectl create secret generic s3-credentials \
  --from-literal=access-key=YOUR_ACCESS_KEY \
  --from-literal=secret-key=YOUR_SECRET_KEY
```

## Deploy

```bash
kubectl apply -f notebook.yaml
```

## Using the kubectl-marimo plugin

With the plugin, use `--source` to mount S3 storage:

```bash
kubectl marimo edit --source=cw://my-bucket/data notebook.py
```

Or specify mounts in frontmatter:

```yaml
---
title: data-analysis
storage: 5Gi
mounts:
  - cw://my-bucket/data
---
```

The plugin automatically generates the sidecar configuration.
