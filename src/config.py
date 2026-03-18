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


# Instagram
IG_ACCESS_TOKEN = _require("IG_ACCESS_TOKEN")
IG_ACCOUNT_ID = _require("IG_ACCOUNT_ID")
IG_BASE_URL = "https://graph.facebook.com/v19.0"

# Etsy
ETSY_API_KEY = _require("ETSY_API_KEY")
ETSY_REFRESH_TOKEN = _require("ETSY_REFRESH_TOKEN")
ETSY_SHOP_ID = _require("ETSY_SHOP_ID")
ETSY_BASE_URL = "https://openapi.etsy.com/v3/application"

# Google Sheets
GOOGLE_SERVICE_ACCOUNT_JSON = json.loads(_require("GOOGLE_SERVICE_ACCOUNT_JSON"))
GOOGLE_SPREADSHEET_ID = _require("GOOGLE_SPREADSHEET_ID")

# Email
EMAIL_SENDER = _require("EMAIL_SENDER")
EMAIL_PASSWORD = _require("EMAIL_PASSWORD")
EMAIL_RECIPIENT = _require("EMAIL_RECIPIENT")

# GitHub (for writing refreshed tokens back to Secrets)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "")

# Sheet tab names — change these if you rename your tabs
SHEET_IG_PULSE = "ig_pulse"
SHEET_IG_STARS = "ig_stars"
SHEET_ETSY_STARS = "etsy_stars"
