# Etsy + Instagram Analytics Pipeline

Automated weekly data collection for your Etsy shop and connected Instagram account.
Pulls data from the Instagram Graph API and Etsy Open API v3, appends to Google Sheets,
and sends a weekly email digest with AI-generated insights.

## What this does

**Every Monday at 8AM UTC** the weekly pipeline:
1. Pulls last week's Instagram account metrics → writes to `ig_pulse` tab
2. Pulls per-post metrics for posts published last week → writes to `ig_stars` tab
3. Pulls per-listing sales data for active auto-renewing Etsy listings → writes to `etsy_stars` tab
4. Sends a weekly email digest with metrics, week-over-week comparisons, and AI-generated insights

**Quarterly and annually** the review pipeline:
- **March 31** — Q1 review email (Jan–Mar)
- **June 30** — Q2 review email (Apr–Jun)
- **September 30** — Q3 review email (Jul–Sep)
- **December 31** — Q4 review email (Oct–Dec) + Annual review email (full year)

Review emails include aggregated totals, top performing posts, Etsy summary, and AI-generated strategic insights.

## Repo structure

```
.
├── .github/
│   └── workflows/
│       └── weekly_pipeline.yml   # GitHub Actions — weekly + quarterly + annual schedules
├── src/
│   ├── main.py                   # Entry point — weekly pipeline
│   ├── review_runner.py          # Entry point — quarterly and annual reviews
│   ├── ig_collector.py           # Instagram Graph API logic
│   ├── etsy_collector.py         # Etsy Open API v3 logic
│   ├── sheets.py                 # Google Sheets read/write helpers
│   ├── email_digest.py           # Weekly email with AI insights (Gemini)
│   ├── review_digest.py          # Quarterly and annual review emails
│   └── config.py                 # Centralised config — reads from env vars
├── scripts/
│   ├── ig_auth.py                # One-time Instagram OAuth setup
│   └── etsy_auth.py              # One-time Etsy OAuth setup
├── requirements.txt
├── .env.example
├── README.md
├── SETUP.md                      # Step-by-step first-time setup guide
└── MAINTENANCE.md                # Ongoing maintenance and troubleshooting
```

## Tabs automated vs manual

| Tab | Source | Cadence | Status |
|-----|--------|---------|--------|
| `ig_pulse` | Instagram Graph API | Weekly (Monday) | ✅ Automated |
| `ig_stars` | Instagram Graph API | Weekly (new posts only) | ✅ Automated |
| `etsy_stars` | Etsy Open API v3 | Weekly | ✅ Automated |
| `etsy_pulse` | Manual | Monthly | ✋ Manual — Etsy doesn't expose shop-level stats via API |

## Quick reference — credentials needed

| Secret | Where to get it |
|--------|----------------|
| `IG_APP_ID` | Meta Dashboard → Instagram → API Setup |
| `IG_APP_SECRET` | Meta Dashboard → Instagram → API Setup |
| `IG_ACCESS_TOKEN` | Run `scripts/ig_auth.py` |
| `IG_ACCOUNT_ID` | Output of `scripts/ig_auth.py` |
| `ETSY_API_KEY` | Etsy Developer Portal → your app |
| `ETSY_REFRESH_TOKEN` | Run `scripts/etsy_auth.py` |
| `ETSY_SHOP_ID` | Output of `scripts/etsy_auth.py` |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Google Cloud → Service Account → JSON key |
| `GOOGLE_SPREADSHEET_ID` | Google Sheet URL between `/d/` and `/edit` |
| `EMAIL_SENDER` | Your Gmail address |
| `EMAIL_PASSWORD` | Gmail App Password (16 chars, no spaces) |
| `EMAIL_RECIPIENT` | Where to send the digest |
| `GOOGLE_AI_API_KEY` | Google AI Studio |

## Running locally

```bash
pip install -r requirements.txt
cp .env.example .env
# fill in .env with your credentials

python src/main.py              # full pipeline
python src/main.py --skip-etsy  # skip Etsy (use while waiting for API approval)
```

## Schedule

Runs every **Monday at 8:00 AM UTC** (1:00 AM Mountain Time).
To change the time, edit the cron in `.github/workflows/weekly_pipeline.yml`.

See `SETUP.md` for first-time setup and `MAINTENANCE.md` for ongoing maintenance.