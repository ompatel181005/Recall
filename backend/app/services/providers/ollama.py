"""Local Ollama provider (free, private, runs on the laptop GPU)."""

import httpx

from ...config import settings
from .base import LLMProvider


class OllamaProvider(LLMProvider):
    name = "ollama"

    def complete(
        self,
        messages: list[dict[str, str]],
        system: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> str:
        full_messages = ([{"role": "system", "content": system}] if system else []) + messages
        response = httpx.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": self.model,
                "messages": full_messages,
                "stream": False,
                "options": {"num_predict": max_tokens, "temperature": temperature},
            },
            timeout=300.0,
        )
        response.raise_for_status()
        return response.json()["message"]["content"]

    def available(self) -> bool:
        try:
            return (
                httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=2.0).status_code
                == 200
            )
        except httpx.HTTPError:
            return False
