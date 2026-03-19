# Maintenance Guide

This document covers ongoing maintenance, credential rotation, troubleshooting,
and how to update the pipeline as your needs change.

---

## Regular maintenance (what needs attention over time)

### Instagram access token
**Expires:** 60 days from generation
**Action needed:** None — the pipeline auto-refreshes the token on every run and
writes the new token back to GitHub Secrets. As long as the pipeline runs at least
once every 60 days, the token will never expire.

If the token does expire (e.g. the pipeline was paused for 60+ days):
1. Re-run `scripts/ig_auth.py` locally to get a fresh token
2. Update the `IG_ACCESS_TOKEN` GitHub Secret manually
3. Trigger the pipeline manually to confirm it works

### Etsy refresh token
**Expires:** Never (Etsy refresh tokens are long-lived)
**Action needed:** None — the pipeline auto-exchanges the refresh token for a new
access token and new refresh token on every run, saving both back to GitHub Secrets.

### Google service account JSON
**Expires:** Never (unless you manually revoke it in Google Cloud)
**Action needed:** None

### Gmail App Password
**Expires:** Never (unless you revoke it or change your Google password)
**Action needed:** None

### Gemini API key
**Expires:** Never
**Action needed:** None — but monitor your Google AI Studio usage if on free tier

---

## Enabling Etsy once API is approved

1. Run `python scripts/etsy_auth.py` locally — it will print your refresh token and shop ID
2. Add these three secrets to GitHub (Settings → Secrets → Actions):
   - `ETSY_API_KEY`
   - `ETSY_REFRESH_TOKEN`
   - `ETSY_SHOP_ID`
3. Edit `.github/workflows/weekly_pipeline.yml`:
   - Find the line: `run: python src/main.py --skip-etsy`
   - Change it to: `run: python src/main.py`
4. Commit and push
5. Trigger the workflow manually from the Actions tab to test

---

## Changing the schedule

Edit `.github/workflows/weekly_pipeline.yml`:
```yaml
schedule:
  - cron: "0 8 * * 1"   # currently Monday 8AM UTC = 1AM Mountain
```

Cron format: `minute hour day month weekday`

Common alternatives:
- Monday 9AM Mountain (summer/MDT): `0 15 * * 1`
- Monday 9AM Mountain (winter/MST): `0 16 * * 1`
- Sunday evening instead: `0 22 * * 0`

Commit and push after changing — GitHub picks it up automatically.

---

## Changing which Etsy listings are tracked

Currently tracks: active listings with `should_auto_renew = True`

**To track all active listings** (once product phase-out is complete):
In `src/etsy_collector.py`, find `_get_active_autorenew_listings()` and change:
```python
all_listings.extend(r for r in results if r.get("should_auto_renew", False))
```
to:
```python
all_listings.extend(results)
```

---

## Updating the AI insights prompt

The prompt that drives the weekly insights lives in `src/email_digest.py`
in the `_get_ai_insights()` function. Edit the `prompt` variable directly.

Key things the prompt currently knows:
- Primary goal is follower growth
- Watch time diagnostic rules (< 3s = hook problem, not CTA problem)
- Instagram algorithm signals (saves/shares > likes)
- Hook techniques for low watch time

To change the tone, add context about your niche, or adjust the format,
edit the prompt and redeploy.

---

## Adding historical data to the sheet

You can manually paste historical data into any tab and the pipeline will
respect it — it skips rows that already exist (by `week_end_date` for pulse tabs,
by `permalink` for `ig_stars`, by `week_end_date` for `etsy_stars`).

For `etsy_stars` historical data: the `weekly_views` and `weekly_favorites`
delta columns will be `None` for the oldest row you add (no previous week to
compare against). This is expected.

---

## Troubleshooting common errors

### `400 Client Error` on Instagram insights
Usually means a metric name has been deprecated by Meta.
Check [developers.facebook.com/docs/instagram-platform/changelog](https://developers.facebook.com/docs/instagram-platform/changelog)
for recent deprecations and update the metric names in `src/ig_collector.py`.

### `401 Unauthorized` on Instagram
Your access token has expired. Re-run `scripts/ig_auth.py` and update
the `IG_ACCESS_TOKEN` GitHub Secret.

### `Tab 'X' not found in spreadsheet`
The Google Sheet tab name doesn't match what the code expects.
Tab names are case-sensitive. Check `src/config.py` for the expected names:
- `SHEET_IG_PULSE = "ig_pulse"`
- `SHEET_IG_STARS = "ig_stars"`
- `SHEET_ETSY_STARS = "etsy_stars"`

### `GOOGLE_SERVICE_ACCOUNT_JSON` errors locally
Make sure your `.env` points to the correct file path, e.g.:
```
GOOGLE_SERVICE_ACCOUNT_JSON=service_account.json
```
And that the file exists in your repo root (it's gitignored so won't be committed).

### Email not arriving
1. Check your spam folder
2. Verify your Gmail App Password is correct (no spaces)
3. Make sure 2-Step Verification is still enabled on your Google account —
   disabling it invalidates all App Passwords

### AI insights section missing from email
The pipeline treats Gemini failures as non-fatal — the email sends without insights.
Check the GitHub Actions logs for a line like:
`Warning: AI insights unavailable: ...`
Common causes: rate limit (429), invalid API key, or model name changed.
Current model: `gemini-2.5-flash`

### Etsy `401` or token errors
The refresh token may have been invalidated. Re-run `scripts/etsy_auth.py`
and update the `ETSY_REFRESH_TOKEN` GitHub Secret.

---

## Manually triggering the pipeline

Go to your GitHub repo → **Actions → Weekly Analytics Pipeline → Run workflow → Run workflow**

Useful for:
- Testing after code changes
- Backfilling a missed week
- Verifying credentials after rotation

Note: if the week's data already exists in the sheet, the pipeline will skip
writing it again (upsert logic). Delete the relevant rows first if you need to
force a rewrite.

---

## Viewing pipeline logs

Go to **Actions → Weekly Analytics Pipeline** → click a run → expand
**"Run analytics pipeline"** to see the full output including any warnings.

---

## Updating dependencies

```bash
pip install --upgrade -r requirements.txt
```

Then test locally before pushing. Key packages to watch for breaking changes:
- `gspread` — Google Sheets client
- `requests` — HTTP client used for all API calls
