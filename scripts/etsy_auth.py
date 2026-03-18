"""
etsy_auth.py — One-time script to complete Etsy OAuth 2.0 and get your refresh token.

Run this ONCE locally before setting up GitHub Actions.
It will print your refresh token which you then add to GitHub Secrets as ETSY_REFRESH_TOKEN.

Usage:
    python scripts/etsy_auth.py

You'll need:
    - ETSY_API_KEY set in your .env file
    - A redirect URI of http://localhost:3003/callback registered in your Etsy app settings
"""

import os
import sys
import hashlib
import base64
import secrets
import urllib.parse
import http.server
import threading
import webbrowser
import requests
from dotenv import load_dotenv

load_dotenv()

ETSY_API_KEY = os.getenv("ETSY_API_KEY")
if not ETSY_API_KEY:
    sys.exit("Error: ETSY_API_KEY not set in .env")

REDIRECT_URI = "http://localhost:3003/callback"
SCOPES = "transactions_r listings_r shops_r"

# PKCE
code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
code_challenge = base64.urlsafe_b64encode(
    hashlib.sha256(code_verifier.encode()).digest()
).rstrip(b"=").decode()

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
            self.wfile.write(b"<h2>Auth successful! You can close this tab.</h2>")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"<h2>No code found in callback.</h2>")
        server_done.set()

    def log_message(self, *args):
        pass  # suppress request logs


def run():
    auth_url = (
        "https://www.etsy.com/oauth/connect"
        f"?response_type=code"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&scope={urllib.parse.quote(SCOPES)}"
        f"&client_id={ETSY_API_KEY}"
        f"&state=etsy_auth"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
    )

    print("\nOpening Etsy auth page in your browser...")
    print(f"If it doesn't open, visit:\n  {auth_url}\n")
    webbrowser.open(auth_url)

    server = http.server.HTTPServer(("localhost", 3003), CallbackHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()

    print("Waiting for Etsy to redirect back to localhost:3003...")
    server_done.wait(timeout=120)
    server.shutdown()

    if not auth_code_holder:
        sys.exit("Error: No auth code received. Did you complete the Etsy login?")

    auth_code = auth_code_holder[0]
    print(f"\nAuth code received. Exchanging for tokens...")

    resp = requests.post(
        "https://api.etsy.com/v3/public/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": ETSY_API_KEY,
            "redirect_uri": REDIRECT_URI,
            "code": auth_code,
            "code_verifier": code_verifier,
        },
    )
    resp.raise_for_status()
    tokens = resp.json()

    print("\n" + "=" * 55)
    print("SUCCESS! Add these to your GitHub Secrets and .env file:")
    print("=" * 55)
    print(f"\nETSY_REFRESH_TOKEN={tokens['refresh_token']}\n")
    print("(Your access token expires in 1 hour — the pipeline auto-refreshes it.)")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    run()