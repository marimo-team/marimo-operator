# kubectl-marimo

kubectl plugin for deploying marimo notebooks to Kubernetes.

## Installation

```bash
# With pip
pip install kubectl-marimo

# With uv
uv tool install kubectl-marimo

# With uvx (no install)
uvx kubectl-marimo apply notebook.py
```

## Usage

```bash
# Deploy a notebook
kubectl marimo apply notebook.py
kubectl marimo apply notebook.md

# Sync changes from pod
kubectl marimo sync notebook.py

# Delete deployment
kubectl marimo delete notebook.py

# List active deployments
kubectl marimo status
```

## Frontmatter

Configure deployments via frontmatter:

**Markdown (.md):**
```yaml
---
title: My Notebook
image: ghcr.io/marimo-team/marimo:latest
storage: 1Gi
auth: none
---
```

**Python (.py):**
```python
# /// script
# dependencies = ["marimo", "pandas"]
# ///
# [tool.marimo.k8s]
# image = "custom:latest"
# storage = "5Gi"
```

## Requirements

- Kubernetes cluster with marimo-operator installed
- kubectl configured to access the cluster
