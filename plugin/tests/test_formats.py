"""Tests for format parsers."""

import pytest

from kubectl_marimo.formats.markdown import (
    parse_markdown,
    extract_frontmatter,
    is_marimo_markdown,
)
from kubectl_marimo.formats.python import (
    parse_python,
    extract_pep723_metadata,
    is_marimo_python,
)


class TestMarkdownParser:
    def test_parse_with_frontmatter(self):
        content = """---
title: My Notebook
image: custom:latest
---
# Content here"""
        result_content, frontmatter = parse_markdown(content)
        assert result_content == content
        assert frontmatter["title"] == "My Notebook"
        assert frontmatter["image"] == "custom:latest"

    def test_parse_no_frontmatter(self):
        content = "# Just markdown\nNo frontmatter"
        result_content, frontmatter = parse_markdown(content)
        assert result_content == content
        assert frontmatter is None


class TestExtractFrontmatter:
    def test_basic(self):
        content = """---
title: Test
port: 8080
---
body"""
        fm = extract_frontmatter(content)
        assert fm["title"] == "Test"
        assert fm["port"] == "8080"

    def test_quoted_values(self):
        content = """---
title: "Quoted Title"
image: 'single quoted'
---
body"""
        fm = extract_frontmatter(content)
        assert fm["title"] == "Quoted Title"
        assert fm["image"] == "single quoted"

    def test_no_closing(self):
        content = """---
title: Test
body without closing"""
        fm = extract_frontmatter(content)
        assert fm is None

    def test_no_frontmatter(self):
        content = "Just content"
        fm = extract_frontmatter(content)
        assert fm is None


class TestIsMarimoMarkdown:
    def test_has_frontmatter(self):
        assert is_marimo_markdown("---\ntitle: Test\n---\nbody")

    def test_has_marimo_block(self):
        content = "# Title\n```python {.marimo}\ncode\n```"
        assert is_marimo_markdown(content)

    def test_alternative_block_syntax(self):
        content = "# Title\n```{python marimo}\ncode\n```"
        assert is_marimo_markdown(content)

    def test_plain_markdown(self):
        content = "# Title\nJust text"
        assert not is_marimo_markdown(content)


class TestPythonParser:
    def test_parse_with_pep723(self):
        content = '''# /// script
# dependencies = ["marimo", "pandas"]
# ///
import marimo
app = marimo.App()'''
        result_content, metadata = parse_python(content)
        assert result_content == content
        assert metadata["dependencies"] == '["marimo", "pandas"]'

    def test_parse_no_metadata(self):
        content = "import marimo\napp = marimo.App()"
        result_content, metadata = parse_python(content)
        assert result_content == content
        assert metadata is None


class TestExtractPep723Metadata:
    def test_basic(self):
        content = '''# /// script
# dependencies = ["marimo"]
# requires-python = ">=3.10"
# ///
code'''
        meta = extract_pep723_metadata(content)
        assert meta["dependencies"] == '["marimo"]'
        assert meta["requires-python"] == ">=3.10"

    def test_k8s_config(self):
        content = '''# /// script
# dependencies = ["marimo"]
# ///
# [tool.marimo.k8s]
# image = "custom:latest"
# storage = "5Gi"
import marimo'''
        meta = extract_pep723_metadata(content)
        assert meta["image"] == "custom:latest"
        assert meta["storage"] == "5Gi"

    def test_no_metadata(self):
        content = "import marimo\napp = marimo.App()"
        meta = extract_pep723_metadata(content)
        assert meta is None


class TestIsMaimoPython:
    def test_import_marimo(self):
        assert is_marimo_python("import marimo\napp = marimo.App()")

    def test_from_import(self):
        assert is_marimo_python("from marimo import App")

    def test_app_cell(self):
        assert is_marimo_python("@app.cell\ndef cell():\n    pass")

    def test_marimo_app(self):
        assert is_marimo_python("app = marimo.App()")

    def test_not_marimo(self):
        assert not is_marimo_python("import pandas\ndf = pandas.DataFrame()")
