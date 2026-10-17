#!/usr/bin/env python3
import argparse
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys


DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
IMAGE_BASE = re.compile(
    r"[a-z0-9-]+-docker\.pkg\.dev/[a-z][a-z0-9-]*/[a-z][a-z0-9-]*/[a-z0-9]+(?:[._-][a-z0-9]+)*"
)


@dataclass(frozen=True)
class Image:
    digest: str
    created: datetime
    tags: tuple[str, ...]


def list_images(base: str) -> list[Image]:
    if not IMAGE_BASE.fullmatch(base):
        raise ValueError("Expected a fully qualified application image without a tag or digest.")
    result = subprocess.run(
        ["gcloud", "artifacts", "docker", "images", "list", base,
         "--include-tags", "--format=json", "--quiet"],
        capture_output=True, text=True, check=True,
    )
    records = json.loads(result.stdout)
    if not isinstance(records, list):
        raise ValueError("Artifact Registry did not return an image list.")
    images = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Artifact Registry returned invalid image metadata.")
        if record.get("package") != base:
            continue
        digest, timestamp, tags = record.get("version"), record.get("createTime"), record.get("tags", [])
        if (
            not isinstance(digest, str) or not DIGEST.fullmatch(digest)
            or not isinstance(timestamp, str)
            or not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags)
        ):
            raise ValueError("Artifact Registry returned invalid image version metadata.")
        created = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if created.utcoffset() is None:
            raise ValueError("Image creation timestamps must include a timezone.")
        images.append(Image(digest, created, tuple(tags)))
    if len({image.digest for image in images}) != len(images):
        raise ValueError("Artifact Registry returned duplicate image versions.")
    return sorted(images, key=lambda image: (image.created, image.digest), reverse=True)


def select_image(base: str, sha: str, source_changed: bool) -> dict[str, str]:
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Expected a full Git commit SHA.")
    images = list_images(base)
    matching = next((image for image in images if sha in image.tags), None)
    if matching is not None:
        return {"build": "false", "image": f"{base}@{matching.digest}"}
    if source_changed or not images:
        return {"build": "true", "image": f"{base}:{sha}"}
    return {"build": "false", "image": f"{base}@{images[0].digest}"}


def prune_images(base: str, keep_digest: str) -> None:
    if not DIGEST.fullmatch(keep_digest):
        raise ValueError("Expected the selected image's sha256 digest.")
    images = list_images(base)
    if keep_digest not in {image.digest for image in images[:2]}:
        raise ValueError("Selected image is not among the two newest versions; refusing deletion.")
    for image in images[2:]:
        try:
            subprocess.run(
                ["gcloud", "artifacts", "docker", "images", "delete",
                 f"{base}@{image.digest}", "--delete-tags", "--quiet"],
                capture_output=True, text=True, check=True,
            )
        except subprocess.CalledProcessError:
            if image.digest in {current.digest for current in list_images(base)}:
                raise
            print(f"Verified {image.digest} was already removed by concurrent cleanup.")
    remaining = list_images(base)
    if len(remaining) > 2 or keep_digest not in {image.digest for image in remaining}:
        raise RuntimeError("Could not verify the two-image retention limit and selected image.")
    print(f"Verified {len(remaining)} retained application image version(s).")


def main() -> int:
    parser = argparse.ArgumentParser(description="Select and retain production application images.")
    parser.add_argument("command", choices=("select", "prune"))
    parser.add_argument("--image-base", required=True)
    parser.add_argument("--sha")
    parser.add_argument("--source-changed", choices=("true", "false"), default="false")
    parser.add_argument("--keep-digest")
    arguments = parser.parse_args()
    try:
        if arguments.command == "select":
            if arguments.sha is None:
                parser.error("select requires --sha")
            selected = select_image(
                arguments.image_base, arguments.sha, arguments.source_changed == "true",
            )
            output = os.environ.get("GITHUB_OUTPUT")
            if output:
                with Path(output).open("a", encoding="utf-8") as stream:
                    for key, value in selected.items():
                        stream.write(f"{key}={value}\n")
            print(json.dumps(selected))
        else:
            if arguments.keep_digest is None:
                parser.error("prune requires --keep-digest")
            prune_images(arguments.image_base, arguments.keep_digest)
    except subprocess.CalledProcessError as error:
        print(error.stderr, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
