#!/usr/bin/env python3
"""One-time setup: authorize this app to upload videos to your YouTube
channel, and save a reusable token.

1. In Google Cloud Console, create/select a project, then enable the
   "YouTube Data API v3", then create an OAuth client ID of type
   "Desktop app" (APIs & Services -> Credentials).
2. Download the JSON and save it as youtube_client_secret.json in the
   project root (or point YOUTUBE_CLIENT_SECRET_FILE in .env at it).
3. Run: python scripts/setup_youtube_oauth.py
   A browser window opens asking you to sign in and grant upload access
   to whichever Google account/channel you choose. That's the channel
   stage 5 will publish to.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google_auth_oauthlib.flow import InstalledAppFlow

from src.config import load_settings

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main() -> None:
    settings = load_settings()
    client_secret_file = settings.youtube_client_secret_file
    if not client_secret_file.exists():
        raise SystemExit(
            f"Missing {client_secret_file}. See the docstring at the top of "
            "this script for how to create/download it."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_file), SCOPES)
    creds = flow.run_local_server(port=0)

    token_file = settings.youtube_token_file
    token_file.write_text(creds.to_json())
    print(f"Saved credentials to {token_file}. You can now run stage 5 uploads.")


if __name__ == "__main__":
    main()
