"""File format parsers for marimo notebooks."""

from pathlib import Path
from typing import Any

from .markdown import parse_markdown
from .python import parse_python


def parse_file(file_path: str) -> tuple[str | None, dict[str, Any] | None]:
    """Parse a notebook file and extract content and frontmatter.

    Returns (content, frontmatter) or (None, None) if parsing fails.
    """
    path = Path(file_path)
    content = path.read_text()

    if path.suffix == ".md":
        return parse_markdown(content)
    elif path.suffix == ".py":
        return parse_python(content)
    elif path.suffix in (".yaml", ".yml"):
        # Pass through YAML files - they're already MarimoNotebook resources
        return content, None
    else:
        # Try to detect format from content
        if content.strip().startswith("---"):
            return parse_markdown(content)
        elif "import marimo" in content or "@app.cell" in content:
            return parse_python(content)
        else:
            # Default to treating as Python
            return content, None


__all__ = ["parse_file", "parse_markdown", "parse_python"]
