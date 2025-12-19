# /// script
# dependencies = ["marimo"]
# ///
# [tool.marimo.k8s]
# storage = "1Gi"
# mounts = ["sshfs://data"]

import marimo

app = marimo.App()


@app.cell
def check_mount():
    import os
    import marimo as mo

    mount_path = "/home/marimo/notebooks/mounts/sshfs-0"
    exists = os.path.exists(mount_path)
    files = os.listdir(mount_path) if exists else []

    return mo.md(f"""
# SSHFS Mount Test

**Mount path:** `{mount_path}`

**Mounted:** {exists}

**Files:** {files}
""")


if __name__ == "__main__":
    app.run()
