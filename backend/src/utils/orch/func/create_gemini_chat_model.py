from collections.abc import Callable

from utils.general.GeminiApiCall import GeminiClient


def create_gemini_chat_model(
	client: GeminiClient | None = None,
) -> Callable[[list[dict[str, str]]], str]:
	"""Adapt a reusable Gemini client to the chat callable interface."""
	gemini_client = GeminiClient() if client is None else client

	def chat_model(messages: list[dict[str, str]]) -> str:
		return gemini_client.generate(
			messages[1]["content"], system_prompt=messages[0]["content"]
		).strip()

	return chat_model
