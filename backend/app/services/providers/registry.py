"""Resolves a task name (config.yaml `tasks:`) to a configured provider."""

from ...config import settings
from .base import LLMProvider
from .claude import ClaudeProvider
from .ollama import OllamaProvider
from .openai_compat import OpenAICompatProvider

_PROVIDERS: dict[str, type[LLMProvider]] = {
    "claude": ClaudeProvider,
    "openai": OpenAICompatProvider,
    "ollama": OllamaProvider,
}


def get_provider_for_task(task: str) -> LLMProvider:
    task_cfg = settings.tasks.get(task)
    if not task_cfg:
        raise KeyError(f"Task '{task}' is not defined in config.yaml under tasks:")
    provider_name = task_cfg.get("provider", "")
    provider_cls = _PROVIDERS.get(provider_name)
    if not provider_cls:
        raise KeyError(
            f"Unknown provider '{provider_name}' for task '{task}' "
            f"(valid: {', '.join(_PROVIDERS)})"
        )
    return provider_cls(model=task_cfg.get("model", ""))


def provider_status() -> dict[str, bool]:
    """Which providers are usable right now — surfaced by /api/health."""
    return {name: cls(model="").available() for name, cls in _PROVIDERS.items()}
