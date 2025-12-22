"""CLI entry point for kubectl-marimo."""

import click

from . import __version__
from .deploy import deploy_notebook
from .delete import delete_notebook
from .status import show_status
from .sync import sync_notebook


@click.group()
@click.version_option(version=__version__)
def cli():
    """Deploy marimo notebooks to Kubernetes.

    Examples:

        kubectl marimo edit notebook.py
        kubectl marimo run notebook.py
        kubectl marimo edit --source=cw://bucket/data notebook.py
        kubectl marimo sync notebook.py
        kubectl marimo delete notebook.py
        kubectl marimo status
    """
    pass


@cli.command()
@click.argument("file", type=click.Path(exists=True), required=False, default=".")
@click.option(
    "-n",
    "--namespace",
    default=None,
    help="Kubernetes namespace (default: from kubectl context)",
)
@click.option("--source", help="Data source URI (cw://, sshfs://, rsync://)")
@click.option("--dry-run", is_flag=True, help="Print YAML without applying")
@click.option("--headless", is_flag=True, help="Deploy without port-forward or browser")
@click.option("--force", "-f", is_flag=True, help="Overwrite without prompting")
def edit(
    file: str,
    namespace: str | None,
    source: str | None,
    dry_run: bool,
    headless: bool,
    force: bool,
):
    """Create or edit notebooks in the cluster.

    FILE is a marimo notebook (.py, .md) or directory. Defaults to current directory.
    """
    deploy_notebook(
        file,
        mode="edit",
        namespace=namespace,
        source=source,
        dry_run=dry_run,
        headless=headless,
        force=force,
    )


@cli.command()
@click.argument("file", type=click.Path(exists=True))
@click.option(
    "-n",
    "--namespace",
    default=None,
    help="Kubernetes namespace (default: from kubectl context)",
)
@click.option("--source", help="Data source URI (cw://, sshfs://, rsync://)")
@click.option("--dry-run", is_flag=True, help="Print YAML without applying")
@click.option("--headless", is_flag=True, help="Deploy without port-forward or browser")
@click.option("--force", "-f", is_flag=True, help="Overwrite without prompting")
def run(
    file: str,
    namespace: str | None,
    source: str | None,
    dry_run: bool,
    headless: bool,
    force: bool,
):
    """Run a notebook as a read-only application.

    FILE is a marimo notebook (.py, .md).
    """
    deploy_notebook(
        file,
        mode="run",
        namespace=namespace,
        source=source,
        dry_run=dry_run,
        headless=headless,
        force=force,
    )


@cli.command()
@click.argument("file", type=click.Path(exists=True))
@click.option(
    "-n", "--namespace", help="Kubernetes namespace (default: from swap file)"
)
@click.option(
    "--force", "-f", is_flag=True, help="Overwrite local file without prompting"
)
def sync(file: str, namespace: str | None, force: bool):
    """Pull changes from pod back to local file.

    FILE is the local notebook that was previously deployed.
    """
    sync_notebook(file, namespace=namespace, force=force)


@cli.command()
@click.argument("file", type=click.Path(exists=True))
@click.option(
    "-n", "--namespace", help="Kubernetes namespace (default: from swap file)"
)
@click.option(
    "--delete-pvc",
    is_flag=True,
    help="Also delete PersistentVolumeClaim (destroys data)",
)
@click.option("--no-sync", is_flag=True, help="Delete without syncing changes back")
def delete(file: str, namespace: str | None, delete_pvc: bool, no_sync: bool):
    """Sync changes, then delete cluster resources.

    FILE is the local notebook that was previously deployed.
    PVC is preserved by default to protect your data.
    """
    delete_notebook(file, namespace=namespace, delete_pvc=delete_pvc, no_sync=no_sync)


@cli.command()
@click.argument("directory", default=".", type=click.Path(exists=True))
def status(directory: str):
    """List active notebook deployments.

    DIRECTORY to scan for swap files (default: current directory).
    """
    show_status(directory)


if __name__ == "__main__":
    cli()
