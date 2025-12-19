# /// script
# dependencies = ["marimo"]
# ///
# [tool.marimo.k8s]
# storage = "1Gi"
# mounts = ["rsync://examples:examples"]

import marimo

__generated_with = "0.16.4"
app = marimo.App()


@app.cell
def check_sync():

    return


if __name__ == "__main__":
    app.run()
