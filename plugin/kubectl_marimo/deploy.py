"""Deploy command implementation."""

import sys
from pathlib import Path

import click

from .formats import parse_file
from .k8s import apply_resource, get_resource, get_pod_logs
from .resources import build_marimo_notebook, resource_name, compute_hash, to_yaml
from .swap import read_swap_file, write_swap_file, create_swap_meta


def deploy_notebook(
    file_path: str,
    mode: str = "edit",
    namespace: str = "default",
    source: str | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> None:
    """Deploy a notebook to the cluster.

    Args:
        file_path: Path to notebook file or directory
        mode: Marimo mode - "edit" (interactive) or "run" (read-only)
        namespace: Kubernetes namespace
        source: Data source URI (cw://, sshfs://, file://)
        dry_run: Print YAML without applying
        force: Overwrite without prompting
    """
    path = Path(file_path)

    # Handle directory case (edit without file)
    if path.is_dir():
        # For directory mode, we deploy the directory itself
        content = None
        frontmatter = None
        name = resource_name(file_path, None)
    else:
        # Check for existing deployment
        existing = read_swap_file(file_path)
        if existing and not force:
            current_hash = compute_hash(path.read_text())
            if current_hash != existing.file_hash:
                click.echo(f"Warning: Local file '{file_path}' modified since last deploy.")
                if not click.confirm("Continue and overwrite tracking?"):
                    click.echo("Deploy cancelled")
                    return

        # Parse file content and frontmatter
        content, frontmatter = parse_file(file_path)
        if content is None:
            click.echo(f"Error: Could not parse '{file_path}'", err=True)
            sys.exit(1)
        name = resource_name(file_path, frontmatter)

    # Build resource
    resource = build_marimo_notebook(
        name=name,
        namespace=namespace,
        content=content,
        frontmatter=frontmatter,
        mode=mode,
        source=source,
    )

    if dry_run:
        click.echo(to_yaml(resource))
        return

    # Apply to cluster
    if not apply_resource(resource):
        sys.exit(1)

    # Create swap file (only for file-based deployments)
    if not path.is_dir() and content:
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
    print_access_info(name, namespace, mode, frontmatter)


def print_access_info(name: str, namespace: str, mode: str, frontmatter: dict | None) -> None:
    """Print helpful access information after deploy."""
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

    if mode == "run":
        click.echo()
        click.echo("Running in read-only app mode.")
