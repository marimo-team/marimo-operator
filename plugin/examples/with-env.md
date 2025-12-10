---
title: env-test
auth: none
env:
  DEBUG: "true"
  APP_NAME: kubectl-marimo-test
---

# Environment Variables Test

```python {.marimo}
import os
import marimo as mo

debug = os.environ.get("DEBUG", "not set")
app_name = os.environ.get("APP_NAME", "not set")

mo.md(f"""
**Environment:**
- DEBUG = `{debug}`
- APP_NAME = `{app_name}`
""")
```
