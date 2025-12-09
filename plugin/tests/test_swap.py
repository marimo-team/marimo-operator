"""Tests for swap file management."""

from pathlib import Path

from kubectl_marimo.swap import (
    SwapMeta,
    swap_file_path,
    write_swap_file,
    read_swap_file,
    delete_swap_file,
    create_swap_meta,
)


class TestSwapFilePath:
    def test_basic(self):
        path = swap_file_path("/path/to/notebook.py")
        assert path == Path("/path/to/.notebook.py.marimo")

    def test_relative(self):
        path = swap_file_path("notebook.py")
        assert path == Path(".notebook.py.marimo")


class TestSwapMeta:
    def test_to_dict(self):
        meta = SwapMeta(
            name="test",
            namespace="default",
            applied_at="2025-01-01T00:00:00Z",
            original_file="/path/to/file.py",
            file_hash="sha256:abc123",
        )
        d = meta.to_dict()
        assert d["name"] == "test"
        assert d["namespace"] == "default"

    def test_from_dict(self):
        d = {
            "name": "test",
            "namespace": "ns",
            "applied_at": "2025-01-01T00:00:00Z",
            "original_file": "/path",
            "file_hash": "sha256:abc",
        }
        meta = SwapMeta.from_dict(d)
        assert meta.name == "test"
        assert meta.namespace == "ns"


class TestCreateSwapMeta:
    def test_creates_timestamp(self):
        meta = create_swap_meta(
            name="test",
            namespace="default",
            original_file="file.py",
            file_hash="sha256:abc",
        )
        assert meta.applied_at.endswith("Z")
        assert "T" in meta.applied_at


class TestSwapFileIO:
    def test_write_read_roundtrip(self, tmp_path):
        notebook_file = tmp_path / "notebook.py"
        notebook_file.write_text("content")

        meta = SwapMeta(
            name="test",
            namespace="default",
            applied_at="2025-01-01T00:00:00Z",
            original_file=str(notebook_file),
            file_hash="sha256:abc",
        )
        write_swap_file(str(notebook_file), meta)

        loaded = read_swap_file(str(notebook_file))
        assert loaded is not None
        assert loaded.name == "test"
        assert loaded.namespace == "default"

    def test_read_nonexistent(self, tmp_path):
        notebook_file = tmp_path / "missing.py"
        result = read_swap_file(str(notebook_file))
        assert result is None

    def test_delete(self, tmp_path):
        notebook_file = tmp_path / "notebook.py"
        notebook_file.write_text("content")

        meta = SwapMeta(
            name="test",
            namespace="default",
            applied_at="2025-01-01T00:00:00Z",
            original_file=str(notebook_file),
            file_hash="sha256:abc",
        )
        write_swap_file(str(notebook_file), meta)

        # Verify swap file exists
        swap_path = swap_file_path(str(notebook_file))
        assert swap_path.exists()

        # Delete it
        result = delete_swap_file(str(notebook_file))
        assert result is True
        assert not swap_path.exists()

    def test_delete_nonexistent(self, tmp_path):
        notebook_file = tmp_path / "missing.py"
        result = delete_swap_file(str(notebook_file))
        assert result is False


class TestSwapMetaWithMounts:
    def test_to_dict_with_mounts(self):
        meta = SwapMeta(
            name="test",
            namespace="default",
            applied_at="2025-01-01T00:00:00Z",
            original_file="/path/to/file.py",
            file_hash="sha256:abc123",
            local_mounts=[{"local": "/src", "remote": "/dest"}],
        )
        d = meta.to_dict()
        assert d["local_mounts"] == [{"local": "/src", "remote": "/dest"}]

    def test_from_dict_with_mounts(self):
        d = {
            "name": "test",
            "namespace": "ns",
            "applied_at": "2025-01-01T00:00:00Z",
            "original_file": "/path",
            "file_hash": "sha256:abc",
            "local_mounts": [{"local": "/a", "remote": "/b"}],
        }
        meta = SwapMeta.from_dict(d)
        assert meta.local_mounts == [{"local": "/a", "remote": "/b"}]

    def test_roundtrip_with_mounts(self, tmp_path):
        notebook_file = tmp_path / "notebook.py"
        notebook_file.write_text("content")

        meta = SwapMeta(
            name="test",
            namespace="default",
            applied_at="2025-01-01T00:00:00Z",
            original_file=str(notebook_file),
            file_hash="sha256:abc",
            local_mounts=[{"local": "./examples", "remote": "/data"}],
        )
        write_swap_file(str(notebook_file), meta)
        loaded = read_swap_file(str(notebook_file))
        assert loaded.local_mounts == [{"local": "./examples", "remote": "/data"}]

    def test_create_swap_meta_with_mounts(self):
        meta = create_swap_meta(
            name="test",
            namespace="default",
            original_file="file.py",
            file_hash="sha256:abc",
            local_mounts=[{"local": "/local", "remote": "/remote"}],
        )
        assert meta.local_mounts == [{"local": "/local", "remote": "/remote"}]
