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
        # RECALL_DATA_DIR redirects everything — database, audio, slides —
        # somewhere else. Tests must set it: they create and delete courses
        # wholesale, and pointing that at the real data_dir destroys recordings.
        override = os.getenv("RECALL_DATA_DIR", "").strip()
        self.data_dir = (
            Path(override).resolve()
            if override
            else (REPO_ROOT / "backend" / storage.get("data_dir", "../data")).resolve()
        )
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "recall.db"

        # The project was called TranscribeAI before. Carry an existing database
        # over rather than silently starting an empty one beside it — it holds
        # recordings that cannot be made again. If the rename cannot happen
        # (file locked, permissions), keep using the old file instead.
        legacy_db = self.data_dir / "transcribeai.db"
        if legacy_db.exists() and not self.db_path.exists():
            try:
                legacy_db.rename(self.db_path)
            except OSError:
                self.db_path = legacy_db

        self.transcription: dict[str, Any] = self._cfg.get("transcription", {})
        # values are provider/model strings plus an optional compare_with list
        self.tasks: dict[str, dict[str, Any]] = self._cfg.get("tasks", {})

        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.openai_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        # 127.0.0.1, not localhost: Ollama binds IPv4 only, and localhost resolves
        # to ::1 first on Windows, which costs a connection timeout per call.
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")


settings = Settings()
