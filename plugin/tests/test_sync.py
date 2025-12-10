"""Tests for sync module."""

from kubectl_marimo.sync import sync_local_mounts


class TestSyncLocalMounts:
    def test_syncs_single_mount(self, mocker):
        """Syncs files from pod to local directory."""
        mock_run = mocker.patch("kubectl_marimo.sync.subprocess.run")
        mock_run.return_value.returncode = 0

        sync_local_mounts(
            name="test-pod",
            namespace="default",
            local_mounts=[{"local": "/tmp/data", "remote": "/mnt/data"}],
        )

        # Verify kubectl cp was called correctly
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "kubectl" in args
        assert "cp" in args
        assert "default/test-pod:/mnt/data/." in args
        assert "/tmp/data" in args
        assert "-c" in args
        assert "marimo" in args

    def test_syncs_multiple_mounts(self, mocker):
        """Syncs multiple mount points."""
        mock_run = mocker.patch("kubectl_marimo.sync.subprocess.run")
        mock_run.return_value.returncode = 0

        sync_local_mounts(
            name="pod",
            namespace="ns",
            local_mounts=[
                {"local": "/data1", "remote": "/mnt1"},
                {"local": "/data2", "remote": "/mnt2"},
            ],
        )

        assert mock_run.call_count == 2

    def test_handles_sync_failure(self, mocker):
        """Warns but continues on sync failure."""
        mock_run = mocker.patch("kubectl_marimo.sync.subprocess.run")
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "error"

        mock_echo = mocker.patch("kubectl_marimo.sync.click.echo")

        sync_local_mounts(
            name="pod",
            namespace="ns",
            local_mounts=[{"local": "/data", "remote": "/mnt"}],
        )

        # Should have printed a warning
        calls = [str(c) for c in mock_echo.call_args_list]
        assert any("Warning" in str(c) for c in calls)

    def test_empty_mounts_no_op(self, mocker):
        """Does nothing with empty mount list."""
        mock_run = mocker.patch("kubectl_marimo.sync.subprocess.run")
        sync_local_mounts("pod", "ns", [])
        mock_run.assert_not_called()

    def test_cleans_marimo_files_after_sync(self, mocker, tmp_path):
        """Removes .marimo swap files after sync to prevent false positives."""
        local_dir = tmp_path / "data"
        local_dir.mkdir()

        # Create fake .marimo files that would have been synced back
        marimo_file1 = local_dir / ".test.py.marimo"
        marimo_file1.write_text("{}")
        marimo_file2 = local_dir / "subdir"
        marimo_file2.mkdir()
        marimo_file3 = marimo_file2 / ".nested.py.marimo"
        marimo_file3.write_text("{}")

        mock_run = mocker.patch("kubectl_marimo.sync.subprocess.run")
        mock_run.return_value.returncode = 0

        sync_local_mounts("pod", "ns", [{"local": str(local_dir), "remote": "/mnt"}])

        # .marimo files should be deleted (both top-level and nested)
        assert not marimo_file1.exists()
        assert not marimo_file3.exists()
        # But the directory structure should remain
        assert marimo_file2.exists()
