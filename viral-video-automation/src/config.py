"""Loads config.yaml + .env into a single settings object used by every stage."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")


@dataclass
class Settings:
    raw: dict[str, Any]

    @property
    def niche(self) -> str:
        return self.raw["niche"]

    @property
    def trend_scanner(self) -> dict:
        return self.raw["trend_scanner"]

    @property
    def ideation(self) -> dict:
        return self.raw["ideation"]

    @property
    def video_generation(self) -> dict:
        cfg = dict(self.raw["video_generation"])
        cfg["provider"] = os.environ.get("VIDEO_PROVIDER", cfg.get("provider", "mock"))
        return cfg

    @property
    def review(self) -> dict:
        return self.raw["review"]

    @property
    def upload(self) -> dict:
        return self.raw["upload"]

    def path(self, relative: str) -> Path:
        p = PROJECT_ROOT / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    # --- secrets (env-only, never in yaml) ---
    @property
    def youtube_api_key(self) -> str | None:
        return os.environ.get("YOUTUBE_API_KEY") or None

    @property
    def anthropic_api_key(self) -> str | None:
        return os.environ.get("ANTHROPIC_API_KEY") or None

    @property
    def runway_api_key(self) -> str | None:
        return os.environ.get("RUNWAY_API_KEY") or None

    @property
    def youtube_client_secret_file(self) -> Path:
        return PROJECT_ROOT / os.environ.get("YOUTUBE_CLIENT_SECRET_FILE", "youtube_client_secret.json")

    @property
    def youtube_token_file(self) -> Path:
        return PROJECT_ROOT / os.environ.get("YOUTUBE_TOKEN_FILE", "youtube_token.json")


def load_settings(config_path: Path | None = None) -> Settings:
    config_path = config_path or (PROJECT_ROOT / "config" / "config.yaml")
    with open(config_path) as f:
        raw = yaml.safe_load(f)
    return Settings(raw=raw)
