"""
ig_auth.py — One-time script to get a proper long-lived Instagram access token.

The token generated in the Meta dashboard can't be exchanged for a long-lived
token. This script does the full OAuth flow correctly:
  1. Opens Instagram login in your browser
  2. Catches the redirect on localhost
  3. Exchanges the code for a short-lived token
  4. Exchanges that for a long-lived token (60 days)
  5. Prints your token and account ID

Run once per Instagram account. Add the results to your .env and GitHub Secrets.

Usage:
    python scripts/ig_auth.py

You'll need in your .env:
    IG_APP_ID       — your Instagram App ID (from Meta dashboard > Instagram > API Setup)
    IG_APP_SECRET   — your Instagram App Secret (same page)

You'll also need a redirect URI registered in your app:
    Go to Meta dashboard > Instagram > API Setup with Instagram Login
    Under "Instagram App Settings", add this redirect URI:
        https://localhost/
"""

import os
import sys
import http.server
import threading
import webbrowser
import urllib.parse
import requests
from dotenv import load_dotenv

load_dotenv()

APP_ID = os.getenv("IG_APP_ID")
APP_SECRET = os.getenv("IG_APP_SECRET")

if not APP_ID or not APP_SECRET:
    sys.exit(
        "Error: IG_APP_ID and IG_APP_SECRET must be set in your .env file.\n"
        "Find them at: Meta Dashboard > Instagram > API Setup with Instagram Login"
    )

REDIRECT_URI = "http://localhost:8888/callback"
SCOPE = "instagram_business_basic,instagram_business_manage_insights"

auth_code_holder = []
server_done = threading.Event()


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        if code:
            auth_code_holder.append(code)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<h2>Success! You can close this tab and go back to your terminal.</h2>")
        else:
            self.send_response(400)
            self.end_headers()
            error = params.get("error_description", ["Unknown error"])[0]
            self.wfile.write(f"<h2>Error: {error}</h2>".encode())
        server_done.set()

    def log_message(self, *args):
        pass


def run():
    # Step 1 — build auth URL
    auth_url = (
        "https://api.instagram.com/oauth/authorize"
        f"?client_id={APP_ID}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&scope={SCOPE}"
        f"&response_type=code"
    )

    print("\n" + "="*55)
    print("  Instagram OAuth — one-time setup")
    print("="*55)
    print("\nMake sure you've added this redirect URI in your Meta app:")
    print(f"  {REDIRECT_URI}")
    print("\nMeta Dashboard > Instagram > API Setup with Instagram Login")
    print("> Instagram App Settings > add to 'Redirect URIs'\n")
    input("Press Enter when the redirect URI is added and you're ready...")

    # Step 2 — start local server to catch redirect
    server = http.server.HTTPServer(("localhost", 8888), CallbackHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()

    print("\nOpening Instagram login in your browser...")
    webbrowser.open(auth_url)
    print("Log in and authorize the app. Waiting for redirect...\n")

    server_done.wait(timeout=120)
    server.shutdown()

    if not auth_code_holder:
        sys.exit("No auth code received. Did you complete the Instagram login?")

    code = auth_code_holder[0]
    # Instagram appends #_ to the code sometimes — strip it
    code = code.split("#")[0]

    # Step 3 — exchange code for short-lived token
    print("Exchanging code for short-lived token...")
    resp = requests.post(
        "https://api.instagram.com/oauth/access_token",
        data={
            "client_id": APP_ID,
            "client_secret": APP_SECRET,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
            "code": code,
        },
    )
    resp.raise_for_status()
    short_lived = resp.json()
    short_token = short_lived["access_token"]
    user_id = short_lived["user_id"]
    print(f"  Got short-lived token for user ID: {user_id}")

    # Step 4 — exchange for long-lived token (60 days)
    print("Exchanging for long-lived token...")
    resp2 = requests.get(
        "https://graph.instagram.com/access_token",
        params={
            "grant_type": "ig_exchange_token",
            "client_secret": APP_SECRET,
            "access_token": short_token,
        },
    )
    resp2.raise_for_status()
    long_lived = resp2.json()
    long_token = long_lived["access_token"]
    expires_in = long_lived.get("expires_in", 5184000)
    expires_days = expires_in // 86400

    # Step 5 — get username to confirm correct account
    resp3 = requests.get(
        "https://graph.instagram.com/me",
        params={"fields": "id,username", "access_token": long_token},
    )
    resp3.raise_for_status()
    account = resp3.json()

    print("\n" + "="*55)
    print("  SUCCESS!")
    print("="*55)
    print(f"\n  Instagram account : @{account.get('username')}")
    print(f"  Account ID        : {account.get('id')}")
    print(f"  Token expires in  : {expires_days} days")
    print(f"\nAdd these to your .env and GitHub Secrets:")
    print(f"\n  IG_ACCESS_TOKEN={long_token}")
    print(f"  IG_ACCOUNT_ID={account.get('id')}")
    print("\n" + "="*55 + "\n")


if __name__ == "__main__":
    run()
