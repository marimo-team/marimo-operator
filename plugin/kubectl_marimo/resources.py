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
    return slugify(path.stem)


def build_marimo_notebook(
    name: str,
    namespace: str,
    content: str,
    frontmatter: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build MarimoNotebook custom resource."""
    spec: dict[str, Any] = {
        "content": content,
    }

    # Apply frontmatter settings
    if frontmatter:
        if "image" in frontmatter:
            spec["image"] = frontmatter["image"]
        if "port" in frontmatter:
            spec["port"] = int(frontmatter["port"])
        if "storage" in frontmatter:
            spec["storage"] = {"size": frontmatter["storage"]}
        if "auth" in frontmatter:
            if frontmatter["auth"] == "none":
                spec["auth"] = {}  # Empty auth block = --no-token

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
