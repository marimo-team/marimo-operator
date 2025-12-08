"""Parser for marimo Python notebooks."""

import re
from typing import Any


def parse_python(content: str) -> tuple[str, dict[str, Any] | None]:
    """Parse marimo Python notebook.

    Extracts PEP 723 inline script metadata if present.
    Returns the full content unchanged.

    Returns (content, frontmatter_dict).
    """
    metadata = extract_pep723_metadata(content)
    return content, metadata


def extract_pep723_metadata(content: str) -> dict[str, Any] | None:
    """Extract PEP 723 inline script metadata.

    PEP 723 metadata is embedded in a comment block:

    # /// script
    # dependencies = ["marimo", "pandas"]
    # ///

    We also look for custom marimo fields:
    # [tool.marimo.k8s]
    # image = "custom-image:latest"
    # storage = "5Gi"
    """
    # Look for PEP 723 script block
    pattern = r'# /// script\n((?:# .*\n)*?)# ///'
    match = re.search(pattern, content)

    if not match:
        return None

    metadata = {}
    block = match.group(1)

    # Parse TOML-like lines
    for line in block.split("\n"):
        line = line.lstrip("# ").strip()
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Parse simple values
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            elif value.startswith("["):
                # List - for now just store as string
                pass
            metadata[key] = value

    # Look for marimo k8s config
    k8s_pattern = r'# \[tool\.marimo\.k8s\]\n((?:# .*\n)*)'
    k8s_match = re.search(k8s_pattern, content)
    if k8s_match:
        for line in k8s_match.group(1).split("\n"):
            line = line.lstrip("# ").strip()
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                metadata[key] = value

    return metadata if metadata else None


def is_marimo_python(content: str) -> bool:
    """Check if content looks like a marimo Python notebook."""
    markers = [
        "import marimo",
        "from marimo import",
        "@app.cell",
        "@app.function",
        "marimo.App(",
    ]
    return any(marker in content for marker in markers)
