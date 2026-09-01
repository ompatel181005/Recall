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


def get_provider(name: str, model: str) -> LLMProvider:
    """Build a provider directly, for one-off overrides (e.g. comparing the
    configured default against a local model). Normal feature code should ask
    for a task instead."""
    provider_cls = _PROVIDERS.get(name)
    if not provider_cls:
        raise KeyError(f"Unknown provider '{name}' (valid: {', '.join(_PROVIDERS)})")
    return provider_cls(model=model)


def options_for_task(task: str) -> list[dict]:
    """The configured provider for a task plus any `compare_with` alternatives,
    each flagged with whether it can run right now. Drives the model picker in
    the UI without hard-coding model names in the frontend."""
    task_cfg = settings.tasks.get(task)
    if not task_cfg:
        return []

    entries = [
        {"provider": task_cfg.get("provider", ""), "model": task_cfg.get("model", ""),
         "is_default": True}
    ]
    for alternative in task_cfg.get("compare_with") or []:
        entries.append(
            {"provider": alternative.get("provider", ""),
             "model": alternative.get("model", ""), "is_default": False}
        )

    options = []
    for entry in entries:
        try:
            available = get_provider(entry["provider"], entry["model"]).available()
        except KeyError:
            available = False
        options.append({**entry, "available": available})
    return options


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
