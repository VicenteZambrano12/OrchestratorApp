import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import migrate_images


class MigrateImagesTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.source = Path(self.directory.name)
        self.patch_source = patch.object(migrate_images, "SOURCE_DIRECTORY", self.source)
        self.patch_source.start()
        self.addCleanup(self.patch_source.stop)
        self.gcloud = patch.object(migrate_images.shutil, "which", return_value="/usr/bin/gcloud")
        self.gcloud.start()
        self.addCleanup(self.gcloud.stop)
        self.run_patch = patch.object(migrate_images.subprocess, "run")
        self.run = self.run_patch.start()
        self.addCleanup(self.run_patch.stop)
        self.run.return_value.returncode = 0
        self.stdout = contextlib.redirect_stdout(io.StringIO())
        self.stdout.__enter__()
        self.addCleanup(self.stdout.__exit__, None, None, None)
        self.stderr = contextlib.redirect_stderr(io.StringIO())
        self.stderr.__enter__()
        self.addCleanup(self.stderr.__exit__, None, None, None)

    def test_upload_command_preserves_tree_without_deleting_destination_objects(self):
        self.assertEqual(migrate_images.main([]), 0)
        self.run.assert_called_once_with(
            [
                "/usr/bin/gcloud", "storage", "rsync", str(self.source),
                "gs://orch_app_bucket/images/", "--recursive", "--checksums-only",
                r"--exclude=(^|/)\.gitkeep$",
            ],
            check=False,
        )

    def test_dry_run_is_forwarded(self):
        self.assertEqual(migrate_images.main(["--dry-run"]), 0)
        self.assertEqual(self.run.call_args.args[0][-1], "--dry-run")

    def test_missing_source_fails_before_running_gcloud(self):
        with patch.object(migrate_images, "SOURCE_DIRECTORY", self.source / "missing"):
            with self.assertRaises(SystemExit) as error:
                migrate_images.main([])
        self.assertEqual(error.exception.code, 2)
        self.run.assert_not_called()

    def test_missing_gcloud_fails_explicitly(self):
        with patch.object(migrate_images.shutil, "which", return_value=None):
            with self.assertRaises(SystemExit) as error:
                migrate_images.main([])
        self.assertEqual(error.exception.code, 2)
        self.run.assert_not_called()

    def test_transfer_error_is_propagated(self):
        self.run.return_value.returncode = 7
        self.assertEqual(migrate_images.main([]), 7)

    def test_launch_error_fails(self):
        self.run.side_effect = OSError("Cannot execute gcloud")
        self.assertEqual(migrate_images.main([]), 1)


if __name__ == "__main__":
    unittest.main()
