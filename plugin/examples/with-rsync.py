# /// script
# dependencies = ["marimo"]
# ///
# [tool.marimo.k8s]
# storage = "1Gi"
# mounts = ["rsync://examples:examples"]

import marimo

__generated_with = "0.18.4"
app = marimo.App()


if __name__ == "__main__":
    app.run()
