"""Deploy command implementation."""

import re
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

import click

from .formats import parse_file
from .k8s import apply_resource
from .resources import build_marimo_notebook, resource_name, compute_hash, to_yaml
from .swap import read_swap_file, write_swap_file, create_swap_meta
from .sync import sync_notebook


def deploy_notebook(
    file_path: str,
    mode: str = "edit",
    namespace: str = "default",
    source: str | None = None,
    dry_run: bool = False,
    headless: bool = False,
    force: bool = False,
) -> None:
    """Deploy a notebook to the cluster.

    Args:
        file_path: Path to notebook file or directory
        mode: Marimo mode - "edit" (interactive) or "run" (read-only)
        namespace: Kubernetes namespace
        source: Data source URI (cw://, sshfs://, file://)
        dry_run: Print YAML without applying
        headless: Deploy without port-forward or browser
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
                click.echo(
                    f"Warning: Local file '{file_path}' modified since last deploy."
                )
                if not click.confirm("Continue and overwrite tracking?"):
                    click.echo("Deploy cancelled")
                    return

        # Parse file content and frontmatter
        content, frontmatter = parse_file(file_path)
        if content is None:
            click.echo(f"Error: Could not parse '{file_path}'", err=True)
            sys.exit(1)
        name = resource_name(file_path, frontmatter)

    # Build resource (separates local mounts from remote)
    resource, local_mounts = build_marimo_notebook(
        name=name,
        namespace=namespace,
        content=content,
        frontmatter=frontmatter,
        mode=mode,
        source=source,
    )

    if dry_run:
        click.echo(to_yaml(resource))
        if local_mounts:
            click.echo("\n# Local mounts (handled by plugin via kubectl cp):")
            for src, dest, scheme in local_mounts:
                click.echo(f"#   {src} → {dest}")
        return

    # Apply to cluster
    if not apply_resource(resource):
        sys.exit(1)

    # Handle local mounts - need to wait for pod ready first
    if local_mounts:
        click.echo(f"Waiting for {name} to be ready for local sync...")
        if wait_for_ready(name, namespace):
            for src, dest, _scheme in local_mounts:
                sync_local_source(name, namespace, src, dest)
        else:
            click.echo("Warning: Pod not ready, skipping local sync", err=True)

    # Create swap file for tracking deployment
    file_hash = compute_hash(content) if content else ""
    # Convert local_mounts to serializable format
    mounts_data = (
        [{"local": src, "remote": dest} for src, dest, _ in local_mounts]
        if local_mounts
        else None
    )
    meta = create_swap_meta(
        name=name,
        namespace=namespace,
        original_file=file_path,
        file_hash=file_hash,
        local_mounts=mounts_data,
    )
    write_swap_file(file_path, meta)
    from .swap import swap_file_path

    click.echo(f"Tracking deployment in {swap_file_path(file_path)}")

    # Get port from frontmatter
    port = 2718
    if frontmatter and "port" in frontmatter:
        port = int(frontmatter["port"])

    if headless:
        # Print access info for manual port-forward
        print_access_info(name, namespace, mode, frontmatter)
    else:
        # Auto port-forward and open browser
        open_notebook(name, namespace, port, file_path)


def print_access_info(
    name: str, namespace: str, mode: str, frontmatter: dict | None
) -> None:
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


def open_notebook(name: str, namespace: str, port: int, file_path: str) -> None:
    """Port-forward and open browser.

    Args:
        name: Resource name
        namespace: Kubernetes namespace
        port: Service port
        file_path: Path to local notebook file (for sync on exit)
    """
    # Wait for pod ready
    click.echo(f"Waiting for {name} to be ready...")
    if not wait_for_ready(name, namespace):
        click.echo("Warning: Pod may not be ready, continuing anyway...", err=True)

    # Extract access token from pod logs (retry a few times as marimo may still be starting)
    token = None
    for _ in range(5):
        token = get_access_token(name, namespace)
        if token:
            break
        time.sleep(1)

    # Find available local port
    local_port = find_available_port(port)

    # Build URL with token
    url = f"http://localhost:{local_port}"
    if token:
        url = f"{url}?access_token={token}"

    click.echo(f"Opening {url}")
    click.echo("Press Ctrl+C to stop port-forward and sync changes")
    click.echo()

    # Open browser
    webbrowser.open(url)

    # Port-forward (blocking)
    try:
        subprocess.run(
            [
                "kubectl",
                "port-forward",
                "-n",
                namespace,
                f"svc/{name}",
                f"{local_port}:{port}",
            ]
        )
    except KeyboardInterrupt:
        click.echo("\nSyncing changes...")
        try:
            sync_notebook(file_path, namespace=namespace, force=True)
        except Exception as e:
            click.echo(f"Warning: Sync failed: {e}", err=True)
        click.echo("Done")


def get_access_token(name: str, namespace: str) -> str | None:
    """Extract access token from marimo pod logs.

    Args:
        name: Pod name
        namespace: Kubernetes namespace

    Returns:
        Access token if found, None otherwise
    """
    cmd = ["kubectl", "logs", "-n", namespace, name, "-c", "marimo"]
    result = subprocess.run(cmd, capture_output=True, text=True)

    # marimo logs: "URL: http://0.0.0.0:2718?access_token=ABC123"
    match = re.search(r'access_token=([^\s&"]+)', result.stdout)
    return match.group(1) if match else None


def wait_for_ready(name: str, namespace: str, timeout: int = 120) -> bool:
    """Wait for pod to be ready.

    Args:
        name: Pod name
        namespace: Kubernetes namespace
        timeout: Timeout in seconds

    Returns:
        True if pod is ready, False otherwise
    """
    cmd = [
        "kubectl",
        "wait",
        "-n",
        namespace,
        f"pod/{name}",
        "--for=condition=Ready",
        f"--timeout={timeout}s",
    ]
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0


def sync_local_source(
    name: str,
    namespace: str,
    local_path: str,
    mount_point: str,
) -> bool:
    """Copy local files to pod.

    Args:
        name: Pod name
        namespace: Kubernetes namespace
        local_path: Local directory to copy
        mount_point: Target path inside pod

    Returns:
        True if sync succeeded
    """
    path = Path(local_path)
    if not path.exists():
        click.echo(f"Warning: Local path '{local_path}' does not exist", err=True)
        return False

    # Create target directory in pod
    mkdir_cmd = [
        "kubectl",
        "exec",
        "-n",
        namespace,
        name,
        "-c",
        "marimo",
        "--",
        "mkdir",
        "-p",
        mount_point,
    ]
    subprocess.run(mkdir_cmd, capture_output=True)

    # Use kubectl cp to copy files
    # For directories, copy contents; for files, copy the file
    if path.is_dir():
        # Add trailing /. to copy contents into mount_point
        src = f"{local_path}/."
    else:
        src = local_path

    cp_cmd = [
        "kubectl",
        "cp",
        src,
        f"{namespace}/{name}:{mount_point}",
        "-c",
        "marimo",
    ]
    result = subprocess.run(cp_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        click.echo(f"Warning: Failed to sync {local_path}: {result.stderr}", err=True)
        return False

    # Clean up .marimo swap files that may have been copied
    cleanup_cmd = [
        "kubectl",
        "exec",
        "-n",
        namespace,
        name,
        "-c",
        "marimo",
        "--",
        "find",
        mount_point,
        "-name",
        "*.marimo",
        "-delete",
    ]
    subprocess.run(cleanup_cmd, capture_output=True)

    click.echo(f"Synced {local_path} → {mount_point}")
    return True


def find_available_port(preferred: int) -> int:
    """Find available local port, preferring the given one.

    Args:
        preferred: Preferred port to use

    Returns:
        Available port (preferred if available, random otherwise)
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("localhost", preferred))
            return preferred
        except OSError:
            s.bind(("localhost", 0))
            return s.getsockname()[1]
