"""Resolve the deployment mode shared by SQL and image-storage providers.

Environment settings take precedence over caller-loaded dotenv settings.
Invalid modes fail explicitly so a deployment cannot silently select another
storage provider.
"""

from collections.abc import Mapping
import os


def runtime_mode(settings: Mapping[str, str | None]) -> str:
    """Resolve and validate the local or cloud deployment mode.

    Args:
        settings: Dotenv-style settings used when MODE is absent from the
            process environment.

    Returns:
        str: Normalized ``LOCAL`` or ``CLOUD``; defaults to ``LOCAL``.

    Raises:
        ValueError: The resolved MODE is empty or unsupported.
    """
    # 1. Honor deployment overrides before consulting file-based defaults.
    mode = (os.environ.get("MODE", settings.get("MODE", "LOCAL")) or "").strip().upper()
    # 2. Reject ambiguous configuration rather than choosing a fallback provider.
    if mode not in ("LOCAL", "CLOUD"):
        raise ValueError("MODE must be LOCAL or CLOUD.")
    return mode
