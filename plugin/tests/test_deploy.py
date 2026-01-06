"""Tests for deploy module."""

import socket

import pytest

from kubectl_marimo.deploy import find_available_port, get_access_token


class TestFindAvailablePort:
    """Tests for find_available_port function."""

    def test_preferred_port_available(self):
        """Returns preferred port if available."""
        # Use a high port that's likely available
        port = find_available_port(54321)
        assert port == 54321

    def test_fallback_when_port_in_use(self):
        """Returns different port if preferred is in use."""
        # Bind to a port first
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("localhost", 54322))
            s.listen(1)
            # Now try to get that port - should get a different one
            port = find_available_port(54322)
            assert port != 54322
            assert port > 0

    def test_returns_valid_port_range(self):
        """Returned port is in valid range."""
        port = find_available_port(2718)
        assert 1 <= port <= 65535


class TestGetAccessToken:
    """Tests for get_access_token function."""

    def test_extracts_token_from_logs(self, mocker):
        """Extracts access token from marimo log output."""
        mock_result = mocker.Mock()
        mock_result.stdout = """
        Create or edit notebooks in your browser
        URL: http://0.0.0.0:2718?access_token=ABC123XYZ
        Network: http://10.0.0.1:2718?access_token=ABC123XYZ
        """
        mock_result.returncode = 0

        mocker.patch("subprocess.run", return_value=mock_result)

        token = get_access_token("test", "default")
        assert token == "ABC123XYZ"

    def test_returns_none_when_no_token(self, mocker):
        """Returns None when no access token in logs."""
        mock_result = mocker.Mock()
        mock_result.stdout = "Some other log output without token"
        mock_result.returncode = 0

        mocker.patch("subprocess.run", return_value=mock_result)

        token = get_access_token("test", "default")
        assert token is None

    def test_returns_none_on_empty_output(self, mocker):
        """Returns None when logs are empty."""
        mock_result = mocker.Mock()
        mock_result.stdout = ""
        mock_result.returncode = 0

        mocker.patch("subprocess.run", return_value=mock_result)

        token = get_access_token("test", "default")
        assert token is None


class TestReconnectionAlert:
    """Tests for reconnection alert when pod already exists."""

    @pytest.fixture
    def notebook_file(self, tmp_path):
        """Create a temporary notebook file."""
        nb = tmp_path / "test_notebook.py"
        nb.write_text(
            "import marimo\napp = marimo.App()\n@app.cell\ndef _():\n    pass"
        )
        return nb

    @pytest.fixture
    def mock_deploy_deps(self, mocker):
        """Mock all deploy dependencies."""
        mocks = {
            "apply_resource": mocker.patch(
                "kubectl_marimo.deploy.apply_resource", return_value=True
            ),
            "resource_exists": mocker.patch(
                "kubectl_marimo.deploy.resource_exists", return_value=False
            ),
            "wait_for_ready": mocker.patch(
                "kubectl_marimo.deploy.wait_for_ready", return_value=True
            ),
            "write_swap_file": mocker.patch("kubectl_marimo.deploy.write_swap_file"),
            "read_swap_file": mocker.patch(
                "kubectl_marimo.deploy.read_swap_file", return_value=None
            ),
            "echo": mocker.patch("kubectl_marimo.deploy.click.echo"),
            "style": mocker.patch(
                "kubectl_marimo.deploy.click.style", side_effect=lambda x, **kw: x
            ),
        }
        return mocks

    def test_shows_reconnection_alert_when_pod_exists(
        self, notebook_file, mock_deploy_deps, mocker
    ):
        """Shows yellow reconnection message when pod already exists."""
        from kubectl_marimo.deploy import deploy_notebook

        mock_deploy_deps["resource_exists"].return_value = True

        deploy_notebook(str(notebook_file), namespace="default", headless=True)

        # Should show reconnection message
        mock_deploy_deps["style"].assert_any_call(mocker.ANY, fg="yellow")
        # Check the styled message contains "Reconnecting"
        style_calls = mock_deploy_deps["style"].call_args_list
        reconnect_calls = [c for c in style_calls if "Reconnecting" in str(c)]
        assert len(reconnect_calls) > 0

        # Should NOT call apply_resource when reconnecting
        mock_deploy_deps["apply_resource"].assert_not_called()

    def test_creates_new_pod_when_not_exists(self, notebook_file, mock_deploy_deps):
        """Creates new pod when resource doesn't exist."""
        from kubectl_marimo.deploy import deploy_notebook

        mock_deploy_deps["resource_exists"].return_value = False

        deploy_notebook(str(notebook_file), namespace="default", headless=True)

        # Should call apply_resource for new pod
        mock_deploy_deps["apply_resource"].assert_called_once()


