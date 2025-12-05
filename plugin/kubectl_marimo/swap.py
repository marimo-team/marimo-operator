"""Swap file management for tracking deployments."""

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class SwapMeta:
    """Metadata about an active deployment."""

    name: str
    namespace: str
    applied_at: str
    original_file: str
    file_hash: str
    local_mounts: list[dict] | None = None  # [{"local": "/path", "remote": "/mount"}]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SwapMeta":
        return cls(
            name=data["name"],
            namespace=data["namespace"],
            applied_at=data["applied_at"],
            original_file=data["original_file"],
            file_hash=data["file_hash"],
            local_mounts=data.get("local_mounts"),
        )


def swap_file_path(file_path: str) -> Path:
    """Get the swap file path for a notebook file or directory."""
    path = Path(file_path)
    # For directories, use .directory.marimo inside the directory
    if path.is_dir():
        return path / ".directory.marimo"
    return path.parent / f".{path.name}.marimo"


def write_swap_file(file_path: str, meta: SwapMeta) -> None:
    """Write swap file with deployment metadata."""
    swap_path = swap_file_path(file_path)
    with open(swap_path, "w") as f:
        json.dump(meta.to_dict(), f, indent=2)


def read_swap_file(file_path: str) -> Optional[SwapMeta]:
    """Read swap file if it exists."""
    swap_path = swap_file_path(file_path)
    if not swap_path.exists():
        return None
    try:
        with open(swap_path) as f:
            data = json.load(f)
        return SwapMeta.from_dict(data)
    except (json.JSONDecodeError, KeyError):
        return None


def delete_swap_file(file_path: str) -> bool:
    """Delete swap file if it exists."""
    swap_path = swap_file_path(file_path)
    if swap_path.exists():
        swap_path.unlink()
        return True
    return False


def create_swap_meta(
    name: str,
    namespace: str,
    original_file: str,
    file_hash: str,
    local_mounts: list[dict] | None = None,
) -> SwapMeta:
    """Create new swap metadata."""
    return SwapMeta(
        name=name,
        namespace=namespace,
        applied_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        original_file=str(Path(original_file).resolve()),
        file_hash=file_hash,
        local_mounts=local_mounts,
    )
