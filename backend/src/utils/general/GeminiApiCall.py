"""Provide the synchronous Gemini transport shared by agent subsystems.

This module resolves provider settings and calls the Gemini Developer REST API
using standard-library HTTP primitives. Callers supply user text and optional
system instructions; the client does not select agents or execute model tools.
JSON output mode requests a MIME type but leaves schema validation to subsystem
Pydantic models. Provider, network, and decoding failures remain visible to the
calling workflow rather than becoming successful fallback responses.
"""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import Literal
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from dotenv import dotenv_values

from obervability.logger import Logger


ENV_FILE = Path(__file__).resolve().parents[4] / ".env"
logger = Logger.get_logger(__name__)


def _configuration_value(name: str, default: str = "") -> str:
    """Resolve a provider setting without interpolating dotenv values.

    Args:
        name: Environment variable or dotenv entry to read.
        default: Value used when the entry or dotenv file is absent.

    Returns:
        str: Environment value if present; otherwise the dotenv value or default.
            An empty or null dotenv entry resolves to an empty string.

    Raises:
        OSError: The existing dotenv file cannot be opened or read.
    """
    # 1. Preserve explicit deployment settings, including empty values.
    value = os.environ.get(name)
    if value is not None:
        return value
    # 2. Consult the project dotenv file only when the environment has no value.
    if not ENV_FILE.exists():
        return default
    with ENV_FILE.open(encoding="utf-8") as stream:
        return dotenv_values(stream=stream, interpolate=False).get(name, default) or ""


@dataclass
class GeminiClient:
    """Hold provider credentials and limits for synchronous Gemini requests.

    Attributes:
        api_key (str): Stripped API credential, excluded from dataclass repr.
        model (str): Model identifier, defaulting to LLM_MODEL or
            ``gemini-2.5-flash-lite``.
        max_output_tokens (int): Positive generation output limit, default 256.
        timeout (float): Positive HTTP timeout in seconds, default 30.0.
    """

    api_key: str = field(
        default_factory=lambda: _configuration_value("GEMINI_API_KEY"),
        repr=False,
    )
    model: str = field(
        default_factory=lambda: _configuration_value("LLM_MODEL", "gemini-2.5-flash-lite")
    )
    max_output_tokens: int = 256
    timeout: float = 30.0

    def __post_init__(self) -> None:
        """Normalize provider settings and reject unusable client configuration.

        Returns:
            None: Validates and normalizes the instance in place.

        Raises:
            ValueError: Credentials or model are blank, or limits are nonpositive.
        """
        # 1. Fail before network access when required provider settings are absent.
        self.api_key = self.api_key.strip()
        if not self.api_key:
            raise ValueError(
                "Set GEMINI_API_KEY in .env or the environment to your Google AI Studio API key."
            )
        self.model = self.model.strip()
        if not self.model:
            raise ValueError("model (LLM_MODEL) must not be empty.")
        # 2. Bound request resources through positive configured limits.
        if self.max_output_tokens <= 0 or self.timeout <= 0:
            raise ValueError("max_output_tokens and timeout must be positive.")

    @Logger.trace(logger)
    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        response_mime_type: Literal["text/plain", "application/json"] = "text/plain",
    ) -> str:
        """Generate visible text from one user message and optional instructions.

        Args:
            prompt: Nonblank user content sent unchanged to Gemini.
            system_prompt: Optional nonblank instructions inserted in the
                provider's ``systemInstruction`` field, not the user message.
            response_mime_type: Requested text or JSON output mode; JSON
                schema validation remains the caller's responsibility.

        Returns:
            str: Concatenated non-thought text from the first candidate.

        Raises:
            ValueError: Input text or output mode is invalid, or the provider
                response cannot be decoded as JSON.
            RuntimeError: The provider returns no candidates or usable text.
            urllib.error.HTTPError: Gemini rejects the HTTP request.
            urllib.error.URLError: The provider cannot be reached.
            TimeoutError: Network operations time out.
        """
        # 1. Reject unusable requests before consuming provider quota.
        if not prompt.strip():
            raise ValueError("prompt must not be empty.")
        if system_prompt is not None and not system_prompt.strip():
            raise ValueError("system_prompt must not be empty.")
        if response_mime_type not in ("text/plain", "application/json"):
            raise ValueError("response_mime_type must be text/plain or application/json.")

        # 2. Separate system instructions from user content at the provider boundary.
        payload: dict[str, object] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": self.max_output_tokens,
                "responseMimeType": response_mime_type,
            },
        }
        if system_prompt is not None:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        # 3. Authenticate via headers and send a bounded synchronous REST request.
        request = Request(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{quote(self.model, safe='')}:generateContent",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )
        with urlopen(request, timeout=self.timeout) as response:
            result = json.load(response)

        # 4. Exclude thought parts and reject blocked or empty generations.
        candidates = result.get("candidates", [])
        if not candidates:
            reason = result.get("promptFeedback", {}).get("blockReason", "no candidates")
            raise RuntimeError(f"Gemini returned no text: {reason}.")
        candidate = candidates[0]
        text = "".join(
            part["text"]
            for part in candidate.get("content", {}).get("parts", [])
            if "text" in part and not part.get("thought", False)
        )
        if not text.strip():
            reason = candidate.get("finishReason", "empty response")
            raise RuntimeError(f"Gemini returned no text: {reason}.")
        return text

    @Logger.trace(logger)
    def list_models(self) -> list[str]:
        """Enumerate models that support content generation for this credential.

        Returns:
            list[str]: Model identifiers without the ``models/`` prefix, in
                provider page order.

        Raises:
            RuntimeError: No compatible models are returned.
            ValueError: A provider response is not valid JSON.
            urllib.error.HTTPError: The provider rejects the listing request.
            urllib.error.URLError: The provider cannot be reached.
            TimeoutError: A listing request times out.
        """
        # 1. Follow provider pagination so diagnostics see the complete model set.
        models = []
        page_token = ""
        while True:
            url = "https://generativelanguage.googleapis.com/v1beta/models"
            if page_token:
                url += "?" + urlencode({"pageToken": page_token})
            request = Request(url, headers={"x-goog-api-key": self.api_key})
            with urlopen(request, timeout=self.timeout) as response:
                result = json.load(response)
            # 2. Keep only models usable by the generation transport.
            models.extend(
                model["name"].removeprefix("models/")
                for model in result.get("models", [])
                if "generateContent" in model.get("supportedGenerationMethods", [])
            )
            page_token = result.get("nextPageToken", "")
            if not page_token:
                break
        # 3. Surface unavailable generation capability rather than an empty success.
        if not models:
            raise RuntimeError("No text-generation models are available for this API key.")
        return models