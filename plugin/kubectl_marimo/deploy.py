"""Deploy command implementation."""

import configparser
import os
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


def ensure_cw_credentials(namespace: str) -> bool:
    """Create cw-credentials secret from ~/.s3cfg if needed.

    Args:
        namespace: Kubernetes namespace

    Returns:
        True if secret exists or was created, False if no credentials available
    """
    s3cfg_path = os.path.expanduser("~/.s3cfg")
    if not os.path.exists(s3cfg_path):
        click.echo(
            "Warning: ~/.s3cfg not found. Run 's3cmd --configure' to set up credentials.",
            err=True,
        )
        return False

    # Check if secret already exists
    result = subprocess.run(
        ["kubectl", "get", "secret", "cw-credentials", "-n", namespace],
        capture_output=True,
    )
    if result.returncode == 0:
        return True  # Already exists

    # Parse ~/.s3cfg
    config = configparser.ConfigParser()
    config.read(s3cfg_path)

    try:
        access_key = config.get("default", "access_key")
        secret_key = config.get("default", "secret_key")
    except (configparser.NoSectionError, configparser.NoOptionError) as e:
        click.echo(f"Warning: Could not read credentials from ~/.s3cfg: {e}", err=True)
        return False

    # Create secret
    result = subprocess.run(
        [
            "kubectl",
            "create",
            "secret",
            "generic",
            "cw-credentials",
            "-n",
            namespace,
            f"--from-literal=AWS_ACCESS_KEY_ID={access_key}",
            f"--from-literal=AWS_SECRET_ACCESS_KEY={secret_key}",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        click.echo(
            f"Warning: Failed to create cw-credentials secret: {result.stderr}",
            err=True,
        )
        return False

    click.echo(f"Created cw-credentials secret in namespace {namespace}")
    return True


def has_cw_mounts(resource: dict) -> bool:
    """Check if resource has any cw:// mounts."""
    mounts = resource.get("spec", {}).get("mounts", [])
    return any(m.startswith("cw://") for m in mounts)


def has_sshfs_sidecars(resource: dict) -> bool:
    """Check if resource has any sshfs sidecars."""
    sidecars = resource.get("spec", {}).get("sidecars", [])
    return any(s.get("name", "").startswith("sshfs-") for s in sidecars)


def ensure_ssh_pubkey(namespace: str, dry_run: bool = False) -> bool:
    """Create ssh-pubkey secret from public key.

    Args:
        namespace: K8s namespace
        dry_run: If True, only print what would be done

    Returns True if secret exists or was created (or would be in dry_run).
    """
    # Check if secret already exists
    if not dry_run:
        result = subprocess.run(
            ["kubectl", "get", "secret", "ssh-pubkey", "-n", namespace],
            capture_output=True,
        )
        if result.returncode == 0:
            return True  # Already exists

    # Check default locations for public key
    default_paths = [
        Path.home() / ".ssh" / "id_rsa.pub",
        Path.home() / ".ssh" / "id_ed25519.pub",
    ]

    pub_key_path = None
    for p in default_paths:
        if p.exists():
            pub_key_path = p
            break

    if pub_key_path:
        # Found default key - confirm with user
        if not click.confirm(f"Use SSH key at {pub_key_path}?"):
            # User declined default - ask for path or suggest creation
            key_input = click.prompt(
                "Enter path to SSH public key (or press Enter to generate)",
                default="",
            )
            if key_input:
                pub_key_path = Path(key_input).expanduser()
            else:
                # Generate new key
                click.echo("Generating SSH key pair...")
                new_key_path = Path.home() / ".ssh" / "id_ed25519"
                subprocess.run(
                    ["ssh-keygen", "-t", "ed25519", "-f", str(new_key_path), "-N", ""],
                    check=True,
                )
                pub_key_path = Path(str(new_key_path) + ".pub")
    else:
        # No default key found
        click.echo("No SSH key found at ~/.ssh/id_rsa.pub or ~/.ssh/id_ed25519.pub")
        key_input = click.prompt(
            "Enter path to SSH public key (or press Enter to generate)",
            default="",
        )
        if key_input:
            pub_key_path = Path(key_input).expanduser()
        else:
            # Generate new key
            click.echo("Generating SSH key pair...")
            new_key_path = Path.home() / ".ssh" / "id_ed25519"
            subprocess.run(
                ["ssh-keygen", "-t", "ed25519", "-f", str(new_key_path), "-N", ""],
                check=True,
            )
            pub_key_path = Path(str(new_key_path) + ".pub")

    if not pub_key_path or not pub_key_path.exists():
        click.echo(f"Error: SSH key not found at {pub_key_path}", err=True)
        return False

    if dry_run:
        click.echo(f"# Would create ssh-pubkey secret from {pub_key_path}")
        return True

    # Create secret
    result = subprocess.run(
        [
            "kubectl",
            "create",
            "secret",
            "generic",
            "ssh-pubkey",
            "-n",
            namespace,
            f"--from-file=authorized_keys={pub_key_path}",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        click.echo(f"Created ssh-pubkey secret in namespace {namespace}")
        return True
    else:
        click.echo(
            f"Warning: Failed to create ssh-pubkey secret: {result.stderr}", err=True
        )
        return False


def setup_local_sshfs_mount(
    name: str,
    namespace: str,
    remote_path: str,
    local_mount: str,
    ssh_port: int = 2222,
) -> subprocess.Popen | None:
    """Set up local sshfs mount to pod using key-based auth.

    Args:
        name: Resource name
        namespace: Kubernetes namespace
        remote_path: Path inside the pod to mount
        local_mount: Local directory to mount to
        ssh_port: SSH port to forward

    Returns:
        Port-forward process, or None if setup failed
    """
    # Check sshfs is installed
    result = subprocess.run(["which", "sshfs"], capture_output=True)
    sshfs_available = result.returncode == 0

    # Find available local port for SSH
    local_ssh_port = find_available_port(ssh_port)

    # Always start port-forward for SSH access (even without sshfs)
    pf_proc = subprocess.Popen(
        [
            "kubectl",
            "port-forward",
            "-n",
            namespace,
            f"svc/{name}",
            f"{local_ssh_port}:2222",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait for port-forward to be ready
    time.sleep(2)

    if not sshfs_available:
        click.echo("sshfs not installed - skipping local mount.", err=True)
        click.echo("You can SSH directly to access files:", err=True)
        click.echo(f"  ssh -p {local_ssh_port} marimo@localhost", err=True)
        return pf_proc  # Return port-forward process so it stays alive

    # Create local mount directory
    local_mount_path = Path(local_mount).expanduser().resolve()
    local_mount_path.mkdir(parents=True, exist_ok=True)

    # Find user's private key
    private_key = None
    for key_name in ["id_rsa", "id_ed25519"]:
        key_path = Path.home() / ".ssh" / key_name
        if key_path.exists():
            private_key = key_path
            break

    if not private_key:
        click.echo("Warning: No SSH private key found, sshfs may fail", err=True)
        private_key = Path.home() / ".ssh" / "id_rsa"  # Try anyway

    # Mount via sshfs
    sshfs_cmd = [
        "sshfs",
        f"marimo@localhost:{remote_path}",
        str(local_mount_path),
        "-p",
        str(local_ssh_port),
        "-o",
        f"IdentityFile={private_key}",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
    ]

    result = subprocess.run(sshfs_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        click.echo(f"Warning: sshfs mount failed: {result.stderr}", err=True)
        pf_proc.terminate()
        return None

    click.echo(f"Mounted pod:{remote_path} → {local_mount_path}")
    return pf_proc


def cleanup_sshfs_mount(local_mount: str, pf_proc: subprocess.Popen | None) -> None:
    """Unmount sshfs and stop port-forward.

    Args:
        local_mount: Local mount path to unmount
        pf_proc: Port-forward process to terminate
    """
    local_mount_path = Path(local_mount).expanduser().resolve()

    # Unmount sshfs
    if local_mount_path.exists():
        subprocess.run(["fusermount", "-u", str(local_mount_path)], capture_output=True)
        # Also try umount on macOS
        subprocess.run(["umount", str(local_mount_path)], capture_output=True)

    # Stop port-forward
    if pf_proc:
        pf_proc.terminate()


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
        source: Data source URI (cw://, sshfs://, rsync://)
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
    resource, rsync_mounts, sshfs_mounts = build_marimo_notebook(
        name=name,
        namespace=namespace,
        content=content,
        frontmatter=frontmatter,
        mode=mode,
        source=source,
    )

    if dry_run:
        click.echo(to_yaml(resource))
        if rsync_mounts:
            click.echo("\n# Rsync mounts (handled by plugin via kubectl cp):")
            for src, dest, scheme in rsync_mounts:
                click.echo(f"#   {src} → {dest}")
        if sshfs_mounts:
            click.echo("\n# SSHFS mounts (plugin mounts pod filesystem locally):")
            for remote_path, local_mount in sshfs_mounts:
                click.echo(f"#   pod:{remote_path} → {local_mount}")
        # Check if we'd need SSH pubkey
        if has_sshfs_sidecars(resource):
            ensure_ssh_pubkey(namespace, dry_run=True)
        return

    # Ensure cw-credentials secret exists if using cw:// mounts
    if has_cw_mounts(resource):
        ensure_cw_credentials(namespace)

    # Ensure ssh-pubkey secret exists if using sshfs sidecars
    if has_sshfs_sidecars(resource):
        if not ensure_ssh_pubkey(namespace):
            click.echo("Error: SSH pubkey required for sshfs mounts", err=True)
            sys.exit(1)

    # Apply to cluster
    if not apply_resource(resource):
        sys.exit(1)

    # Handle rsync mounts - need to wait for pod ready first
    if rsync_mounts:
        click.echo(f"Waiting for {name} to be ready for local sync...")
        if wait_for_ready(name, namespace):
            for src, dest, _scheme in rsync_mounts:
                sync_local_source(name, namespace, src, dest)
        else:
            click.echo("Warning: Pod not ready, skipping local sync", err=True)

    # Create swap file for tracking deployment
    file_hash = compute_hash(content) if content else ""
    # Convert mounts to serializable format
    mounts_data = None
    if rsync_mounts:
        mounts_data = [{"local": src, "remote": dest} for src, dest, _ in rsync_mounts]
    if sshfs_mounts:
        mounts_data = mounts_data or []
        mounts_data.extend(
            [
                {"local": local, "remote": remote, "type": "sshfs"}
                for remote, local in sshfs_mounts
            ]
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
        print_access_info(name, namespace, mode, frontmatter, sshfs_mounts)
    else:
        # Auto port-forward and open browser
        open_notebook(name, namespace, port, file_path, sshfs_mounts)


def print_access_info(
    name: str,
    namespace: str,
    mode: str,
    frontmatter: dict | None,
    sshfs_mounts: list[tuple[str, str]] | None = None,
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

    # Print sshfs mount instructions
    if sshfs_mounts:
        click.echo()
        click.echo("To mount pod filesystem locally:")
        click.echo(f"  kubectl port-forward -n {namespace} svc/{name} 2222:2222 &")
        for remote_path, local_mount in sshfs_mounts:
            click.echo(f"  mkdir -p {local_mount}")
            click.echo(f"  sshfs marimo@localhost:{remote_path} {local_mount} -p 2222")


def open_notebook(
    name: str,
    namespace: str,
    port: int,
    file_path: str,
    sshfs_mounts: list[tuple[str, str]] | None = None,
) -> None:
    """Port-forward and open browser.

    Args:
        name: Resource name
        namespace: Kubernetes namespace
        port: Service port
        file_path: Path to local notebook file (for sync on exit)
        sshfs_mounts: List of (remote_path, local_mount) for sshfs mounts
    """
    # Wait for pod ready
    click.echo(f"Waiting for {name} to be ready...")
    if not wait_for_ready(name, namespace):
        click.echo("Warning: Pod may not be ready, continuing anyway...", err=True)

    # Set up local sshfs mounts if any
    sshfs_procs: list[tuple[str, subprocess.Popen | None]] = []
    if sshfs_mounts:
        click.echo("Setting up sshfs mounts...")
        for remote_path, local_mount in sshfs_mounts:
            pf_proc = setup_local_sshfs_mount(name, namespace, remote_path, local_mount)
            sshfs_procs.append((local_mount, pf_proc))

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
        # Clean up sshfs mounts
        if sshfs_procs:
            click.echo("\nCleaning up sshfs mounts...")
            for local_mount, pf_proc in sshfs_procs:
                cleanup_sshfs_mount(local_mount, pf_proc)

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
