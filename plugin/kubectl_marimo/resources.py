"""Generate Kubernetes resources for MarimoNotebook."""

import hashlib
import os
import re
from pathlib import Path
from typing import Any


# Default SSH image, configurable via environment
SSH_IMAGE = os.environ.get("SSH_IMAGE", "linuxserver/openssh-server:latest")


def parse_mount_uri(uri: str) -> tuple[str, str]:
    """Parse mount URI into (scheme, path).

    Examples:
        sshfs:///path → ('sshfs', '/path')
        rsync://./data → ('rsync', './data')
        cw://bucket/path → ('cw', 'bucket/path')
    """
    match = re.match(r"^(\w+)://(.*)$", uri)
    if not match:
        raise ValueError(f"Invalid mount URI: {uri}")
    return (match.group(1), match.group(2))


def filter_mounts(
    mounts: list[str],
) -> tuple[list[str], list[tuple[str, str, str]], list[tuple[str, str]]]:
    """Categorize mounts by scheme.

    Returns:
        (cw_mounts, rsync_mounts, sshfs_mounts)
        - cw_mounts: URIs to pass to CRD (operator handles via s3fs sidecar)
        - rsync_mounts: list of (source_path, mount_point, scheme) for kubectl cp
        - sshfs_mounts: list of (remote_path, local_mount) for local sshfs mount
    """
    cw_mounts = []
    rsync_mounts = []
    sshfs_mounts = []

    for i, uri in enumerate(mounts):
        try:
            scheme, path = parse_mount_uri(uri)

            if scheme == "cw":
                # CoreWeave S3 - operator handles
                cw_mounts.append(uri)
            elif scheme == "rsync":
                # Local rsync - plugin handles via kubectl cp
                # Parse optional mount point: rsync://./data:/mnt/data
                parts = path.rsplit(":", 1)
                if len(parts) == 2 and parts[1].startswith("/"):
                    source, mount = parts
                else:
                    source = path
                    mount = f"/home/marimo/notebooks/mounts/local-{i}"
                rsync_mounts.append((source, mount, scheme))
            elif scheme == "sshfs":
                # Local sshfs - plugin runs sshfs locally to mount pod
                # sshfs:///home/marimo/notebooks means mount pod's /home/marimo/notebooks locally
                remote_path = path if path.startswith("/") else f"/{path}"
                local_mount = f"./marimo-mount-{i}"
                sshfs_mounts.append((remote_path, local_mount))
            else:
                # Unknown scheme - pass through to operator
                cw_mounts.append(uri)
        except ValueError:
            # Invalid URI - pass through to operator
            cw_mounts.append(uri)

    return cw_mounts, rsync_mounts, sshfs_mounts


def build_ssh_sidecar(index: int) -> dict[str, Any]:
    """Build SSH sidecar spec for key-based auth.

    The sidecar runs an SSH server that accepts connections using
    the user's public key (stored in ssh-pubkey secret).
    """
    return {
        "name": f"sshfs-{index}",
        "image": SSH_IMAGE,
        "exposePort": 2222,
        "env": [
            {"name": "PASSWORD_ACCESS", "value": "false"},
            {"name": "USER_NAME", "value": "marimo"},
            {"name": "PUID", "value": "1000"},
            {"name": "PGID", "value": "1000"},
            {"name": "PUBLIC_KEY_FILE", "value": "/config/ssh-pubkey/authorized_keys"},
        ],
    }


def compute_hash(content: str) -> str:
    """Compute SHA256 hash of content."""
    h = hashlib.sha256(content.encode()).hexdigest()[:16]
    return f"sha256:{h}"


def slugify(name: str) -> str:
    """Convert name to valid Kubernetes resource name."""
    import re

    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s[:63]  # Max K8s name length


def resource_name(file_path: str, frontmatter: dict[str, Any] | None = None) -> str:
    """Derive resource name from file path or frontmatter title."""
    if frontmatter and frontmatter.get("title"):
        return slugify(frontmatter["title"])
    path = Path(file_path)
    # For directories, use the directory name (resolve "." to actual dir name)
    if path.is_dir():
        # path.name is "" for ".", so always resolve to get actual name
        name = path.name or path.resolve().name
        return slugify(name)
    return slugify(path.stem)


