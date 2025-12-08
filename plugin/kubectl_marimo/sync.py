"""Sync command implementation."""

import sys
from pathlib import Path

import click

from .formats import parse_file
from .k8s import exec_in_pod
from .resources import compute_hash, detect_content_type
from .swap import read_swap_file, write_swap_file


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
        click.echo(f"Error: No active deployment found for '{file_path}'", err=True)
        click.echo("Hint: Run 'kubectl marimo apply' first", err=True)
        sys.exit(1)

    # Use namespace from swap file if not specified
    if namespace is None:
        namespace = meta.namespace

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
        click.echo(f"Error reading from pod: {content}", err=True)
        sys.exit(1)

    # Write to local file
    path.write_text(content)

    # Update swap file hash
    meta.file_hash = compute_hash(content)
    write_swap_file(file_path, meta)

    click.echo(f"Synced from {namespace}/{meta.name} to {file_path}")
