from pathlib import Path


def resolve_systems_path(systems_path: str | Path | None = None) -> Path:
	return (
		Path(systems_path)
		if systems_path is not None
		else Path(__file__).resolve().parents[3] / "config/systems.json"
	)
