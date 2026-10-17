"""Upload the local image tree to the production bucket using the gcloud CLI."""

import argparse
from pathlib import Path
import shlex
import shutil
import subprocess
import sys


SOURCE_DIRECTORY = Path(__file__).resolve().parents[1] / "database" / "images"
DESTINATION = "gs://orch_app_bucket/images/"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show proposed transfers without uploading or changing objects.",
    )
    args = parser.parse_args(argv)

    if not SOURCE_DIRECTORY.is_dir():
        parser.error(f"Image directory does not exist: {SOURCE_DIRECTORY}")

    gcloud = shutil.which("gcloud")
    if gcloud is None:
        parser.error("Install the Google Cloud CLI and authenticate with gcloud auth login.")

    command = [
        gcloud,
        "storage",
        "rsync",
        str(SOURCE_DIRECTORY),
        DESTINATION,
        "--recursive",
        "--checksums-only",
        r"--exclude=(^|/)\.gitkeep$",
    ]
    if args.dry_run:
        command.append("--dry-run")

    print(shlex.join(command), flush=True)
    try:
        result = subprocess.run(command, check=False)
    except OSError as error:
        print(f"Could not start gcloud: {error}", file=sys.stderr)
        return 1

    if result.returncode != 0:
        print(f"Image migration failed: gcloud exited with {result.returncode}.", file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())