# /// script
# dependencies = ["marimo"]
# [tool.marimo.k8s]
# mounts = ["cw://operator-bucket"]
# ///
# Note: cw-credentials secret is auto-created from ~/.s3cfg by the plugin

import marimo

__generated_with = "0.18.4"
app = marimo.App()


@app.cell
def check_mount():
    import os
    import subprocess

    # Check default mount location
    mount_dir = "/home/marimo/notebooks/mounts"
    print(f"Checking mount directory: {mount_dir}")

    if os.path.exists(mount_dir):
        print(f"Contents: {os.listdir(mount_dir)}")
        for item in os.listdir(mount_dir):
            item_path = os.path.join(mount_dir, item)
            if os.path.isdir(item_path):
                print(f"  {item}/: {os.listdir(item_path)}")
    else:
        print("Mount directory does not exist yet")

    # Show running processes (to verify s3fs sidecar)
    result = subprocess.run(["ps", "aux"], capture_output=True, text=True)
    if "s3fs" in result.stdout:
        print("\ns3fs process is running!")
    return (os,)


@app.cell
def read_test_file(os):
    test_file = "/home/marimo/notebooks/mounts/cw-0/test-data.txt"
    if os.path.exists(test_file):
        with open(test_file) as f:
            content = f.read()
        print(f"File contents: {content}")
    else:
        print(f"Test file not found at {test_file}")
        print(
            "Available mounts:",
            os.listdir("/home/marimo/notebooks/mounts")
            if os.path.exists("/home/marimo/notebooks/mounts")
            else "none",
        )
    return


if __name__ == "__main__":
    app.run()
