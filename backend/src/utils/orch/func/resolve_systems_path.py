"""Resolve router configuration locations without reading or validating files.

The route helper loads this path only when a request omits inline subsystems.
"""

from pathlib import Path


def resolve_systems_path(systems_path: str | Path | None = None) -> Path:
	"""Choose an explicit systems file or the packaged configuration path.

    Args:
        systems_path (str | Path | None): Optional caller-provided file path.

    Returns:
        Path: Override as supplied, or the source-relative ``config/systems.json``.
    """
	# 1. Defer filesystem access until routing actually needs configured targets.
	return (
		Path(systems_path)
		if systems_path is not None
		else Path(__file__).resolve().parents[3] / "config/systems.json"
	)
