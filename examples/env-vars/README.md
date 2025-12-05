# Environment Variables Example

Configure notebooks with environment variables from values and Kubernetes secrets.

## Prerequisites

Create a secret with your API key:

```bash
kubectl create secret generic api-credentials \
  --from-literal=api-key=YOUR_API_KEY
```

## Deploy

```bash
kubectl apply -f notebook.yaml
```

## Using the kubectl-marimo plugin

Specify env vars in frontmatter:

**Markdown:**
```yaml
---
title: api-notebook
env:
  DEBUG: "true"
  LOG_LEVEL: "debug"
  API_KEY:
    secret: api-credentials
    key: api-key
---
```

**Python:**
```python
# /// script
# dependencies = ["marimo", "requests"]
# ///
# [tool.marimo.k8s]
# storage = "1Gi"
#
# [tool.marimo.k8s.env]
# DEBUG = "true"
# LOG_LEVEL = "debug"
```

For secrets in Python format, use the full YAML frontmatter or specify via `--env` flag.
