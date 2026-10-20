"""Bridge the router's two-message chat contract to Gemini system instructions.

One reusable client serves the closure; selection retries remain the caller's
responsibility rather than being hidden in this transport adapter.
"""

from collections.abc import Callable

from utils.general.GeminiApiCall import GeminiClient


def create_gemini_chat_model(
	client: GeminiClient | None = None,
) -> Callable[[list[dict[str, str]]], str]:
	"""Create a chat callable backed by one injected or configured client.

    Args:
        client (GeminiClient | None): Existing client, or create a default client.

    Returns:
        Callable[[list[dict[str, str]]], str]: Adapter for system/user messages.

    Raises:
        ValueError: Default Gemini configuration is invalid.
    """
	# 1. Reuse client configuration across router attempts and future requests.
	gemini_client = GeminiClient() if client is None else client

	def chat_model(messages: list[dict[str, str]]) -> str:
		"""Send the selector's user content with its separate system instruction.

        Args:
            messages (list[dict[str, str]]): System message followed by user message.

        Returns:
            str: Trimmed Gemini text, still subject to routing validation.

        Raises:
            IndexError: Either required message is missing.
            KeyError: A message omits ``content``.
            Exception: Gemini configuration, network, or response failures propagate.
        """
		# 1. Map the fixed chat ordering to Gemini's explicit system-prompt channel.
		return gemini_client.generate(
			messages[1]["content"], system_prompt=messages[0]["content"]
		).strip()

	return chat_model
