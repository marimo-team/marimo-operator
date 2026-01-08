"""Sync command implementation."""

import subprocess
from pathlib import Path

import click

from .k8s import exec_in_pod
from .resources import compute_hash, detect_content_type
from .swap import read_swap_file, write_swap_file


def sync_local_mounts(
    name: str,
    namespace: str | None,
    local_mounts: list[dict],
) -> None:
    """Sync mount points from pod to local.

    Args:
        name: Pod name
        namespace: Kubernetes namespace
        local_mounts: List of {"local": path, "remote": mount_point} dicts
    """
    for mount in local_mounts:
        local_path = mount["local"]
        remote_path = mount["remote"]

        # kubectl cp from pod to local
        cp_cmd = [
            "kubectl",
            "cp",
            f"{namespace}/{name}:{remote_path}/.",
            local_path,
            "-c",
            "marimo",
        ]
        result = subprocess.run(cp_cmd, capture_output=True, text=True)
        if result.returncode == 0:
            click.echo(f"Synced {remote_path} → {local_path}")
            # Clean up .marimo swap files that may have been copied back
            local_dir = Path(local_path)
            if local_dir.is_dir():
                for marimo_file in local_dir.rglob("*.marimo"):
                    marimo_file.unlink()
        else:
            click.echo(
                f"Warning: Failed to sync {remote_path}: {result.stderr}", err=True
            )


def sync_notebook(
    file_path: str,
    namespace: str | None = None,
    force: bool = False,
) -> None:
    """Sync notebook content from pod to local file."""
    path = Path(file_path)

    # Read swap file to get pod info
    meta = read_swap_file(file_path)
    if meta is None:
        raise click.UsageError(
            f"No active deployment found for '{file_path}'. "
            "Hint: Run 'kubectl marimo apply' first"
        )

    # Use namespace from swap file if not specified
    if namespace is None:
        namespace = meta.namespace

    # Sync local mounts FIRST (if present)
    if meta.local_mounts:
        sync_local_mounts(meta.name, namespace, meta.local_mounts)

    # For directory mode, only sync local mounts (no content to sync)
    if path.is_dir():
        click.echo(f"Synced mounts from {namespace}/{meta.name}")
        return

    # Check for local modifications
    if not force and path.exists():
        current_hash = compute_hash(path.read_text())
        if current_hash != meta.file_hash:
            click.echo(f"Warning: Local file '{file_path}' modified since deploy.")
            if not click.confirm("Overwrite with pod content?"):
                click.echo("Sync cancelled")
                return

    # Determine notebook filename in pod
    content_type = detect_content_type(path.read_text() if path.exists() else "")
    if content_type == "markdown":
        notebook_file = "notebook.md"
    else:
        notebook_file = "notebook.py"

    # Pull content from pod via kubectl exec
    success, content = exec_in_pod(
        meta.name,
        namespace,
        f"cat /home/marimo/notebooks/{notebook_file}",
    )

    if not success:
        raise click.ClickException(f"Error reading from pod: {content}")

    # Write to local file
    path.write_text(content)

    # Update swap file hash
    meta.file_hash = compute_hash(content)
    write_swap_file(file_path, meta)

    click.echo(f"Synced from {namespace}/{meta.name} to {file_path}")
