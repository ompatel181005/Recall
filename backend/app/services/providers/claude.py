"""Anthropic Claude provider."""

from ...config import settings
from .base import LLMProvider


class ClaudeProvider(LLMProvider):
    name = "claude"

    def complete(
        self,
        messages: list[dict[str, str]],
        system: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=self.model,
            system=system or anthropic.NOT_GIVEN,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return "".join(block.text for block in response.content if block.type == "text")

    def available(self) -> bool:
        return bool(settings.anthropic_api_key)
