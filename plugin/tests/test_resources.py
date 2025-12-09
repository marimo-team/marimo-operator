"""Tests for resources module."""

import pytest

from kubectl_marimo.resources import (
    compute_hash,
    slugify,
    resource_name,
    build_marimo_notebook,
    detect_content_type,
    parse_env,
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
        resource = build_marimo_notebook(
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

    def test_with_image(self):
        resource = build_marimo_notebook(
            name="test",
            namespace="default",
            content="content",
            frontmatter={"image": "custom:latest"},
        )
        assert resource["spec"]["image"] == "custom:latest"

    def test_with_port(self):
        resource = build_marimo_notebook(
            name="test",
            namespace="default",
            content="content",
            frontmatter={"port": "8080"},
        )
        assert resource["spec"]["port"] == 8080

    def test_with_storage(self):
        resource = build_marimo_notebook(
            name="test",
            namespace="default",
            content="content",
            frontmatter={"storage": "5Gi"},
        )
        assert resource["spec"]["storage"]["size"] == "5Gi"

    def test_auth_none(self):
        resource = build_marimo_notebook(
            name="test",
            namespace="default",
            content="content",
            frontmatter={"auth": "none"},
        )
        assert resource["spec"]["auth"] == {}

    def test_mode_edit(self):
        resource = build_marimo_notebook(
            name="test",
            namespace="default",
            content="content",
            mode="edit",
        )
        assert resource["spec"]["mode"] == "edit"

    def test_mode_run(self):
        resource = build_marimo_notebook(
            name="test",
            namespace="default",
            content="content",
            mode="run",
        )
        assert resource["spec"]["mode"] == "run"

    def test_source_adds_mount(self):
        resource = build_marimo_notebook(
            name="test",
            namespace="default",
            content="content",
            source="cw://bucket/data",
        )
        assert resource["spec"]["mounts"] == ["cw://bucket/data"]

    def test_frontmatter_mounts(self):
        resource = build_marimo_notebook(
            name="test",
            namespace="default",
            content="content",
            frontmatter={"mounts": ["cw://bucket1", "sshfs://host/path"]},
        )
        assert resource["spec"]["mounts"] == ["cw://bucket1", "sshfs://host/path"]

    def test_source_and_frontmatter_mounts_combined(self):
        resource = build_marimo_notebook(
            name="test",
            namespace="default",
            content="content",
            frontmatter={"mounts": ["cw://bucket1"]},
            source="sshfs://host/path",
        )
        # Source should come first, then frontmatter mounts
        assert resource["spec"]["mounts"] == ["sshfs://host/path", "cw://bucket1"]

    def test_frontmatter_env(self):
        resource = build_marimo_notebook(
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
        resource = build_marimo_notebook(
            name="test",
            namespace="default",
            content=None,  # Directory mode
        )
        assert "content" not in resource["spec"]
        assert resource["spec"]["mode"] == "edit"
        assert resource["spec"]["storage"]["size"] == "1Gi"


class TestParseEnv:
    def test_inline_value(self):
        result = parse_env({"DEBUG": "true"})
        assert result == [{"name": "DEBUG", "value": "true"}]

    def test_secret_reference(self):
        result = parse_env({
            "API_KEY": {"secret": "my-secret", "key": "api-key"}
        })
        assert len(result) == 1
        assert result[0]["name"] == "API_KEY"
        assert result[0]["valueFrom"]["secretKeyRef"]["name"] == "my-secret"
        assert result[0]["valueFrom"]["secretKeyRef"]["key"] == "api-key"

    def test_secret_default_key(self):
        result = parse_env({
            "API_KEY": {"secret": "my-secret"}
        })
        # Default key should be lowercase of env var name
        assert result[0]["valueFrom"]["secretKeyRef"]["key"] == "api_key"

    def test_mixed_env(self):
        result = parse_env({
            "DEBUG": "true",
            "API_KEY": {"secret": "my-secret", "key": "key"},
        })
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
