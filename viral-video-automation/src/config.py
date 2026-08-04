"""Loads config.yaml + .env into a single settings object used by every stage."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from .logging_setup import configure_logging

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")
configure_logging(PROJECT_ROOT / "data" / "pipeline.log")


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
    def mascot(self) -> dict:
        return self.raw.get("mascot", {"enabled": False})

    @property
    def narration(self) -> dict:
        cfg = dict(self.raw.get("narration", {"enabled": False}))
        cfg["provider"] = os.environ.get("TTS_PROVIDER", cfg.get("provider", "mock"))
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
    def fal_api_key(self) -> str | None:
        # Pika's API is served through fal.ai; FAL_KEY matches fal's own
        # SDK/CLI convention so any snippets copied from their docs work as-is.
        return os.environ.get("FAL_KEY") or None

    @property
    def elevenlabs_api_key(self) -> str | None:
        return os.environ.get("ELEVENLABS_API_KEY") or None

    @property
    def youtube_client_secret_file(self) -> Path:
        return PROJECT_ROOT / os.environ.get("YOUTUBE_CLIENT_SECRET_FILE", "youtube_client_secret.json")

    @property
    def youtube_token_file(self) -> Path:
        return PROJECT_ROOT / os.environ.get("YOUTUBE_TOKEN_FILE", "youtube_token.json")


def _validate(raw: dict) -> None:
    """Fail fast with a clear message instead of a confusing KeyError deep
    in some stage that only runs twice a week -- by the time that happens
    you've forgotten what you edited in config.yaml."""
    required_sections = ["niche", "trend_scanner", "ideation", "video_generation", "review", "upload"]
    missing = [s for s in required_sections if s not in raw]
    if missing:
        raise ValueError(f"config.yaml is missing required section(s): {missing}")

    if not raw["trend_scanner"].get("search_queries"):
        raise ValueError("config.yaml: trend_scanner.search_queries must be a non-empty list")

    vg = raw["video_generation"]
    if vg.get("scenes_per_video", 0) < 1:
        raise ValueError("config.yaml: video_generation.scenes_per_video must be >= 1")
    if vg.get("target_duration_seconds", 0) <= 0:
        raise ValueError("config.yaml: video_generation.target_duration_seconds must be > 0")
    if "x" not in str(vg.get("resolution", "")):
        raise ValueError("config.yaml: video_generation.resolution must look like '1080x1920'")

    if raw["upload"].get("privacy_status") not in ("private", "unlisted", "public"):
        raise ValueError("config.yaml: upload.privacy_status must be one of private/unlisted/public")


def load_settings(config_path: Path | None = None) -> Settings:
    config_path = config_path or (PROJECT_ROOT / "config" / "config.yaml")
    with open(config_path) as f:
        raw = yaml.safe_load(f)
    _validate(raw)
    return Settings(raw=raw)
