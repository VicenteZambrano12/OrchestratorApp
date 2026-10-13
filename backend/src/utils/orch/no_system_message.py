from collections.abc import Mapping
from pathlib import Path

import yaml


def no_system_message(language: str = "EN") -> str:
	"""Load the user-facing no-match message for the requested language."""
	if language not in ("ES", "EN"):
		raise ValueError("language must be ES (Spanish) or EN (English)")
	path = (
		Path(__file__).resolve().parents[2]
		/ "config/prompts/nosystem/nosystem.yaml"
	)
	try:
		configuration = yaml.safe_load(path.read_text(encoding="utf-8"))
	except yaml.YAMLError as error:
		raise ValueError("invalid no_system message YAML") from error
	if not isinstance(configuration, Mapping):
		raise ValueError("no_system message file must contain a YAML mapping")
	messages = configuration.get("messages")
	if not isinstance(messages, Mapping):
		raise ValueError("no_system message file must contain a messages mapping")
	message = messages.get(language)
	if not isinstance(message, str) or not message.strip():
		raise ValueError(f"no_system message for {language} must be a non-empty string")
	return message
