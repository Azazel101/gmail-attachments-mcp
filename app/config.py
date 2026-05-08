"""Centralized configuration loaded from environment / .env file."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


# ---------- Paths ----------
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", str(DATA_DIR / "downloads")))
TOKEN_PATH = Path(os.getenv("GMAIL_TOKEN_PATH", str(DATA_DIR / "token.json")))
CREDENTIALS_PATH = Path(
    os.getenv("GMAIL_CREDENTIALS_PATH", str(DATA_DIR / "credentials.json"))
)
LOG_PATH = Path(os.getenv("LOG_PATH", str(DATA_DIR / "server.log")))

DATA_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ---------- Server ----------
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8765"))
PUBLIC_URL = os.getenv("PUBLIC_URL", f"http://localhost:{PORT}").rstrip("/")

# Web UI session secret - generuj cez `openssl rand -hex 32`
SESSION_SECRET = os.getenv("SESSION_SECRET", "change-me-in-production-please")

# Voliteľné: ďalšia auth vrstva pred web UI (HTTP Basic).
# Ak je UI_PASSWORD nastavené, web rozhranie vyžaduje login.
UI_USERNAME = os.getenv("UI_USERNAME", "admin")
UI_PASSWORD = os.getenv("UI_PASSWORD")  # None = bez auth (len pre lokálnu sieť!)


# ---------- Gmail OAuth ----------
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
OAUTH_REDIRECT_PATH = "/oauth/callback"
OAUTH_REDIRECT_URI = f"{PUBLIC_URL}{OAUTH_REDIRECT_PATH}"


# ---------- OCR ----------
OCR_PIPELINE_URL = os.getenv("OCR_PIPELINE_URL")  # voliteľný forward
