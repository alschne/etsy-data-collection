# Setup Guide

This document covers the complete first-time setup for the Etsy + Instagram analytics pipeline.
Follow the steps in order — some steps depend on earlier ones.

---

## Prerequisites

- Python 3.11+
- A Facebook account that administers your Facebook Page
- Your Instagram Business account linked to a Facebook Page
- An Etsy seller account
- A Gmail account with 2-Step Verification enabled
- A GitHub account

---

## Step 1 — Meta Developer App (Instagram API)

This is the most involved step. Budget 30-45 minutes.

### 1.1 Create a Meta Developer account
1. Go to [developers.facebook.com](https://developers.facebook.com) and log in with your **personal Facebook account** (the one that manages your Facebook Page)
2. Click "Get Started" if it's your first time

### 1.2 Create an app
1. Click **My Apps → Create App**
2. When asked for a use case, select **"Other"** (being phased out — if gone, select "Authenticate and request data from users")
3. App type: **Business**
4. Name it anything (e.g. "Analytics Pipeline"), enter your email → Create App

### 1.3 Add Instagram product
1. In your app dashboard, find **Add Products**
2. Find **Instagram** → click **Set Up**
3. In the left sidebar you'll now see Instagram

### 1.4 Add yourself as an Instagram Tester
1. Go to **App Roles → Roles → Instagram Testers**
2. Add your Instagram account as a tester
3. Accept the invite at **instagram.com/accounts/manage_access/** (not in Settings — this specific URL)

### 1.5 Add a redirect URI
1. Go to **Instagram → API Setup with Instagram Login**
2. Scroll to **Set up Instagram business login**
3. Add redirect URI: `https://localhost/`
4. Save

### 1.6 Generate your access token (manual OAuth flow)

Open this URL in your browser (replace `YOUR_APP_ID`):
```
https://api.instagram.com/oauth/authorize?client_id=YOUR_APP_ID&redirect_uri=https://localhost/&scope=instagram_business_basic,instagram_business_manage_insights&response_type=code
```

Log in with Instagram. You'll be redirected to a URL like:
```
https://localhost/?code=AQXXXXXX...#_
```

Copy everything between `?code=` and `#_`. Then run:

```bash
curl -X POST "https://api.instagram.com/oauth/access_token" \
  -d "client_id=YOUR_APP_ID" \
  -d "client_secret=YOUR_APP_SECRET" \
  -d "grant_type=authorization_code" \
  -d "redirect_uri=https://localhost/" \
  -d "code=YOUR_CODE"
```

This returns a short-lived token. Exchange it for a 60-day token:

```bash
curl "https://graph.instagram.com/access_token?grant_type=ig_exchange_token&client_secret=YOUR_APP_SECRET&access_token=YOUR_SHORT_LIVED_TOKEN"
```

Save the long-lived token as `IG_ACCESS_TOKEN`.

### 1.7 Get your Instagram Account ID

```bash
curl "https://graph.instagram.com/me?fields=id,username&access_token=YOUR_LONG_LIVED_TOKEN"
```

Save the `id` as `IG_ACCOUNT_ID`.

> ⚠️ **Token expiry:** Long-lived tokens last 60 days. The pipeline auto-refreshes the token
> on every run, so as long as the pipeline runs at least once every 60 days it will never expire.

---

## Step 2 — Etsy API

### 2.1 Create an Etsy Developer app
1. Go to [etsy.com/developers](https://www.etsy.com/developers) → **Create a New App**
2. Fill in the app details — for keystring and shared secret purposes, the details don't matter much for a private app
3. Submit and wait for API access approval (can take a few days)
4. Once approved, note your **Keystring** — this is your `ETSY_API_KEY`

> If you already have an Etsy app from another project, you can reuse it — one app can handle multiple use cases as long as it's just you using it.

### 2.2 Find your Shop ID
Run this once your API is approved (replace with your shop name and API key):
```bash
curl "https://openapi.etsy.com/v3/application/shops?shop_name=YOURSHOPNAME" \
  -H "x-api-key: YOUR_ETSY_API_KEY"
```
The numeric `shop_id` in the response is your `ETSY_SHOP_ID`.

### 2.3 Complete OAuth to get your refresh token
Run the one-time auth script:
```bash
python scripts/etsy_auth.py
```
This opens a browser, you log into Etsy and authorize, and it prints your `ETSY_REFRESH_TOKEN`.
Save it — you won't see it again (though you can always re-run the script to get a new one).

> The Etsy refresh token is long-lived. The pipeline auto-exchanges it for a new access token
> and refresh token on every run and saves the new refresh token back to GitHub Secrets.

---

## Step 3 — Google Cloud (Sheets access)

### 3.1 Create a project
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Click the project dropdown → **New Project** → name it anything → Create
3. Make sure your new project is selected

### 3.2 Enable APIs
1. Search **"Google Sheets API"** → Enable
2. Search **"Google Drive API"** → Enable

### 3.3 Create a Service Account
1. Go to **APIs & Services → Credentials**
2. Click **+ Create Credentials → Service Account**
3. Name it (e.g. "sheets-writer") → **Create and Continue**
4. Skip the role and user access steps → **Done**

### 3.4 Download the JSON key
1. Click your new service account in the list
2. Go to **Keys** tab → **Add Key → Create New Key → JSON → Create**
3. A JSON file downloads — keep it safe, don't commit it to git

### 3.5 Share your Google Sheet
1. Open the JSON file and find the `client_email` field
   (looks like `something@yourproject.iam.gserviceaccount.com`)
2. Share your Google Sheet with that email address, giving it **Editor** access

### 3.6 Get your Spreadsheet ID
It's the long string in your Sheet URL between `/d/` and `/edit`.

### 3.7 Local .env setup
In your `.env` file you can reference the JSON file by path:
```
GOOGLE_SERVICE_ACCOUNT_JSON=path/to/service_account.json
```
For GitHub Secrets, paste the entire JSON file contents as a single string.

---

## Step 4 — Gmail App Password

1. Go to [myaccount.google.com](https://myaccount.google.com) → **Security**
2. Confirm **2-Step Verification is ON**
3. Search **"App Passwords"** in the search bar → click the result
4. App name: type anything (e.g. "Analytics Pipeline") → **Create**
5. Copy the 16-character password immediately — remove spaces before saving

Your `.env`:
```
EMAIL_SENDER=you@gmail.com
EMAIL_PASSWORD=xxxxxxxxxxxxxxxx   # 16 chars, no spaces
EMAIL_RECIPIENT=you@gmail.com     # can be any email
```

---

## Step 5 — Google AI Studio (Gemini insights)

1. Go to [aistudio.google.com](https://aistudio.google.com) → **Get API Key**
2. Create a key → copy it
3. Save as `GOOGLE_AI_API_KEY`

---

## Step 6 — Google Sheet tabs

Create a Google Sheet with exactly these four tab names (case-sensitive):
- `ig_pulse`
- `ig_stars`
- `etsy_stars`
- `etsy_pulse` (manual — pipeline doesn't write to this one)

The pipeline writes headers automatically on the first run.

---

## Step 7 — GitHub Setup

### 7.1 Create the repo
1. Go to [github.com](https://github.com) → **New repository**
2. Name it, set to **Private**, do NOT initialize with README → **Create**

### 7.2 Push the code
```bash
cd your-repo-folder
git init
git add .
git commit -m "Initial pipeline setup"
git branch -M main
git remote add origin https://github.com/YOURUSERNAME/YOURREPO.git
git push -u origin main
```

### 7.3 Add GitHub Secrets
Go to your repo → **Settings → Secrets and variables → Actions → New repository secret**

Add all of these:
```
IG_APP_ID
IG_APP_SECRET
IG_ACCESS_TOKEN
IG_ACCOUNT_ID
ETSY_API_KEY          ← add when Etsy API is approved
ETSY_REFRESH_TOKEN    ← add when Etsy API is approved
ETSY_SHOP_ID          ← add when Etsy API is approved
GOOGLE_SERVICE_ACCOUNT_JSON   ← paste entire JSON file contents
GOOGLE_SPREADSHEET_ID
EMAIL_SENDER
EMAIL_PASSWORD
EMAIL_RECIPIENT
GOOGLE_AI_API_KEY
```

> `GITHUB_TOKEN` is automatically provided by GitHub Actions — do not add it manually.

### 7.4 Set up the workflow file
Make sure `weekly_pipeline.yml` is in `.github/workflows/` (not loose in the repo root).

### 7.5 Test manually
Go to **Actions → Weekly Analytics Pipeline → Run workflow → Run workflow**
Watch the logs. If anything fails, the error message will tell you exactly which step.

---

## Step 8 — Enable Etsy once API is approved

When your Etsy API access is approved:
1. Run `python scripts/etsy_auth.py` to get your refresh token
2. Find your shop ID (see Step 2.2)
3. Add `ETSY_API_KEY`, `ETSY_REFRESH_TOKEN`, `ETSY_SHOP_ID` to GitHub Secrets
4. Edit `.github/workflows/weekly_pipeline.yml` — remove `--skip-etsy` from the run command
5. Commit and push
6. Trigger the workflow manually to test with Etsy enabled
