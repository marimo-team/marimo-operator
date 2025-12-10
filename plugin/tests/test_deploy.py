"""Tests for deploy module."""

import socket


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
