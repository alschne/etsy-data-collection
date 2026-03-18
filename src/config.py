"""
config.py — Centralised configuration. Reads from environment variables.
All other modules import from here rather than reading env vars directly.
"""

import os
import json
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(f"Required environment variable '{key}' is not set.")
    return value


def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default)


# Instagram
IG_ACCESS_TOKEN = _require("IG_ACCESS_TOKEN")
IG_ACCOUNT_ID = _require("IG_ACCOUNT_ID")
IG_APP_ID = _require("IG_APP_ID")
IG_APP_SECRET = _require("IG_APP_SECRET")
IG_BASE_URL = "https://graph.instagram.com"

# Etsy — optional until API is approved, only required when not using --skip-etsy
ETSY_API_KEY = _optional("ETSY_API_KEY")
ETSY_REFRESH_TOKEN = _optional("ETSY_REFRESH_TOKEN")
ETSY_SHOP_ID = _optional("ETSY_SHOP_ID")
ETSY_BASE_URL = "https://openapi.etsy.com/v3/application"

# Google Sheets
# Accepts either a file path (local dev) or a raw JSON string (GitHub Secrets)
_sa_value = _require("GOOGLE_SERVICE_ACCOUNT_JSON")
if _sa_value.strip().startswith("{"):
    GOOGLE_SERVICE_ACCOUNT_JSON = json.loads(_sa_value)
else:
    with open(_sa_value) as _f:
        GOOGLE_SERVICE_ACCOUNT_JSON = json.load(_f)

GOOGLE_SPREADSHEET_ID = _require("GOOGLE_SPREADSHEET_ID")

# Google AI (Gemini) — for AI-generated insights in the weekly email
GOOGLE_AI_API_KEY = _optional("GOOGLE_AI_API_KEY")

# Email
EMAIL_SENDER = _require("EMAIL_SENDER")
EMAIL_PASSWORD = _require("EMAIL_PASSWORD")
EMAIL_RECIPIENT = _require("EMAIL_RECIPIENT")

# GitHub (for writing refreshed tokens back to Secrets)
GITHUB_TOKEN = _optional("GITHUB_TOKEN")
GITHUB_REPO = _optional("GITHUB_REPO")

# Sheet tab names — change these if you rename your tabs
SHEET_IG_PULSE = "ig_pulse"
SHEET_IG_STARS = "ig_stars"
SHEET_ETSY_STARS = "etsy_stars"