"""Reusable Gemini Developer API client with text and JSON output modes."""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import Literal
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from dotenv import dotenv_values


ENV_FILE = Path(__file__).resolve().parents[4] / ".env"


def _configuration_value(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value is not None:
        return value
    if not ENV_FILE.exists():
        return default
    with ENV_FILE.open(encoding="utf-8") as stream:
        return dotenv_values(stream=stream, interpolate=False).get(name, default) or ""


@dataclass
class GeminiClient:
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
        self.api_key = self.api_key.strip()
        if not self.api_key:
            raise ValueError(
                "Set GEMINI_API_KEY in .env or the environment to your Google AI Studio API key."
            )
        self.model = self.model.strip()
        if not self.model:
            raise ValueError("model (LLM_MODEL) must not be empty.")
        if self.max_output_tokens <= 0 or self.timeout <= 0:
            raise ValueError("max_output_tokens and timeout must be positive.")

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        response_mime_type: Literal["text/plain", "application/json"] = "text/plain",
    ) -> str:
        """Return generated text; API, network, and response errors propagate."""
        if not prompt.strip():
            raise ValueError("prompt must not be empty.")
        if system_prompt is not None and not system_prompt.strip():
            raise ValueError("system_prompt must not be empty.")
        if response_mime_type not in ("text/plain", "application/json"):
            raise ValueError("response_mime_type must be text/plain or application/json.")

        payload: dict[str, object] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": self.max_output_tokens,
                "responseMimeType": response_mime_type,
            },
        }
        if system_prompt is not None:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

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

    def list_models(self) -> list[str]:
        """List models supporting text generation for this API key."""
        models = []
        page_token = ""
        while True:
            url = "https://generativelanguage.googleapis.com/v1beta/models"
            if page_token:
                url += "?" + urlencode({"pageToken": page_token})
            request = Request(url, headers={"x-goog-api-key": self.api_key})
            with urlopen(request, timeout=self.timeout) as response:
                result = json.load(response)
            models.extend(
                model["name"].removeprefix("models/")
                for model in result.get("models", [])
                if "generateContent" in model.get("supportedGenerationMethods", [])
            )
            page_token = result.get("nextPageToken", "")
            if not page_token:
                break
        if not models:
            raise RuntimeError("No text-generation models are available for this API key.")
        return models