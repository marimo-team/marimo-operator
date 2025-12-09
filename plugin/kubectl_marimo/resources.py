"""Generate Kubernetes resources for MarimoNotebook."""

import hashlib
import re
from pathlib import Path
from typing import Any


def parse_mount_uri(uri: str) -> tuple[str, str, str | None, str | None]:
    """Parse mount URI in Docker-style format.

    Format: <scheme>://[user@host:]<source>[:mount_point]

    Local detection: no '@' in URI (supports relative and absolute paths)
    Remote detection: has '@' (user@host format)

    Mount point handling:
    - Absolute (/data) → use as-is
    - Relative (data) → prepend /home/marimo/notebooks/

    Returns: (scheme, source_path, user_host, mount_point)

    Examples:
        rsync://examples:data           → ('rsync', 'examples', None, '/home/marimo/notebooks/data')
        rsync://examples:/data          → ('rsync', 'examples', None, '/data')
        rsync:///abs/path:/mnt          → ('rsync', '/abs/path', None, '/mnt')
        rsync://relative/path           → ('rsync', 'relative/path', None, None)
        rsync://user@host:/data:/mnt    → ('rsync', '/data', 'user@host', '/mnt')
        rsync://user@host:/data         → ('rsync', '/data', 'user@host', None)
        sshfs://user@host:/remote:/mnt  → ('sshfs', '/remote', 'user@host', '/mnt')
    """
    # Extract scheme
    match = re.match(r"^(\w+)://(.*)$", uri)
    if not match:
        raise ValueError(f"Invalid mount URI: {uri}")

    scheme = match.group(1)
    remainder = match.group(2)

    # Local mount: rsync scheme with no '@' means local path (relative or absolute)
    # rsync://examples:/data or rsync:///abs/path:/mnt
    # Note: only rsync supports local paths; other schemes (sshfs, cw) are always remote
    if scheme == "rsync" and "@" not in remainder:
        # Split on last ':' to get source and optional mount point
        # examples:data → source=examples, mount=/home/marimo/notebooks/data
        # examples:/data → source=examples, mount=/data
        # /abs/path:/mnt → source=/abs/path, mount=/mnt
        parts = remainder.rsplit(":", 1)
        if len(parts) == 2 and parts[1]:
            source, mount = parts
            # Relative mount point → prepend /home/marimo/notebooks/
            if not mount.startswith("/"):
                mount = f"/home/marimo/notebooks/{mount}"
            return (scheme, source, None, mount)
        return (scheme, remainder, None, None)

    # Remote mount: rsync://user@host:/path or rsync://user@host:/path:/mount
    # Format: user@host:/source or user@host:/source:/mount
    # Split at first : that follows the host
    colon_idx = remainder.find(":/")
    if colon_idx == -1:
        raise ValueError(f"Invalid remote mount URI: {uri}")

    user_host = remainder[:colon_idx]
    path_part = remainder[colon_idx + 1 :]  # includes leading /

    # Check for mount point (another : followed by /)
    # /data:/mnt → source=/data, mount=/mnt
    parts = path_part.rsplit(":", 1)
    if len(parts) == 2 and parts[1].startswith("/"):
        return (scheme, parts[0], user_host, parts[1])
    return (scheme, path_part, user_host, None)


def is_local_mount(uri: str) -> bool:
    """Check if mount URI is local (no host).

    Local: rsync:// with no '@' (relative or absolute paths)
    Remote: has '@' (user@host:/path format) or non-rsync scheme
    """
    _, _, user_host, _ = parse_mount_uri(uri)
    return user_host is None


def filter_mounts(
    mounts: list[str],
) -> tuple[list[str], list[tuple[str, str, str | None]]]:
    """Separate local and remote mounts.

    Returns:
        (remote_mounts, local_mounts)
        - remote_mounts: URIs to pass to CRD (operator handles)
        - local_mounts: list of (source_path, mount_point, scheme) tuples (plugin handles)
    """
    remote_mounts = []
    local_mounts = []

    for i, uri in enumerate(mounts):
        try:
            scheme, source_path, user_host, mount_point = parse_mount_uri(uri)

            if user_host is None:
                # Local mount - plugin handles via kubectl cp
                default_mount = f"/home/marimo/notebooks/mounts/local-{i}"
                local_mounts.append((source_path, mount_point or default_mount, scheme))
            else:
                # Remote mount - pass to CRD as-is
                remote_mounts.append(uri)
        except ValueError:
            # Unknown scheme (e.g., cw://) - pass through to operator
            remote_mounts.append(uri)

    return remote_mounts, local_mounts


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
    namespace: str,
    content: str | None,
    frontmatter: dict[str, Any] | None = None,
    mode: str = "edit",
    source: str | None = None,
) -> tuple[dict[str, Any], list[tuple[str, str, str | None]]]:
    """Build MarimoNotebook custom resource.

    Args:
        name: Resource name
        namespace: Kubernetes namespace
        content: Notebook content (None for directory mode)
        frontmatter: Parsed frontmatter configuration
        mode: Marimo mode - "edit" or "run"
        source: Data source URI (rsync://, sshfs://)

    Returns:
        (resource, local_mounts)
        - resource: CRD dict to apply to cluster
        - local_mounts: list of (source_path, mount_point, scheme) for plugin to handle
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

    # Collect mounts from --source and frontmatter
    all_mounts = []
    if source:
        all_mounts.append(source)
    if frontmatter and "mounts" in frontmatter:
        all_mounts.extend(frontmatter["mounts"])

    # Separate local (plugin handles) from remote (operator handles)
    local_mounts: list[tuple[str, str, str | None]] = []
    if all_mounts:
        remote_mounts, local_mounts = filter_mounts(all_mounts)
        if remote_mounts:
            spec["mounts"] = remote_mounts

    resource = {
        "apiVersion": "marimo.io/v1alpha1",
        "kind": "MarimoNotebook",
        "metadata": {
            "name": name,
            "namespace": namespace,
        },
        "spec": spec,
    }
    return resource, local_mounts


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
