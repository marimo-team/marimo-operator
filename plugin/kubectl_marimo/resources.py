"""Generate Kubernetes resources for MarimoNotebook."""

import hashlib
from pathlib import Path
from typing import Any


def compute_hash(content: str) -> str:
    """Compute SHA256 hash of content."""
    h = hashlib.sha256(content.encode()).hexdigest()[:16]
    return f"sha256:{h}"


def slugify(name: str) -> str:
    """Convert name to valid Kubernetes resource name."""
    import re
    s = name.lower()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    s = s.strip('-')
    return s[:63]  # Max K8s name length


def resource_name(file_path: str, frontmatter: dict[str, Any] | None = None) -> str:
    """Derive resource name from file path or frontmatter title."""
    if frontmatter and frontmatter.get("title"):
        return slugify(frontmatter["title"])
    path = Path(file_path)
    # For directories, use the directory name
    if path.is_dir():
        return slugify(path.name if path.name != "." else path.resolve().name)
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
            result.append({
                "name": name,
                "valueFrom": {
                    "secretKeyRef": {
                        "name": value["secret"],
                        "key": value.get("key", name.lower()),
                    }
                }
            })
    return result


def build_marimo_notebook(
    name: str,
    namespace: str,
    content: str | None,
    frontmatter: dict[str, Any] | None = None,
    mode: str = "edit",
    source: str | None = None,
) -> dict[str, Any]:
    """Build MarimoNotebook custom resource.

    Args:
        name: Resource name
        namespace: Kubernetes namespace
        content: Notebook content (None for directory mode)
        frontmatter: Parsed frontmatter configuration
        mode: Marimo mode - "edit" or "run"
        source: Data source URI (cw://, sshfs://, file://)
    """
    spec: dict[str, Any] = {
        "mode": mode,
    }

    # Content (file-based deployments)
    if content:
        spec["content"] = content

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

    # Mounts from --source and frontmatter
    mounts = []
    if source:
        mounts.append(source)
    if frontmatter and "mounts" in frontmatter:
        mounts.extend(frontmatter["mounts"])
    if mounts:
        spec["mounts"] = mounts

    return {
        "apiVersion": "marimo.io/v1alpha1",
        "kind": "MarimoNotebook",
        "metadata": {
            "name": name,
            "namespace": namespace,
        },
        "spec": spec,
    }


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
    if re.search(r'```(?:python\s*\{\.marimo\}|\{python\s+marimo\})', content):
        return "markdown"

    # Default to python
    return "python"
