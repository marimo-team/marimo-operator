"""Tests for resources module."""

import pytest

from kubectl_marimo.resources import (
    compute_hash,
    slugify,
    resource_name,
    build_marimo_notebook,
    detect_content_type,
    parse_env,
    parse_mount_uri,
    is_local_mount,
    filter_mounts,
)


class TestComputeHash:
    def test_consistent(self):
        content = "hello world"
        h1 = compute_hash(content)
        h2 = compute_hash(content)
        assert h1 == h2

    def test_prefix(self):
        h = compute_hash("test")
        assert h.startswith("sha256:")

    def test_different_content(self):
        h1 = compute_hash("content1")
        h2 = compute_hash("content2")
        assert h1 != h2


class TestSlugify:
    def test_lowercase(self):
        assert slugify("MyNotebook") == "mynotebook"

    def test_special_chars(self):
        assert slugify("my notebook!@#") == "my-notebook"

    def test_strip_dashes(self):
        assert slugify("--my-notebook--") == "my-notebook"

    def test_max_length(self):
        long_name = "a" * 100
        result = slugify(long_name)
        assert len(result) <= 63


class TestResourceName:
    def test_from_file_path(self):
        name = resource_name("/path/to/notebook.py")
        assert name == "notebook"

    def test_from_frontmatter_title(self):
        name = resource_name("/path/to/file.py", {"title": "My Notebook"})
        assert name == "my-notebook"

    def test_frontmatter_takes_precedence(self):
        name = resource_name("/path/to/other.py", {"title": "Preferred Name"})
        assert name == "preferred-name"


class TestBuildMarimoNotebook:
    def test_basic(self):
        resource, local_mounts = build_marimo_notebook(
            name="test-notebook",
            namespace="default",
            content="# test content",
        )
        assert resource["apiVersion"] == "marimo.io/v1alpha1"
        assert resource["kind"] == "MarimoNotebook"
        assert resource["metadata"]["name"] == "test-notebook"
        assert resource["metadata"]["namespace"] == "default"
        assert resource["spec"]["content"] == "# test content"
        # Default mode should be "edit"
        assert resource["spec"]["mode"] == "edit"
        # Default storage should be 1Gi
        assert resource["spec"]["storage"]["size"] == "1Gi"
        assert local_mounts == []

    def test_with_image(self):
        resource, _ = build_marimo_notebook(
            name="test",
            namespace="default",
            content="content",
            frontmatter={"image": "custom:latest"},
        )
        assert resource["spec"]["image"] == "custom:latest"

    def test_with_port(self):
        resource, _ = build_marimo_notebook(
            name="test",
            namespace="default",
            content="content",
            frontmatter={"port": "8080"},
        )
        assert resource["spec"]["port"] == 8080

    def test_with_storage(self):
        resource, _ = build_marimo_notebook(
            name="test",
            namespace="default",
            content="content",
            frontmatter={"storage": "5Gi"},
        )
        assert resource["spec"]["storage"]["size"] == "5Gi"

    def test_auth_none(self):
        resource, _ = build_marimo_notebook(
            name="test",
            namespace="default",
            content="content",
            frontmatter={"auth": "none"},
        )
        assert resource["spec"]["auth"] == {}

    def test_mode_edit(self):
        resource, _ = build_marimo_notebook(
            name="test",
            namespace="default",
            content="content",
            mode="edit",
        )
        assert resource["spec"]["mode"] == "edit"

    def test_mode_run(self):
        resource, _ = build_marimo_notebook(
            name="test",
            namespace="default",
            content="content",
            mode="run",
        )
        assert resource["spec"]["mode"] == "run"

    def test_source_adds_mount(self):
        resource, _ = build_marimo_notebook(
            name="test",
            namespace="default",
            content="content",
            source="cw://bucket/data",
        )
        assert resource["spec"]["mounts"] == ["cw://bucket/data"]

    def test_frontmatter_mounts(self):
        resource, _ = build_marimo_notebook(
            name="test",
            namespace="default",
            content="content",
            frontmatter={"mounts": ["cw://bucket1", "sshfs://user@host:/path"]},
        )
        assert resource["spec"]["mounts"] == ["cw://bucket1", "sshfs://user@host:/path"]

    def test_source_and_frontmatter_mounts_combined(self):
        resource, _ = build_marimo_notebook(
            name="test",
            namespace="default",
            content="content",
            frontmatter={"mounts": ["cw://bucket1"]},
            source="sshfs://user@host:/path",
        )
        # Source should come first, then frontmatter mounts
        assert resource["spec"]["mounts"] == ["sshfs://user@host:/path", "cw://bucket1"]

    def test_frontmatter_env(self):
        resource, _ = build_marimo_notebook(
            name="test",
            namespace="default",
            content="content",
            frontmatter={"env": {"DEBUG": "true", "LOG_LEVEL": "info"}},
        )
        env_vars = resource["spec"]["env"]
        assert len(env_vars) == 2
        # Check inline values
        debug_var = next(e for e in env_vars if e["name"] == "DEBUG")
        assert debug_var["value"] == "true"

    def test_content_none_for_directory(self):
        resource, _ = build_marimo_notebook(
            name="test",
            namespace="default",
            content=None,  # Directory mode
        )
        # Empty content for directory mode (satisfies operator validation)
        assert resource["spec"]["content"] == ""
        assert resource["spec"]["mode"] == "edit"
        assert resource["spec"]["storage"]["size"] == "1Gi"

    def test_local_mount_filtered(self):
        """Local mounts (rsync:///path) should be returned separately, not in CRD."""
        resource, local_mounts = build_marimo_notebook(
            name="test",
            namespace="default",
            content="content",
            source="rsync:///local/data:/mnt/data",
        )
        # Local mounts should NOT be in CRD
        assert "mounts" not in resource["spec"]
        # Local mount should be returned separately
        assert len(local_mounts) == 1
        src, dest, scheme = local_mounts[0]
        assert src == "/local/data"
        assert dest == "/mnt/data"
        assert scheme == "rsync"

    def test_mixed_local_and_remote_mounts(self):
        """Mix of local and remote mounts should be separated correctly."""
        resource, local_mounts = build_marimo_notebook(
            name="test",
            namespace="default",
            content="content",
            frontmatter={
                "mounts": [
                    "rsync:///local/path",  # Local (no host)
                    "rsync://user@host:/remote",  # Remote
                ]
            },
        )
        # Only remote mount should be in CRD
        assert resource["spec"]["mounts"] == ["rsync://user@host:/remote"]
        # Local mount should be separate
        assert len(local_mounts) == 1
        src, dest, scheme = local_mounts[0]
        assert src == "/local/path"
        assert dest == "/home/marimo/notebooks/mounts/local-0"  # Default
        assert scheme == "rsync"


