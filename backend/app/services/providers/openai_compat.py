"""OpenAI-compatible provider (OpenAI, Groq, Together, OpenRouter, ...).

Point OPENAI_BASE_URL at any compatible endpoint.
"""

from ...config import settings
from .base import LLMProvider


class OpenAICompatProvider(LLMProvider):
    name = "openai"

    def complete(
        self,
        messages: list[dict[str, str]],
        system: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> str:
        from openai import OpenAI

        client = OpenAI(
            api_key=settings.openai_api_key, base_url=settings.openai_base_url
        )
        full_messages = ([{"role": "system", "content": system}] if system else []) + messages
        response = client.chat.completions.create(
            model=self.model,
            messages=full_messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content or ""

    def available(self) -> bool:
        return bool(settings.openai_api_key)
