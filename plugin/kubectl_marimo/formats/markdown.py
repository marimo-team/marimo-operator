"""Parser for marimo markdown notebooks."""

import re
from typing import Any

import yaml


def parse_markdown(content: str) -> tuple[str, dict[str, Any] | None]:
    """Parse marimo markdown notebook.

    Extracts YAML frontmatter and returns the full content.
    Frontmatter fields are used to configure the MarimoNotebook spec.

    Supported frontmatter fields:
        - title: Used as resource name
        - image: Container image
        - port: Marimo server port
        - storage: PVC size (e.g., "1Gi")
        - auth: "none" to disable authentication
        - env: Environment variables (inline or secret refs)
        - mounts: Data source URIs

    Returns (content, frontmatter_dict).
    """
    frontmatter = extract_frontmatter(content)
    return content, frontmatter


def extract_frontmatter(content: str) -> dict[str, Any] | None:
    """Extract YAML frontmatter from markdown content."""
    lines = content.split("\n")

    if not lines or lines[0].strip() != "---":
        return None

    # Find closing ---
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        return None

    # Extract raw frontmatter YAML
    frontmatter_text = "\n".join(lines[1:end_idx])

    try:
        fm = yaml.safe_load(frontmatter_text)
        return fm if isinstance(fm, dict) else None
    except yaml.YAMLError:
        return None


def is_marimo_markdown(content: str) -> bool:
    """Check if content looks like a marimo markdown notebook."""
    # Marimo markdown has frontmatter and/or code blocks with marimo syntax
    has_frontmatter = content.strip().startswith("---")

    # Check for marimo code blocks: ```python {.marimo} or ```{python marimo}
    has_marimo_blocks = bool(
        re.search(r"```(?:python\s*\{\.marimo\}|\{python\s+marimo\})", content)
    )

    return has_frontmatter or has_marimo_blocks