class TestParseEnv:
    def test_inline_value(self):
        result = parse_env({"DEBUG": "true"})
        assert result == [{"name": "DEBUG", "value": "true"}]

    def test_secret_reference(self):
        result = parse_env({"API_KEY": {"secret": "my-secret", "key": "api-key"}})
        assert len(result) == 1
        assert result[0]["name"] == "API_KEY"
        assert result[0]["valueFrom"]["secretKeyRef"]["name"] == "my-secret"
        assert result[0]["valueFrom"]["secretKeyRef"]["key"] == "api-key"

    def test_secret_default_key(self):
        result = parse_env({"API_KEY": {"secret": "my-secret"}})
        # Default key should be lowercase of env var name
        assert result[0]["valueFrom"]["secretKeyRef"]["key"] == "api_key"

    def test_mixed_env(self):
        result = parse_env(
            {
                "DEBUG": "true",
                "API_KEY": {"secret": "my-secret", "key": "key"},
            }
        )
        assert len(result) == 2
        debug_var = next(e for e in result if e["name"] == "DEBUG")
        api_var = next(e for e in result if e["name"] == "API_KEY")
        assert debug_var["value"] == "true"
        assert "valueFrom" in api_var


class TestDetectContentType:
    def test_markdown_frontmatter(self):
        content = "---\ntitle: Test\n---\n# Heading"
        assert detect_content_type(content) == "markdown"

    def test_markdown_code_block(self):
        content = "# Title\n```python {.marimo}\nprint('hi')\n```"
        assert detect_content_type(content) == "markdown"

    def test_python_default(self):
        content = "import marimo\napp = marimo.App()"
        assert detect_content_type(content) == "python"

    def test_empty_is_python(self):
        assert detect_content_type("") == "python"


