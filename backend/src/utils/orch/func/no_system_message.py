"""Load deterministic localized guidance when no configured subsystem matches.

This fallback uses YAML rather than another LLM call, so a rejected domain
request cannot accidentally dispatch to an unsupported tool or subsystem.
"""

from collections.abc import Mapping
from pathlib import Path

import yaml


def no_system_message(language: str = "EN") -> str:
	"""Read and validate the selected language's no-match response.

    Args:
        language (str): ``EN`` or ``ES``.

    Returns:
        str: Configured message, preserving its original whitespace.

    Raises:
        ValueError: Language, YAML syntax, mapping shape, or message is invalid.
        OSError: The packaged message file cannot be read.
    """
	# 1. Reject unknown languages rather than silently changing response language.
	if language not in ("ES", "EN"):
		raise ValueError("language must be ES (Spanish) or EN (English)")
	path = (
		Path(__file__).resolve().parents[3]
		/ "config/prompts/nosystem/nosystem.yaml"
	)
	try:
		# 2. Convert syntax errors into the same configuration contract as shape errors.
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
