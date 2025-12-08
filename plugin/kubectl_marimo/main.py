"""CLI entry point for kubectl-marimo."""

import click

from . import __version__
from .apply import apply_notebook
from .delete import delete_notebook
from .status import show_status
from .sync import sync_notebook


@click.group()
@click.version_option(version=__version__)
def cli():
    """Deploy marimo notebooks to Kubernetes.

    Examples:

        kubectl marimo apply notebook.py
        kubectl marimo apply notebook.md
        kubectl marimo sync notebook.py
        kubectl marimo delete notebook.py
        kubectl marimo status
    """
    pass


@cli.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("-n", "--namespace", default="default", help="Kubernetes namespace")
@click.option("--dry-run", is_flag=True, help="Print YAML without applying")
@click.option("--force", "-f", is_flag=True, help="Overwrite without prompting")
def apply(file: str, namespace: str, dry_run: bool, force: bool):
    """Deploy a notebook to the cluster.

    FILE is a marimo notebook (.py, .md) or MarimoNotebook YAML.
    """
    apply_notebook(file, namespace=namespace, dry_run=dry_run, force=force)


@cli.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("-n", "--namespace", help="Kubernetes namespace (default: from swap file)")
@click.option("--force", "-f", is_flag=True, help="Overwrite local file without prompting")
def sync(file: str, namespace: str | None, force: bool):
    """Pull changes from pod back to local file.

    FILE is the local notebook that was previously applied.
    """
    sync_notebook(file, namespace=namespace, force=force)


@cli.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("-n", "--namespace", help="Kubernetes namespace (default: from swap file)")
@click.option("--keep-pvc", is_flag=True, help="Keep PersistentVolumeClaim (preserve data)")
@click.option("--no-sync", is_flag=True, help="Delete without syncing changes back")
def delete(file: str, namespace: str | None, keep_pvc: bool, no_sync: bool):
    """Sync changes, then delete cluster resources.

    FILE is the local notebook that was previously applied.
    """
    delete_notebook(file, namespace=namespace, keep_pvc=keep_pvc, no_sync=no_sync)


@cli.command()
@click.argument("directory", default=".", type=click.Path(exists=True))
def status(directory: str):
    """List active notebook deployments.

    DIRECTORY to scan for swap files (default: current directory).
    """
    show_status(directory)


if __name__ == "__main__":
    cli()
