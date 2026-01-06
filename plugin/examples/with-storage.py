# /// script
# dependencies = ["marimo"]
# ///
# [tool.marimo.k8s]
# storage = "2Gi"

import marimo

__generated_with = "0.18.4"
app = marimo.App()


@app.cell
def check():
    import os

    path = "/home/marimo/notebooks"
    os.listdir(path) if os.path.exists(path) else []
    return


if __name__ == "__main__":
    app.run()
