"""Tests for delete module."""

import pytest

from kubectl_marimo.delete import delete_notebook


class TestDeleteNotebook:
    """Tests for delete_notebook function."""

    @pytest.fixture
    def notebook_file(self, tmp_path):
        """Create a temporary notebook file."""
        nb = tmp_path / "test_notebook.py"
        nb.write_text(
            "import marimo\napp = marimo.App()\n@app.cell\ndef _():\n    pass"
        )
        return nb

    @pytest.fixture
    def mock_k8s(self, mocker):
        """Mock kubernetes operations."""
        mocks = {
            "delete_resource": mocker.patch(
                "kubectl_marimo.delete.delete_resource", return_value=True
            ),
            "patch_resource": mocker.patch(
                "kubectl_marimo.delete.patch_resource", return_value=True
            ),
            "exec_in_pod": mocker.patch(
                "kubectl_marimo.delete.exec_in_pod",
                return_value=(False, "pod not found"),
            ),
        }
        return mocks

    @pytest.fixture
    def mock_swap(self, mocker):
        """Mock swap file operations."""
        mocker.patch("kubectl_marimo.delete.read_swap_file", return_value=None)
        mocker.patch("kubectl_marimo.delete.delete_swap_file")

    def test_preserves_pvc_by_default(self, notebook_file, mock_k8s, mock_swap):
        """By default, patches PVC to remove owner reference before delete."""
        delete_notebook(str(notebook_file), namespace="default", no_sync=True)

        # Should patch PVC to remove owner references
        mock_k8s["patch_resource"].assert_called_once()
        call_args = mock_k8s["patch_resource"].call_args
        assert call_args[0][0] == "pvc"  # kind
        assert "test-notebook-pvc" in call_args[0][1]  # name
        assert call_args[0][2] == "default"  # namespace
        assert "ownerReferences" in call_args[0][3]  # patch contains ownerReferences

        # Should still delete the MarimoNotebook
        mock_k8s["delete_resource"].assert_called_once()

    def test_delete_pvc_flag_skips_patch(self, notebook_file, mock_k8s, mock_swap):
        """With --delete-pvc, skips patching so PVC is garbage collected."""
        delete_notebook(
            str(notebook_file), namespace="default", delete_pvc=True, no_sync=True
        )

        # Should NOT patch PVC
        mock_k8s["patch_resource"].assert_not_called()

        # Should still delete the MarimoNotebook
        mock_k8s["delete_resource"].assert_called_once()

    def test_continues_if_patch_fails(self, notebook_file, mock_k8s, mock_swap, mocker):
        """Continues with delete even if PVC patch fails."""
        mock_k8s["patch_resource"].return_value = False
        mock_echo = mocker.patch("kubectl_marimo.delete.click.echo")

        delete_notebook(str(notebook_file), namespace="default", no_sync=True)

        # Should warn about patch failure
        warning_calls = [c for c in mock_echo.call_args_list if "Warning" in str(c)]
        assert len(warning_calls) > 0

        # Should still attempt delete
        mock_k8s["delete_resource"].assert_called_once()


class TestResourceExists:
    """Tests for resource_exists function."""

    def test_resource_exists_returns_true(self, mocker):
        """Returns True when resource exists."""
        from kubectl_marimo.k8s import resource_exists

        mock_run = mocker.patch("kubectl_marimo.k8s.subprocess.run")
        mock_run.return_value.returncode = 0

        result = resource_exists("marimos.marimo.io", "test-notebook", "default")

        assert result is True
        args = mock_run.call_args[0][0]
        assert "kubectl" in args
        assert "get" in args
        assert "marimos.marimo.io" in args
        assert "test-notebook" in args
        assert "-n" in args
        assert "default" in args

    def test_resource_exists_returns_false_not_found(self, mocker):
        """Returns False when resource doesn't exist."""
        from kubectl_marimo.k8s import resource_exists

        mock_run = mocker.patch("kubectl_marimo.k8s.subprocess.run")
        mock_run.return_value.returncode = 1

        result = resource_exists("marimos.marimo.io", "nonexistent", "default")

        assert result is False

    def test_resource_exists_no_namespace(self, mocker):
        """Works without namespace argument."""
        from kubectl_marimo.k8s import resource_exists

        mock_run = mocker.patch("kubectl_marimo.k8s.subprocess.run")
        mock_run.return_value.returncode = 0

        result = resource_exists("marimos.marimo.io", "test-notebook")

        assert result is True
        args = mock_run.call_args[0][0]
        assert "-n" not in args

    def test_resource_exists_kubectl_not_found(self, mocker):
        """Returns False when kubectl not in PATH."""
        from kubectl_marimo.k8s import resource_exists

        mocker.patch(
            "kubectl_marimo.k8s.subprocess.run", side_effect=FileNotFoundError()
        )

        result = resource_exists("marimos.marimo.io", "test-notebook", "default")

        assert result is False


class TestPatchResource:
    """Tests for patch_resource function."""

    def test_patch_resource_success(self, mocker):
        """Successfully patches a resource."""
        from kubectl_marimo.k8s import patch_resource

        mock_run = mocker.patch("kubectl_marimo.k8s.subprocess.run")
        mock_run.return_value.returncode = 0

        result = patch_resource(
            "pvc", "test-pvc", "default", '{"metadata":{"ownerReferences":null}}'
        )

        assert result is True
        args = mock_run.call_args[0][0]
        assert "kubectl" in args
        assert "patch" in args
        assert "pvc" in args
        assert "test-pvc" in args
        assert "-n" in args
        assert "default" in args
        assert "--type=merge" in args

    def test_patch_resource_failure(self, mocker):
        """Returns False on patch failure."""
        from kubectl_marimo.k8s import patch_resource

        mock_run = mocker.patch("kubectl_marimo.k8s.subprocess.run")
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "resource not found"

        result = patch_resource("pvc", "test-pvc", "default", "{}")

        assert result is False

    def test_patch_resource_kubectl_not_found(self, mocker):
        """Returns False when kubectl not in PATH."""
        from kubectl_marimo.k8s import patch_resource

        mocker.patch(
            "kubectl_marimo.k8s.subprocess.run", side_effect=FileNotFoundError()
        )

        result = patch_resource("pvc", "test-pvc", "default", "{}")

        assert result is False
