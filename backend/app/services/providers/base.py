"""LLMProvider interface — all feature code talks to LLMs through this.

A "message" is {"role": "user" | "assistant", "content": str}.
"""

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    name: str

    def __init__(self, model: str) -> None:
        self.model = model

    @abstractmethod
    def complete(
        self,
        messages: list[dict[str, str]],
        system: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> str:
        """Return the assistant's text response."""

    @abstractmethod
    def available(self) -> bool:
        """True if this provider is usable right now (key set / server up)."""
