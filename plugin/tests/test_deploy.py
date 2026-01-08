"""Tests for deploy module."""

import socket

import pytest

from kubectl_marimo.deploy import (
    check_secret_exists,
    ensure_cw_credentials,
    find_available_port,
    get_access_token,
    parse_s3_credentials,
)


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


class TestCheckSecretExists:
    """Tests for check_secret_exists function."""

    def test_returns_true_when_exists(self, mocker):
        """Returns True when kubectl get secret succeeds."""
        mock_result = mocker.Mock()
        mock_result.returncode = 0
        mocker.patch("subprocess.run", return_value=mock_result)

        assert check_secret_exists("cw-credentials", "default") is True

    def test_returns_false_when_not_exists(self, mocker):
        """Returns False when kubectl get secret fails."""
        mock_result = mocker.Mock()
        mock_result.returncode = 1
        mocker.patch("subprocess.run", return_value=mock_result)

        assert check_secret_exists("cw-credentials", "default") is False

    def test_includes_namespace_flag(self, mocker):
        """Includes -n flag when namespace provided."""
        mock_result = mocker.Mock()
        mock_result.returncode = 0
        mock_run = mocker.patch("subprocess.run", return_value=mock_result)

        check_secret_exists("cw-credentials", "my-namespace")

        cmd = mock_run.call_args[0][0]
        assert "-n" in cmd
        assert "my-namespace" in cmd

    def test_no_namespace_flag_when_none(self, mocker):
        """Omits -n flag when namespace is None."""
        mock_result = mocker.Mock()
        mock_result.returncode = 0
        mock_run = mocker.patch("subprocess.run", return_value=mock_result)

        check_secret_exists("cw-credentials", None)

        cmd = mock_run.call_args[0][0]
        assert "-n" not in cmd


class TestParseS3Credentials:
    """Tests for parse_s3_credentials function."""

    def test_namespace_section_first(self, tmp_path):
        """Namespace section takes priority over marimo and default."""
        s3cfg = tmp_path / ".s3cfg"
        s3cfg.write_text("""
[default]
access_key = DEFAULT_KEY
secret_key = DEFAULT_SECRET

[marimo]
access_key = MARIMO_KEY
secret_key = MARIMO_SECRET

[team-alpha]
access_key = ALPHA_KEY
secret_key = ALPHA_SECRET
""")
        access, secret, section = parse_s3_credentials(str(s3cfg), "team-alpha")
        assert access == "ALPHA_KEY"
        assert secret == "ALPHA_SECRET"
        assert section == "team-alpha"

    def test_marimo_section_over_default(self, tmp_path):
        """[marimo] section takes priority over [default]."""
        s3cfg = tmp_path / ".s3cfg"
        s3cfg.write_text("""
[default]
access_key = DEFAULT_KEY
secret_key = DEFAULT_SECRET

[marimo]
access_key = MARIMO_KEY
secret_key = MARIMO_SECRET
""")
        access, secret, section = parse_s3_credentials(str(s3cfg))
        assert access == "MARIMO_KEY"
        assert secret == "MARIMO_SECRET"
        assert section == "marimo"

    def test_falls_back_to_default(self, tmp_path):
        """Falls back to [default] when [marimo] not present."""
        s3cfg = tmp_path / ".s3cfg"
        s3cfg.write_text("""
[default]
access_key = DEFAULT_KEY
secret_key = DEFAULT_SECRET
""")
        access, secret, section = parse_s3_credentials(str(s3cfg))
        assert access == "DEFAULT_KEY"
        assert secret == "DEFAULT_SECRET"
        assert section == "default"

    def test_returns_none_when_no_valid_section(self, tmp_path):
        """Returns (None, None, None) when no valid section found."""
        s3cfg = tmp_path / ".s3cfg"
        s3cfg.write_text("""
[other]
key = value
""")
        access, secret, section = parse_s3_credentials(str(s3cfg))
        assert access is None
        assert secret is None
        assert section is None

    def test_skips_incomplete_section(self, tmp_path):
        """Skips sections missing required keys."""
        s3cfg = tmp_path / ".s3cfg"
        s3cfg.write_text("""
[marimo]
access_key = MARIMO_KEY
# missing secret_key

[default]
access_key = DEFAULT_KEY
secret_key = DEFAULT_SECRET
""")
        access, secret, section = parse_s3_credentials(str(s3cfg))
        assert access == "DEFAULT_KEY"
        assert section == "default"


