# /// script
# dependencies = ["marimo"]
# ///
# [tool.marimo.k8s]
# mounts = ["cw://operator-bucket"]

import marimo

__generated_with = "0.18.4"
app = marimo.App()


@app.cell
def check_mount():
    import os

    mount_dir = "/home/marimo/notebooks/mounts/cw-0"
    print(f"Checking: {mount_dir}")

    if os.path.exists(mount_dir):
        files = os.listdir(mount_dir)
        print(f"Files: {files}")
        for f in files:
            path = os.path.join(mount_dir, f)
            if os.path.isfile(path):
                with open(path) as fp:
                    print(f"{f}: {fp.read()[:100]}")
    else:
        print("Mount not ready")
    return


if __name__ == "__main__":
    app.run()