class TestParseMountUri:
    def test_local_absolute(self):
        """Triple slash = absolute local path."""
        scheme, source, user_host, mount = parse_mount_uri("rsync:///local/data")
        assert scheme == "rsync"
        assert source == "/local/data"
        assert user_host is None
        assert mount is None

    def test_local_absolute_with_mount(self):
        scheme, source, user_host, mount = parse_mount_uri(
            "rsync:///local/data:/mnt/data"
        )
        assert scheme == "rsync"
        assert source == "/local/data"
        assert user_host is None
        assert mount == "/mnt/data"

    def test_local_relative(self):
        """Double slash without @ = relative local path."""
        scheme, source, user_host, mount = parse_mount_uri("rsync://examples")
        assert scheme == "rsync"
        assert source == "examples"
        assert user_host is None
        assert mount is None

    def test_local_relative_with_mount(self):
        """rsync://examples:/data = relative 'examples' to '/data'."""
        scheme, source, user_host, mount = parse_mount_uri("rsync://examples:/data")
        assert scheme == "rsync"
        assert source == "examples"
        assert user_host is None
        assert mount == "/data"

    def test_local_relative_mount_point(self):
        """rsync://examples:data = relative mount → /home/marimo/notebooks/data."""
        scheme, source, user_host, mount = parse_mount_uri("rsync://examples:data")
        assert scheme == "rsync"
        assert source == "examples"
        assert user_host is None
        assert mount == "/home/marimo/notebooks/data"

    def test_local_relative_path_with_mount(self):
        """rsync://path/to/dir:/mnt = relative path with subdirs."""
        scheme, source, user_host, mount = parse_mount_uri("rsync://path/to/dir:/mnt")
        assert scheme == "rsync"
        assert source == "path/to/dir"
        assert user_host is None
        assert mount == "/mnt"

    def test_remote_simple(self):
        scheme, source, user_host, mount = parse_mount_uri(
            "rsync://user@host:/remote/path"
        )
        assert scheme == "rsync"
        assert source == "/remote/path"
        assert user_host == "user@host"
        assert mount is None

    def test_remote_with_mount(self):
        scheme, source, user_host, mount = parse_mount_uri(
            "rsync://user@host:/remote:/mnt/custom"
        )
        assert scheme == "rsync"
        assert source == "/remote"
        assert user_host == "user@host"
        assert mount == "/mnt/custom"

    def test_sshfs_scheme(self):
        scheme, source, user_host, mount = parse_mount_uri("sshfs://user@host:/data")
        assert scheme == "sshfs"
        assert source == "/data"
        assert user_host == "user@host"

    def test_invalid_uri(self):
        with pytest.raises(ValueError):
            parse_mount_uri("invalid")


class TestIsLocalMount:
    def test_local_absolute(self):
        assert is_local_mount("rsync:///local/path") is True
        assert is_local_mount("rsync:///local/path:/mnt") is True

    def test_local_relative(self):
        assert is_local_mount("rsync://examples") is True
        assert is_local_mount("rsync://examples:/data") is True
        assert is_local_mount("rsync://examples:data") is True  # Relative mount point
        assert is_local_mount("rsync://path/to/dir:/mnt") is True

    def test_remote_mount(self):
        assert is_local_mount("rsync://user@host:/path") is False
        assert is_local_mount("sshfs://user@host:/path") is False


class TestFilterMounts:
    def test_separates_local_and_remote(self):
        mounts = [
            "rsync:///local/path",
            "rsync://user@host:/remote",
            "sshfs://user@host:/data",
        ]
        remote, local = filter_mounts(mounts)
        assert remote == ["rsync://user@host:/remote", "sshfs://user@host:/data"]
        assert len(local) == 1
        assert local[0][0] == "/local/path"  # source
        assert local[0][2] == "rsync"  # scheme

    def test_local_default_mount_point(self):
        mounts = ["rsync:///path1", "rsync:///path2"]
        remote, local = filter_mounts(mounts)
        assert remote == []
        assert len(local) == 2
        # Check default mount points use index
        assert local[0][1] == "/home/marimo/notebooks/mounts/local-0"
        assert local[1][1] == "/home/marimo/notebooks/mounts/local-1"

    def test_local_custom_mount_point(self):
        mounts = ["rsync:///src:/dest"]
        remote, local = filter_mounts(mounts)
        assert local[0][0] == "/src"
        assert local[0][1] == "/dest"
