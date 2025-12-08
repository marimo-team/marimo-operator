"""Apply command implementation."""

import sys
from pathlib import Path

import click

from .formats import parse_file
from .k8s import apply_resource, get_resource, get_pod_logs
from .resources import build_marimo_notebook, resource_name, compute_hash, to_yaml
from .swap import read_swap_file, write_swap_file, create_swap_meta


def apply_notebook(
    file_path: str,
    namespace: str = "default",
    dry_run: bool = False,
    force: bool = False,
) -> None:
    """Deploy a notebook to the cluster."""
    path = Path(file_path)

    # Check for existing deployment
    existing = read_swap_file(file_path)
    if existing and not force:
        current_hash = compute_hash(path.read_text())
        if current_hash != existing.file_hash:
            click.echo(f"Warning: Local file '{file_path}' modified since last deploy.")
            if not click.confirm("Continue and overwrite tracking?"):
                click.echo("Apply cancelled")
                return

    # Parse file content and frontmatter
    content, frontmatter = parse_file(file_path)
    if content is None:
        click.echo(f"Error: Could not parse '{file_path}'", err=True)
        sys.exit(1)

    # Build resource
    name = resource_name(file_path, frontmatter)
    resource = build_marimo_notebook(name, namespace, content, frontmatter)

    if dry_run:
        click.echo(to_yaml(resource))
        return

    # Apply to cluster
    if not apply_resource(resource):
        sys.exit(1)

    # Create swap file
    file_hash = compute_hash(content)
    meta = create_swap_meta(
        name=name,
        namespace=namespace,
        original_file=file_path,
        file_hash=file_hash,
    )
    write_swap_file(file_path, meta)
    click.echo(f"Tracking deployment in {path.parent / f'.{path.name}.marimo'}")

    # Print access info
    print_access_info(name, namespace, frontmatter)


def print_access_info(name: str, namespace: str, frontmatter: dict | None) -> None:
    """Print helpful access information after apply."""
    port = 2718
    if frontmatter and "port" in frontmatter:
        port = int(frontmatter["port"])

    click.echo()
    click.echo("To access your notebook:")
    click.echo(f"  kubectl port-forward -n {namespace} svc/{name} {port}:{port} &")

    # Check auth configuration
    auth_disabled = frontmatter and frontmatter.get("auth") == "none"

    if auth_disabled:
        click.echo(f"  open http://localhost:{port}")
        click.echo()
        click.echo("Note: Authentication is disabled (--no-token)")
    else:
        click.echo(f"  open http://localhost:{port}")
        click.echo()
        click.echo("Note: Token is auto-generated. Check pod logs:")
        click.echo(f"  kubectl logs -n {namespace} {name} | grep token")
