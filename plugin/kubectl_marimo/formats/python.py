"""Parser for marimo Python notebooks."""

import re
import tomllib
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
    """Extract PEP 723 inline script metadata and marimo k8s config.

    PEP 723 metadata is embedded in a comment block at the top of the file:

        # /// script
        # dependencies = ["marimo", "pandas"]
        #
        # [tool.marimo.k8s]
        # image = "custom-image:latest"
        # storage = "5Gi"
        # ///

    The entire block is valid TOML once the leading `# ` is stripped from each line.
    Marimo k8s config lives under [tool.marimo.k8s] and its subsections.
    """
    pattern = r"# /// script\n((?:#(?: .*)?\n)*?)# ///"
    match = re.search(pattern, content)
    if not match:
        return None

    # Strip exactly the `# ` prefix (2 chars) from each comment line.
    # Bare `#` lines (blank comments) become empty lines, preserving TOML structure.
    lines = []
    for line in match.group(1).splitlines():
        if line.startswith("# "):
            lines.append(line[2:])
        elif line.rstrip() == "#":
            lines.append("")
    toml_str = "\n".join(lines)

    try:
        data = tomllib.loads(toml_str)
    except tomllib.TOMLDecodeError:
        return None

    metadata: dict[str, Any] = {}

    # PEP 723 standard top-level fields (resources.py ignores these, but callers may use them)
    for key in ("dependencies", "requires-python"):
        if key in data:
            metadata[key] = data[key]

    # k8s config lives under [tool.marimo.k8s]
    k8s = data.get("tool", {}).get("marimo", {}).get("k8s", {})

    # Kubernetes resource quantities must be strings; tomllib parses bare integers as int.
    if "resources" in k8s:
        for section, limits in k8s["resources"].items():
            if isinstance(limits, dict):
                k8s["resources"][section] = {k: str(v) for k, v in limits.items()}

    metadata.update(k8s)
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
