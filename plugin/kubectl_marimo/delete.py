"""Delete command implementation."""

import sys
from pathlib import Path

import click

from .formats import parse_file
from .k8s import delete_resource, exec_in_pod
from .resources import compute_hash, resource_name, detect_content_type
from .swap import read_swap_file, delete_swap_file


def delete_notebook(
    file_path: str,
    namespace: str | None = None,
    force: bool = False,
    no_sync: bool = False,
    keep_pvc: bool = False,
) -> None:
    """Delete notebook deployment from cluster."""
    path = Path(file_path)

    if not path.exists():
        click.echo(f"Error: File '{file_path}' not found", err=True)
        sys.exit(1)

    # Parse file to get resource name
    content, frontmatter = parse_file(file_path)
    name = resource_name(file_path, frontmatter)

    # Read swap file for sync
    meta = read_swap_file(file_path)

    # Use namespace from swap file if not specified
    if namespace is None:
        namespace = meta.namespace if meta else "default"

    # Sync before delete (unless --no-sync)
    if not no_sync and meta is not None:
        click.echo("Syncing changes from pod before delete...")

        # Check for local modifications
        if not force:
            current_hash = compute_hash(path.read_text())
            if current_hash != meta.file_hash:
                click.echo(f"Warning: Local file '{file_path}' modified since deploy.")
                if not click.confirm("Overwrite with pod content?"):
                    click.echo("Delete cancelled. Use --no-sync to delete without syncing.")
                    return

        # Determine notebook filename in pod
        content_type = detect_content_type(content or "")
        if content_type == "markdown":
            notebook_file = "notebook.md"
        else:
            notebook_file = "notebook.py"

        # Try to pull content from pod
        success, pod_content = exec_in_pod(
            meta.name,
            namespace,
            f"cat /home/marimo/notebooks/{notebook_file}",
        )

        if not success:
            click.echo(f"Warning: Could not sync from pod: {pod_content}", err=True)
            click.echo("Continuing with delete...")
        else:
            path.write_text(pod_content)
            click.echo(f"Synced content to {file_path}")

    # Delete the MarimoNotebook resource
    # Note: PVC is deleted via owner reference unless keep_pvc is set
    if keep_pvc:
        click.echo("Note: --keep-pvc requires manual PVC deletion prevention")
        click.echo(f"      kubectl patch pvc -n {namespace} {name}-pvc -p '{{\"metadata\":{{\"ownerReferences\":[]}}}}'")

    if not delete_resource("marimos.marimo.io", name, namespace):
        sys.exit(1)

    # Remove swap file
    delete_swap_file(file_path)
    click.echo(f"Deleted {namespace}/{name}")
