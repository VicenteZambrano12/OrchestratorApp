from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import registry_images as registry


BASE = "europe-southwest1-docker.pkg.dev/basicrahgapp/orchestratorapp-repo/orchestratorapp"
SHA = "a" * 40


def record(number, tags=(), package=BASE):
    return {
        "package": package,
        "version": f"sha256:{number:064x}",
        "createTime": f"2026-10-{number:02d}T12:00:00.123456789Z",
        "tags": list(tags),
    }


def result(records):
    return subprocess.CompletedProcess([], 0, stdout=json.dumps(records), stderr="")


class RegistryImagesTests(unittest.TestCase):
    def test_first_image_is_built_even_without_source_changes(self):
        with patch.object(registry.subprocess, "run", return_value=result([])):
            self.assertEqual(
                registry.select_image(BASE, SHA, False),
                {"build": "true", "image": f"{BASE}:{SHA}"},
            )

    def test_source_changes_build_a_new_commit_image(self):
        with patch.object(registry.subprocess, "run", return_value=result([record(1)])):
            self.assertEqual(registry.select_image(BASE, SHA, True)["build"], "true")

    def test_rerun_reuses_the_existing_commit_digest(self):
        existing = record(2, [SHA])
        with patch.object(registry.subprocess, "run", return_value=result([existing, record(1)])):
            self.assertEqual(
                registry.select_image(BASE, SHA, True),
                {"build": "false", "image": f"{BASE}@{existing['version']}"},
            )

    def test_infrastructure_only_change_reuses_newest_created_not_newest_retagged(self):
        old = record(1)
        old["updateTime"] = "2026-12-31T23:59:59Z"
        newest = record(3)
        with patch.object(registry.subprocess, "run", return_value=result([old, newest, record(2)])):
            self.assertEqual(
                registry.select_image(BASE, SHA, False),
                {"build": "false", "image": f"{BASE}@{newest['version']}"},
            )

    def test_pruning_keeps_exactly_two_and_never_touches_another_package(self):
        records = [record(2), record(1), record(5), record(3), record(4)]
        unrelated = record(9, package=BASE + "-other")
        responses = iter((result(records + [unrelated]), result([record(4), record(5), unrelated])))
        deleted = []

        def run(command, **kwargs):
            if "delete" in command:
                deleted.append(command)
                return result([])
            return next(responses)

        with patch.object(registry.subprocess, "run", side_effect=run), redirect_stdout(io.StringIO()):
            registry.prune_images(BASE, record(5)["version"])
        self.assertEqual(
            [command[5] for command in deleted],
            [f"{BASE}@{record(number)['version']}" for number in (3, 2, 1)],
        )
        self.assertTrue(all("--delete-tags" in command and "--quiet" in command for command in deleted))
        self.assertNotIn("-other", json.dumps(deleted))

    def test_one_or_two_existing_images_require_no_deletion(self):
        for records in ([record(1)], [record(2), record(1)]):
            with self.subTest(count=len(records)):
                with patch.object(registry.subprocess, "run", return_value=result(records)) as run:
                    with redirect_stdout(io.StringIO()):
                        registry.prune_images(BASE, records[0]["version"])
                self.assertTrue(all("delete" not in call.args[0] for call in run.call_args_list))

    def test_missing_or_old_selected_image_prevents_all_deletions(self):
        for keep in (record(1)["version"], record(9)["version"]):
            with patch.object(registry.subprocess, "run", return_value=result([record(3), record(2), record(1)])) as run:
                with self.assertRaisesRegex(ValueError, "refusing deletion"):
                    registry.prune_images(BASE, keep)
                self.assertEqual(run.call_count, 1)

    def test_retention_threshold_is_verified_after_deletions(self):
        records = [record(3), record(2), record(1)]
        with patch.object(registry.subprocess, "run", side_effect=[result(records), result([]), result(records)]):
            with self.assertRaisesRegex(RuntimeError, "retention limit"):
                registry.prune_images(BASE, record(3)["version"])

    def test_concurrent_native_cleanup_is_accepted_only_after_confirming_absence(self):
        records = [record(3), record(2), record(1)]
        remaining = records[:2]
        error = subprocess.CalledProcessError(1, ["gcloud"], stderr="not found")
        with patch.object(registry.subprocess, "run", side_effect=[
            result(records), error, result(remaining), result(remaining),
        ]):
            with redirect_stdout(io.StringIO()):
                registry.prune_images(BASE, record(3)["version"])

    def test_failed_deletion_propagates_when_image_is_still_present(self):
        records = [record(3), record(2), record(1)]
        error = subprocess.CalledProcessError(1, ["gcloud"], stderr="permission denied")
        with patch.object(registry.subprocess, "run", side_effect=[
            result(records), error, result(records),
        ]):
            with self.assertRaises(subprocess.CalledProcessError):
                registry.prune_images(BASE, record(3)["version"])

    def test_permission_errors_are_not_treated_as_an_empty_repository(self):
        error = subprocess.CalledProcessError(1, ["gcloud"], stderr="permission denied")
        with patch.object(registry.subprocess, "run", side_effect=error):
            with self.assertRaises(subprocess.CalledProcessError):
                registry.select_image(BASE, SHA, False)

    def test_invalid_metadata_aborts_before_deletion(self):
        invalid = record(1)
        invalid["version"] = "not-a-digest"
        no_timezone = record(1)
        no_timezone["createTime"] = "2026-10-01T12:00:00"
        for records in ([invalid], [no_timezone], [record(1), record(1)], {"not": "a list"}):
            with self.subTest(records=records):
                with patch.object(registry.subprocess, "run", return_value=result(records)) as run:
                    with self.assertRaises(ValueError):
                        registry.prune_images(BASE, record(1)["version"])
                    self.assertEqual(run.call_count, 1)

    def test_invalid_image_sha_and_digest_do_not_invoke_gcloud(self):
        with patch.object(registry.subprocess, "run") as run:
            with self.assertRaises(ValueError):
                registry.select_image(BASE, "invalid-sha", True)
            with self.assertRaises(ValueError):
                registry.select_image("another-repository", SHA, True)
            with self.assertRaises(ValueError):
                registry.prune_images(BASE, "invalid-digest")
            run.assert_not_called()

    def test_selection_writes_github_outputs(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "outputs"
            with patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}):
                with patch.object(registry.sys, "argv", [
                    "registry_images.py", "select", "--image-base", BASE,
                    "--sha", SHA, "--source-changed", "true",
                ]):
                    with patch.object(registry.subprocess, "run", return_value=result([])):
                        with redirect_stdout(io.StringIO()):
                            self.assertEqual(registry.main(), 0)
            self.assertEqual(output.read_text(), f"build=true\nimage={BASE}:{SHA}\n")

    def test_cli_reports_gcloud_errors_and_fails(self):
        with patch.object(registry.sys, "argv", [
            "registry_images.py", "prune", "--image-base", BASE,
            "--keep-digest", record(1)["version"],
        ]):
            error = subprocess.CalledProcessError(1, ["gcloud"], stderr="permission denied")
            with patch.object(registry.subprocess, "run", side_effect=error):
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    self.assertEqual(registry.main(), 1)
                self.assertIn("permission denied", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