class TestTeardownPrompt:
    """Tests for teardown prompt on Ctrl-C."""

    @pytest.fixture
    def mock_open_notebook_deps(self, mocker):
        """Mock dependencies for open_notebook."""
        mocks = {
            "wait_for_ready": mocker.patch(
                "kubectl_marimo.deploy.wait_for_ready", return_value=True
            ),
            "get_access_token": mocker.patch(
                "kubectl_marimo.deploy.get_access_token", return_value="token123"
            ),
            "find_available_port": mocker.patch(
                "kubectl_marimo.deploy.find_available_port", return_value=2718
            ),
            "webbrowser_open": mocker.patch("kubectl_marimo.deploy.webbrowser.open"),
            "subprocess_run": mocker.patch(
                "kubectl_marimo.deploy.subprocess.run",
                side_effect=KeyboardInterrupt(),
            ),
            "sync_notebook": mocker.patch("kubectl_marimo.deploy.sync_notebook"),
            "delete_resource": mocker.patch(
                "kubectl_marimo.deploy.delete_resource", return_value=True
            ),
            "delete_swap_file": mocker.patch(
                "kubectl_marimo.deploy.delete_swap_file", return_value=True
            ),
            "confirm": mocker.patch("kubectl_marimo.deploy.click.confirm"),
            "echo": mocker.patch("kubectl_marimo.deploy.click.echo"),
        }
        return mocks

    def test_teardown_on_no_response(self, mock_open_notebook_deps, tmp_path):
        """Tears down pod when user responds No (default)."""
        from kubectl_marimo.deploy import open_notebook

        mock_open_notebook_deps["confirm"].return_value = False
        notebook_file = tmp_path / "test.py"
        notebook_file.write_text("# test")

        open_notebook("test-notebook", "default", 2718, str(notebook_file))

        # Should sync changes
        mock_open_notebook_deps["sync_notebook"].assert_called_once()

        # Should prompt user
        mock_open_notebook_deps["confirm"].assert_called_once_with(
            "Keep pod running?", default=False
        )

        # Should delete resource and swap file
        mock_open_notebook_deps["delete_resource"].assert_called_once_with(
            "marimos.marimo.io", "test-notebook", "default"
        )
        mock_open_notebook_deps["delete_swap_file"].assert_called_once()

    def test_keeps_pod_on_yes_response(self, mock_open_notebook_deps, tmp_path):
        """Keeps pod running when user responds Yes."""
        from kubectl_marimo.deploy import open_notebook

        mock_open_notebook_deps["confirm"].return_value = True
        notebook_file = tmp_path / "test.py"
        notebook_file.write_text("# test")

        open_notebook("test-notebook", "default", 2718, str(notebook_file))

        # Should sync changes
        mock_open_notebook_deps["sync_notebook"].assert_called_once()

        # Should prompt user
        mock_open_notebook_deps["confirm"].assert_called_once()

        # Should NOT delete resource or swap file
        mock_open_notebook_deps["delete_resource"].assert_not_called()
        mock_open_notebook_deps["delete_swap_file"].assert_not_called()

        # Should show message about keeping pod running
        echo_calls = [str(c) for c in mock_open_notebook_deps["echo"].call_args_list]
        keep_running_msgs = [c for c in echo_calls if "left running" in c]
        assert len(keep_running_msgs) > 0

    def test_handles_teardown_failure_gracefully(
        self, mock_open_notebook_deps, tmp_path
    ):
        """Continues gracefully if teardown fails."""
        from kubectl_marimo.deploy import open_notebook

        mock_open_notebook_deps["confirm"].return_value = False
        mock_open_notebook_deps["delete_resource"].side_effect = Exception("k8s error")
        notebook_file = tmp_path / "test.py"
        notebook_file.write_text("# test")

        # Should not raise exception
        open_notebook("test-notebook", "default", 2718, str(notebook_file))

        # Should show warning
        echo_calls = [str(c) for c in mock_open_notebook_deps["echo"].call_args_list]
        warning_msgs = [c for c in echo_calls if "Warning" in c]
        assert len(warning_msgs) > 0

    def test_handles_sync_failure_gracefully(self, mock_open_notebook_deps, tmp_path):
        """Continues to teardown prompt even if sync fails."""
        from kubectl_marimo.deploy import open_notebook

        mock_open_notebook_deps["sync_notebook"].side_effect = Exception("sync error")
        mock_open_notebook_deps["confirm"].return_value = False
        notebook_file = tmp_path / "test.py"
        notebook_file.write_text("# test")

        # Should not raise exception
        open_notebook("test-notebook", "default", 2718, str(notebook_file))

        # Should still prompt for teardown
        mock_open_notebook_deps["confirm"].assert_called_once()

        # Should still attempt teardown
        mock_open_notebook_deps["delete_resource"].assert_called_once()
