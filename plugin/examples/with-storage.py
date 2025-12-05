# /// script
# dependencies = ["marimo"]
# ///
# [tool.marimo.k8s]
# storage = "2Gi"

import marimo

app = marimo.App()


@app.cell
def check():
    import os
    import marimo as mo

    path = "/home/marimo/notebooks"
    files = os.listdir(path) if os.path.exists(path) else []

    return mo.md(f"""
# Storage Test (2Gi PVC)

**Notebook directory:** `{path}`

**Files:** {files}
""")


if __name__ == "__main__":
    app.run()