def parse_env(env_dict: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert frontmatter env to K8s EnvVar format.

    Supports:
        env:
          DEBUG: "true"              # Inline value
          API_KEY:
            secret: my-secret        # From secret
            key: api-key
    """
    result = []
    for name, value in env_dict.items():
        if isinstance(value, str):
            # Inline value
            result.append({"name": name, "value": value})
        elif isinstance(value, dict) and "secret" in value:
            # Secret reference
            result.append(
                {
                    "name": name,
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": value["secret"],
                            "key": value.get("key", name.lower()),
                        }
                    },
                }
            )
    return result


def build_marimo_notebook(
    name: str,
    namespace: str | None,
    content: str | None,
    frontmatter: dict[str, Any] | None = None,
    mode: str = "edit",
    source: str | None = None,
) -> tuple[dict[str, Any], list[tuple[str, str, str]], list[tuple[str, str]]]:
    """Build MarimoNotebook custom resource.

    Args:
        name: Resource name
        namespace: Kubernetes namespace (None = use kubectl context)
        content: Notebook content (None for directory mode)
        frontmatter: Parsed frontmatter configuration
        mode: Marimo mode - "edit" or "run"
        source: Data source URI (rsync://, sshfs://, cw://)

    Returns:
        (resource, rsync_mounts, sshfs_mounts)
        - resource: CRD dict to apply to cluster
        - rsync_mounts: list of (source_path, mount_point, scheme) for kubectl cp
        - sshfs_mounts: list of (remote_path, local_mount) for local sshfs
    """
    spec: dict[str, Any] = {
        "mode": mode,
    }

    # Content (file-based deployments, empty string for directory mode)
    spec["content"] = content if content else ""

    # Default storage (PVC by notebook name) - always create PVC
    storage_size = "1Gi"
    if frontmatter and "storage" in frontmatter:
        storage_size = frontmatter["storage"]
    spec["storage"] = {"size": storage_size}

    # Apply frontmatter settings
    if frontmatter:
        if "image" in frontmatter:
            spec["image"] = frontmatter["image"]
        if "port" in frontmatter:
            spec["port"] = int(frontmatter["port"])
        if "auth" in frontmatter:
            if frontmatter["auth"] == "none":
                spec["auth"] = {}  # Empty auth block = --no-token

        # Environment variables
        if "env" in frontmatter:
            spec["env"] = parse_env(frontmatter["env"])

        # Resources (CPU, memory, GPU)
        if "resources" in frontmatter:
            spec["resources"] = frontmatter["resources"]

    # Collect mounts from --source and frontmatter
    all_mounts = []
    if source:
        all_mounts.append(source)
    if frontmatter and "mounts" in frontmatter:
        all_mounts.extend(frontmatter["mounts"])

    # Categorize mounts by scheme
    rsync_mounts: list[tuple[str, str, str]] = []
    sshfs_mounts: list[tuple[str, str]] = []
    if all_mounts:
        cw_mounts, rsync_mounts, sshfs_mounts = filter_mounts(all_mounts)
        if cw_mounts:
            spec["mounts"] = cw_mounts

    # Add SSH sidecars for sshfs mounts
    sidecars = []
    for i, _ in enumerate(sshfs_mounts):
        sidecars.append(build_ssh_sidecar(i))
    if sidecars:
        spec["sidecars"] = sidecars

    metadata = {"name": name}
    if namespace is not None:
        metadata["namespace"] = namespace

    resource = {
        "apiVersion": "marimo.io/v1alpha1",
        "kind": "MarimoNotebook",
        "metadata": metadata,
        "spec": spec,
    }
    return resource, rsync_mounts, sshfs_mounts


def to_yaml(resource: dict[str, Any]) -> str:
    """Convert resource dict to YAML string."""
    import yaml

    return yaml.dump(resource, default_flow_style=False, sort_keys=False)


def detect_content_type(content: str) -> str:
    """Detect if content is markdown or python.

    Returns "markdown" or "python".
    """
    # Check for markdown frontmatter or marimo code blocks
    if content.strip().startswith("---"):
        return "markdown"

    import re

    if re.search(r"```(?:python\s*\{\.marimo\}|\{python\s+marimo\})", content):
        return "markdown"

    # Default to python
    return "python"