class TestEnsureCwCredentials:
    """Tests for ensure_cw_credentials function."""

    def test_returns_true_when_secret_exists(self, mocker):
        """Returns True immediately when secret already exists."""
        mocker.patch("kubectl_marimo.deploy.check_secret_exists", return_value=True)
        mocker.patch("kubectl_marimo.deploy.click.echo")

        result = ensure_cw_credentials("default")

        assert result is True

    def test_returns_false_when_no_s3cfg(self, mocker, tmp_path):
        """Returns False when secret missing and no ~/.s3cfg."""
        mocker.patch("kubectl_marimo.deploy.check_secret_exists", return_value=False)
        mocker.patch("os.path.expanduser", return_value=str(tmp_path / "nonexistent"))
        mock_echo = mocker.patch("kubectl_marimo.deploy.click.echo")

        result = ensure_cw_credentials("default")

        assert result is False
        # Should show helpful message
        echo_calls = str(mock_echo.call_args_list)
        assert "not found" in echo_calls or "does not exist" in echo_calls

    def test_creates_secret_in_non_tty(self, mocker, tmp_path):
        """Creates secret automatically in non-TTY (CI/CD) mode."""
        mocker.patch("kubectl_marimo.deploy.check_secret_exists", return_value=False)
        s3cfg = tmp_path / ".s3cfg"
        s3cfg.write_text("""
[default]
access_key = TEST_KEY
secret_key = TEST_SECRET
""")
        mocker.patch("os.path.expanduser", return_value=str(s3cfg))
        mocker.patch("os.path.exists", return_value=True)
        mocker.patch("sys.stdin.isatty", return_value=False)
        mocker.patch("kubectl_marimo.deploy.click.echo")

        mock_result = mocker.Mock()
        mock_result.returncode = 0
        mock_run = mocker.patch("subprocess.run", return_value=mock_result)

        result = ensure_cw_credentials("default")

        assert result is True
        # Should have called kubectl create secret
        create_calls = [c for c in mock_run.call_args_list if "create" in str(c)]
        assert len(create_calls) > 0

    def test_prompts_in_tty_mode(self, mocker, tmp_path):
        """Prompts for confirmation in interactive TTY mode."""
        mocker.patch("kubectl_marimo.deploy.check_secret_exists", return_value=False)
        s3cfg = tmp_path / ".s3cfg"
        s3cfg.write_text("""
[default]
access_key = TEST_KEY
secret_key = TEST_SECRET
""")
        mocker.patch("os.path.expanduser", return_value=str(s3cfg))
        mocker.patch("os.path.exists", return_value=True)
        mocker.patch("sys.stdin.isatty", return_value=True)
        mocker.patch("kubectl_marimo.deploy.click.echo")
        mock_confirm = mocker.patch(
            "kubectl_marimo.deploy.click.confirm", return_value=False
        )

        result = ensure_cw_credentials("default")

        assert result is False  # User declined
        mock_confirm.assert_called_once()

    def test_uses_namespace_for_section_lookup(self, mocker, tmp_path):
        """Uses namespace as section name when parsing credentials."""
        mocker.patch("kubectl_marimo.deploy.check_secret_exists", return_value=False)
        s3cfg = tmp_path / ".s3cfg"
        s3cfg.write_text("""
[default]
access_key = DEFAULT_KEY
secret_key = DEFAULT_SECRET

[team-alpha]
access_key = ALPHA_KEY
secret_key = ALPHA_SECRET
""")
        mocker.patch("os.path.expanduser", return_value=str(s3cfg))
        mocker.patch("os.path.exists", return_value=True)
        mocker.patch("sys.stdin.isatty", return_value=False)
        mock_echo = mocker.patch("kubectl_marimo.deploy.click.echo")

        mock_result = mocker.Mock()
        mock_result.returncode = 0
        mock_run = mocker.patch("subprocess.run", return_value=mock_result)

        ensure_cw_credentials("team-alpha")

        # Should use team-alpha credentials
        create_call = [c for c in mock_run.call_args_list if "create" in str(c)][0]
        cmd_str = str(create_call)
        assert "ALPHA_KEY" in cmd_str
