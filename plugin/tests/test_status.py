"""Tests for status command."""

import json
from pathlib import Path

from click.testing import CliRunner

from kubectl_marimo.status import show_status, format_elapsed


class TestShowStatus:
    def test_no_swap_files(self, tmp_path, capsys):
        show_status(str(tmp_path))
        captured = capsys.readouterr()
        assert "No active notebook deployments found" in captured.out

    def test_with_swap_files(self, tmp_path, capsys):
        # Create a swap file
        swap_file = tmp_path / ".notebook.py.marimo"
        swap_file.write_text(
            json.dumps(
                {
                    "name": "test-notebook",
                    "namespace": "default",
                    "applied_at": "2025-01-01T00:00:00Z",
                    "original_file": str(tmp_path / "notebook.py"),
                    "file_hash": "sha256:abc",
                }
            )
        )

        show_status(str(tmp_path))
        captured = capsys.readouterr()
        assert "test-notebook" in captured.out
        assert "default" in captured.out

    def test_filter_by_file_path(self, tmp_path, capsys):
        # Create multiple swap files
        swap1 = tmp_path / ".notebook1.py.marimo"
        swap1.write_text(
            json.dumps(
                {
                    "name": "notebook1",
                    "namespace": "default",
                    "applied_at": "2025-01-01T00:00:00Z",
                    "original_file": str(tmp_path / "notebook1.py"),
                    "file_hash": "sha256:abc",
                }
            )
        )

        swap2 = tmp_path / ".notebook2.py.marimo"
        swap2.write_text(
            json.dumps(
                {
                    "name": "notebook2",
                    "namespace": "default",
                    "applied_at": "2025-01-01T00:00:00Z",
                    "original_file": str(tmp_path / "notebook2.py"),
                    "file_hash": "sha256:def",
                }
            )
        )

        # Create the actual file to filter by
        notebook1 = tmp_path / "notebook1.py"
        notebook1.write_text("content")

        # Filter by specific file
        show_status(str(notebook1))
        captured = capsys.readouterr()
        assert "notebook1" in captured.out
        assert "notebook2" not in captured.out

    def test_filter_by_file_shows_matching(self, tmp_path, capsys):
        # Create swap file
        swap_file = tmp_path / ".myapp.py.marimo"
        swap_file.write_text(
            json.dumps(
                {
                    "name": "myapp",
                    "namespace": "prod",
                    "applied_at": "2025-01-01T00:00:00Z",
                    "original_file": str(tmp_path / "myapp.py"),
                    "file_hash": "sha256:xyz",
                }
            )
        )

        # Create the file
        myapp = tmp_path / "myapp.py"
        myapp.write_text("content")

        show_status(str(myapp))
        captured = capsys.readouterr()
        assert "myapp" in captured.out
        assert "prod" in captured.out

    def test_filter_no_match(self, tmp_path, capsys):
        # Create swap file for different notebook
        swap_file = tmp_path / ".other.py.marimo"
        swap_file.write_text(
            json.dumps(
                {
                    "name": "other",
                    "namespace": "default",
                    "applied_at": "2025-01-01T00:00:00Z",
                    "original_file": str(tmp_path / "other.py"),
                    "file_hash": "sha256:abc",
                }
            )
        )

        # Query for non-existent file
        target = tmp_path / "nonexistent.py"
        target.write_text("content")

        show_status(str(target))
        captured = capsys.readouterr()
        assert "No active notebook deployments found" in captured.out

    def test_directory_shows_all(self, tmp_path, capsys):
        # Create multiple swap files
        for i in range(3):
            swap = tmp_path / f".nb{i}.py.marimo"
            swap.write_text(
                json.dumps(
                    {
                        "name": f"nb{i}",
                        "namespace": "default",
                        "applied_at": "2025-01-01T00:00:00Z",
                        "original_file": str(tmp_path / f"nb{i}.py"),
                        "file_hash": f"sha256:{i}",
                    }
                )
            )

        show_status(str(tmp_path))
        captured = capsys.readouterr()
        assert "nb0" in captured.out
        assert "nb1" in captured.out
        assert "nb2" in captured.out


class TestFormatElapsed:
    def test_invalid_timestamp(self):
        assert format_elapsed("not-a-date") == "unknown"

    def test_none_timestamp(self):
        assert format_elapsed(None) == "unknown"

    def test_valid_timestamp_just_now(self):
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        assert format_elapsed(now) == "just now"

    def test_valid_timestamp_with_z_suffix(self):
        # Ensure Z suffix is handled correctly
        result = format_elapsed("2020-01-01T00:00:00Z")
        assert result.endswith("d ago")  # Should be many days ago

    def test_valid_timestamp_without_z_suffix(self):
        result = format_elapsed("2020-01-01T00:00:00")
        assert result.endswith("d ago")
