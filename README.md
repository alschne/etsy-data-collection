# Etsy + Instagram Analytics Pipeline

Automated weekly data collection for your Etsy shop and connected Instagram account.
Pulls data from the Etsy API and Instagram Graph API, appends to Google Sheets, and
sends a weekly email digest.

## What gets automated

| Tab | Source | Cadence |
|-----|--------|---------|
| `ig_pulse` | Instagram Graph API | Weekly (Sunday) |
| `ig_stars` | Instagram Graph API | Weekly (new posts only) |
| `etsy_stars` | Etsy Open API v3 | Weekly (active + auto-renew listings) |
| `etsy_pulse` | **Manual** | Monthly (Etsy doesn't expose stats via API) |

## Repo structure

```
.
├── .github/
│   └── workflows/
│       └── weekly_pipeline.yml   # GitHub Actions cron schedule
├── src/
│   ├── main.py                   # Entry point — runs all collectors
│   ├── ig_collector.py           # Instagram Graph API logic
│   ├── etsy_collector.py         # Etsy API logic
│   ├── sheets.py                 # Google Sheets read/write helpers
│   ├── email_digest.py           # Weekly email summary
│   └── config.py                 # Centralised config (reads from env)
├── requirements.txt
└── README.md
```

## First-time setup

### 1. Instagram Graph API credentials

1. Go to [developers.facebook.com](https://developers.facebook.com) and create an app
   - App type: **Business**
2. Add the **Instagram Graph API** product
3. Under Instagram → API Setup, connect your Instagram Business account via your linked Facebook Page
4. Generate a **long-lived Page Access Token** (valid 60 days — see note below on refresh)
5. Find your **Instagram Business Account ID** (shown in the API setup screen)

You'll need:
- `IG_ACCESS_TOKEN` — your long-lived access token
- `IG_ACCOUNT_ID` — your Instagram Business Account ID

> ⚠️ Long-lived tokens expire after 60 days. The script auto-refreshes the token on each
> run and saves the new value back to your GitHub Secret via the GitHub API. See
> `config.py` for details.

### 2. Etsy API credentials

1. Go to [etsy.com/developers](https://www.etsy.com/developers) and create an app
2. Note your **Keystring** (API key)
3. Complete the OAuth 2.0 flow once using `scripts/etsy_auth.py` to get your
   refresh token — this only needs to be done once
4. Note your **Shop ID** (visible in your Etsy shop URL)

You'll need:
- `ETSY_API_KEY` — your app keystring
- `ETSY_REFRESH_TOKEN` — obtained from the one-time OAuth flow
- `ETSY_SHOP_ID` — your numeric shop ID

### 3. Google Sheets + Service Account

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project → Enable the **Google Sheets API** and **Google Drive API**
3. Create a **Service Account** → download the JSON key file
4. Share your Google Sheet with the service account email (Editor access)
5. Note your **Spreadsheet ID** (in the sheet URL between `/d/` and `/edit`)

You'll need:
- `GOOGLE_SERVICE_ACCOUNT_JSON` — the entire contents of the JSON key file (as a string)
- `GOOGLE_SPREADSHEET_ID` — your spreadsheet ID

### 4. Email (Gmail)

1. Enable 2FA on your Gmail account
2. Go to Google Account → Security → App Passwords
3. Generate an app password for "Mail"

You'll need:
- `EMAIL_SENDER` — your Gmail address
- `EMAIL_PASSWORD` — the app password (not your regular password)
- `EMAIL_RECIPIENT` — where to send the digest (can be the same address)

### 5. GitHub Secrets

In your GitHub repo → Settings → Secrets and variables → Actions, add all of the above:

```
IG_ACCESS_TOKEN
IG_ACCOUNT_ID
ETSY_API_KEY
ETSY_REFRESH_TOKEN
ETSY_SHOP_ID
GOOGLE_SERVICE_ACCOUNT_JSON
GOOGLE_SPREADSHEET_ID
EMAIL_SENDER
EMAIL_PASSWORD
EMAIL_RECIPIENT
GITHUB_TOKEN  ← this one is auto-provided by GitHub Actions, no action needed
```

### 6. Google Sheet tabs

Create a Google Sheet with exactly these tab names:
- `ig_pulse`
- `ig_stars`
- `etsy_stars`
- `etsy_pulse` (manual — script won't touch this one)

The script will write headers on the first run automatically.

## Running locally

```bash
pip install -r requirements.txt

# Copy and fill in your credentials
cp .env.example .env

python src/main.py
```

## Schedule

The pipeline runs every **Monday at 8:00 AM UTC** via GitHub Actions, covering the
previous week (Monday–Sunday). You can also trigger it manually from the Actions tab.
