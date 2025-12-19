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
    filter_mounts,
    build_ssh_sidecar,
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
        resource, rsync_mounts, sshfs_mounts = build_marimo_notebook(
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
        assert rsync_mounts == []
        assert sshfs_mounts == []

    def test_with_image(self):
        resource, _, _ = build_marimo_notebook(
            name="test",
            namespace="default",
            content="content",
            frontmatter={"image": "custom:latest"},
        )
        assert resource["spec"]["image"] == "custom:latest"

    def test_with_port(self):
        resource, _, _ = build_marimo_notebook(
            name="test",
            namespace="default",
            content="content",
            frontmatter={"port": "8080"},
        )
        assert resource["spec"]["port"] == 8080

    def test_with_storage(self):
        resource, _, _ = build_marimo_notebook(
            name="test",
            namespace="default",
            content="content",
            frontmatter={"storage": "5Gi"},
        )
        assert resource["spec"]["storage"]["size"] == "5Gi"

    def test_auth_none(self):
        resource, _, _ = build_marimo_notebook(
            name="test",
            namespace="default",
            content="content",
            frontmatter={"auth": "none"},
        )
        assert resource["spec"]["auth"] == {}

    def test_mode_edit(self):
        resource, _, _ = build_marimo_notebook(
            name="test",
            namespace="default",
            content="content",
            mode="edit",
        )
        assert resource["spec"]["mode"] == "edit"

    def test_mode_run(self):
        resource, _, _ = build_marimo_notebook(
            name="test",
            namespace="default",
            content="content",
            mode="run",
        )
        assert resource["spec"]["mode"] == "run"

    def test_source_adds_cw_mount(self):
        resource, _, _ = build_marimo_notebook(
            name="test",
            namespace="default",
            content="content",
            source="cw://bucket/data",
        )
        assert resource["spec"]["mounts"] == ["cw://bucket/data"]

    def test_frontmatter_cw_mounts(self):
        resource, _, _ = build_marimo_notebook(
            name="test",
            namespace="default",
            content="content",
            frontmatter={"mounts": ["cw://bucket1", "cw://bucket2"]},
        )
        assert resource["spec"]["mounts"] == ["cw://bucket1", "cw://bucket2"]

    def test_frontmatter_env(self):
        resource, _, _ = build_marimo_notebook(
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
        resource, _, _ = build_marimo_notebook(
            name="test",
            namespace="default",
            content=None,  # Directory mode
        )
        # Empty content for directory mode (satisfies operator validation)
        assert resource["spec"]["content"] == ""
        assert resource["spec"]["mode"] == "edit"
        assert resource["spec"]["storage"]["size"] == "1Gi"

    def test_rsync_mount_filtered(self):
        """Rsync mounts should be returned separately, not in CRD."""
        resource, rsync_mounts, _ = build_marimo_notebook(
            name="test",
            namespace="default",
            content="content",
            source="rsync://./local/data:/mnt/data",
        )
        # Rsync mounts should NOT be in CRD
        assert "mounts" not in resource["spec"]
        # Local mount should be returned separately
        assert len(rsync_mounts) == 1
        src, dest, scheme = rsync_mounts[0]
        assert src == "./local/data"
        assert dest == "/mnt/data"
        assert scheme == "rsync"

    def test_sshfs_mount_adds_sidecar(self):
        """SSHFS mounts should add SSH sidecar and return local mount info."""
        resource, _, sshfs_mounts = build_marimo_notebook(
            name="test",
            namespace="default",
            content="content",
            source="sshfs:///home/marimo/notebooks",
        )
        # Should have sidecar added
        assert "sidecars" in resource["spec"]
        assert len(resource["spec"]["sidecars"]) == 1
        sidecar = resource["spec"]["sidecars"][0]
        assert sidecar["name"] == "sshfs-0"
        assert sidecar["exposePort"] == 2222
        # Should return sshfs mount info
        assert len(sshfs_mounts) == 1
        remote_path, local_mount = sshfs_mounts[0]
        assert remote_path == "/home/marimo/notebooks"

    def test_mixed_mount_schemes(self):
        """Mix of mount schemes should be handled correctly."""
        resource, rsync_mounts, sshfs_mounts = build_marimo_notebook(
            name="test",
            namespace="default",
            content="content",
            frontmatter={
                "mounts": [
                    "rsync://./local/path",  # Rsync - plugin handles
                    "sshfs:///data",  # SSHFS - plugin handles
                    "cw://bucket/path",  # CW - operator handles
                ]
            },
        )
        # Only CW mount should be in CRD mounts
        assert resource["spec"]["mounts"] == ["cw://bucket/path"]
        # Should have sshfs sidecar
        assert "sidecars" in resource["spec"]
        assert len(resource["spec"]["sidecars"]) == 1
        # Rsync should be separate
        assert len(rsync_mounts) == 1
        # SSHFS should be separate
        assert len(sshfs_mounts) == 1


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
    def test_sshfs_absolute(self):
        """sshfs:///path = local sshfs mount."""
        scheme, path = parse_mount_uri("sshfs:///home/marimo/notebooks")
        assert scheme == "sshfs"
        assert path == "/home/marimo/notebooks"

    def test_rsync_relative(self):
        """rsync://./path = relative local path."""
        scheme, path = parse_mount_uri("rsync://./local/data")
        assert scheme == "rsync"
        assert path == "./local/data"

    def test_rsync_with_mount(self):
        """rsync://./local/data:/mnt/data = rsync with mount point."""
        scheme, path = parse_mount_uri("rsync://./local/data:/mnt/data")
        assert scheme == "rsync"
        assert path == "./local/data:/mnt/data"

    def test_cw_bucket(self):
        """cw://bucket/path = CoreWeave S3."""
        scheme, path = parse_mount_uri("cw://mybucket/data")
        assert scheme == "cw"
        assert path == "mybucket/data"

    def test_invalid_uri(self):
        with pytest.raises(ValueError):
            parse_mount_uri("invalid")


class TestFilterMounts:
    def test_separates_schemes(self):
        """Mounts should be categorized by scheme."""
        mounts = [
            "rsync://./local/path",
            "sshfs:///data",
            "cw://bucket/path",
        ]
        cw_mounts, rsync_mounts, sshfs_mounts = filter_mounts(mounts)
        assert cw_mounts == ["cw://bucket/path"]
        assert len(rsync_mounts) == 1
        assert rsync_mounts[0][0] == "./local/path"  # source
        assert rsync_mounts[0][2] == "rsync"  # scheme
        assert len(sshfs_mounts) == 1
        assert sshfs_mounts[0][0] == "/data"  # remote path

    def test_rsync_default_mount_point(self):
        mounts = ["rsync://./path1", "rsync://./path2"]
        cw, rsync, sshfs = filter_mounts(mounts)
        assert cw == []
        assert len(rsync) == 2
        # Check default mount points use index
        assert rsync[0][1] == "/home/marimo/notebooks/mounts/local-0"
        assert rsync[1][1] == "/home/marimo/notebooks/mounts/local-1"

    def test_rsync_custom_mount_point(self):
        mounts = ["rsync://./src:/dest"]
        cw, rsync, sshfs = filter_mounts(mounts)
        assert rsync[0][0] == "./src"
        assert rsync[0][1] == "/dest"

    def test_sshfs_mount_info(self):
        mounts = ["sshfs:///home/marimo/notebooks"]
        cw, rsync, sshfs = filter_mounts(mounts)
        assert len(sshfs) == 1
        remote_path, local_mount = sshfs[0]
        assert remote_path == "/home/marimo/notebooks"
        assert local_mount.startswith("./marimo-mount-")

    def test_unknown_scheme_passes_through(self):
        """Unknown schemes should pass through to operator."""
        mounts = ["nfs://server/path"]
        cw, rsync, sshfs = filter_mounts(mounts)
        assert cw == ["nfs://server/path"]  # Unknown goes to operator
        assert rsync == []
        assert sshfs == []


class TestBuildSshSidecar:
    def test_basic(self):
        sidecar = build_ssh_sidecar(0)
        assert sidecar["name"] == "sshfs-0"
        assert sidecar["exposePort"] == 2222
        assert any(
            e["name"] == "PASSWORD_ACCESS" and e["value"] == "false"
            for e in sidecar["env"]
        )
        assert any(
            e["name"] == "USER_NAME" and e["value"] == "marimo" for e in sidecar["env"]
        )

    def test_index(self):
        sidecar = build_ssh_sidecar(3)
        assert sidecar["name"] == "sshfs-3"
