"""Status command implementation."""

from datetime import datetime, timezone
from pathlib import Path

import click

from .swap import SwapMeta


def show_status(directory: str = ".") -> None:
    """List all active notebook deployments in a directory."""
    dir_path = Path(directory)

    # Find all swap files
    swap_files = list(dir_path.glob(".*.marimo"))

    if not swap_files:
        click.echo("No active notebook deployments found")
        return

    # Print header
    click.echo(f"{'FILE':<30} {'NAME':<20} {'NAMESPACE':<15} {'DEPLOYED'}")
    click.echo("-" * 80)

    for swap_file in sorted(swap_files):
        meta = read_swap_file_direct(swap_file)
        if meta is None:
            continue

        # Extract original filename from swap file path
        orig_file = swap_file.name[1:]  # Remove leading dot
        orig_file = orig_file.rsplit(".marimo", 1)[0]

        # Calculate time since deploy
        time_str = format_elapsed(meta.applied_at)

        click.echo(f"{orig_file:<30} {meta.name:<20} {meta.namespace:<15} {time_str}")


def read_swap_file_direct(swap_path: Path) -> SwapMeta | None:
    """Read swap file directly from path."""
    import json

    if not swap_path.exists():
        return None
    try:
        with open(swap_path) as f:
            data = json.load(f)
        return SwapMeta.from_dict(data)
    except (json.JSONDecodeError, KeyError):
        return None


def format_elapsed(iso_timestamp: str) -> str:
    """Format elapsed time since timestamp."""
    try:
        applied = datetime.fromisoformat(iso_timestamp.rstrip("Z"))
        elapsed = datetime.now(timezone.utc) - applied
        total_seconds = elapsed.total_seconds()

        if total_seconds < 60:
            return "just now"
        elif total_seconds < 3600:  # < 1 hour
            minutes = int(total_seconds / 60)
            return f"{minutes}m ago"
        elif total_seconds < 86400:  # < 24 hours
            hours = int(total_seconds / 3600)
            return f"{hours}h ago"
        else:
            days = int(total_seconds / 86400)
            return f"{days}d ago"
    except (ValueError, TypeError):
        return "unknown"
