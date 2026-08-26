"""Loads config.yaml (repo root) and .env into one settings object."""

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config.yaml"

load_dotenv(REPO_ROOT / ".env")


class Settings:
    def __init__(self) -> None:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            self._cfg: dict[str, Any] = yaml.safe_load(f)

        storage = self._cfg.get("storage", {})
        self.data_dir = (REPO_ROOT / "backend" / storage.get("data_dir", "../data")).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "transcribeai.db"

        server = self._cfg.get("server", {})
        self.host: str = server.get("host", "127.0.0.1")
        self.port: int = int(server.get("port", 8000))

        self.transcription: dict[str, Any] = self._cfg.get("transcription", {})
        self.tasks: dict[str, dict[str, str]] = self._cfg.get("tasks", {})

        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.openai_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


settings = Settings()
