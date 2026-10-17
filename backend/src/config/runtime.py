from collections.abc import Mapping
import os


def runtime_mode(settings: Mapping[str, str | None]) -> str:
    mode = (os.environ.get("MODE", settings.get("MODE", "LOCAL")) or "").strip().upper()
    if mode not in ("LOCAL", "CLOUD"):
        raise ValueError("MODE must be LOCAL or CLOUD.")
    return mode
