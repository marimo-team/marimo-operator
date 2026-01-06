# /// script
# dependencies = ["marimo"]
# ///
# [tool.marimo.k8s]
# storage = "1Gi"
# mounts = ["sshfs://data"]

import marimo

__generated_with = "0.18.4"
app = marimo.App()


@app.cell
def check_mount():
    import os

    mount_path = "/home/marimo/notebooks/mounts/sshfs-0"
    exists = os.path.exists(mount_path)
    os.listdir(mount_path) if exists else []
    return


if __name__ == "__main__":
    app.run()
