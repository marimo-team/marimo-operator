"""Parser for marimo markdown notebooks."""

import re
from typing import Any


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

    # Parse frontmatter
    fm = {}
    for line in lines[1:end_idx]:
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            # Remove quotes if present
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            fm[key] = value

    return fm if fm else None


def is_marimo_markdown(content: str) -> bool:
    """Check if content looks like a marimo markdown notebook."""
    # Marimo markdown has frontmatter and/or code blocks with marimo syntax
    has_frontmatter = content.strip().startswith("---")

    # Check for marimo code blocks: ```python {.marimo} or ```{python marimo}
    has_marimo_blocks = bool(
        re.search(r'```(?:python\s*\{\.marimo\}|\{python\s+marimo\})', content)
    )

    return has_frontmatter or has_marimo_blocks
