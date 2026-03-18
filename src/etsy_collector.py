"""
etsy_collector.py — Pulls Etsy shop and listing data via Etsy Open API v3.

Produces one dataset:
  etsy_stars — per-listing metrics for active + auto-renewing listings

What the Etsy API provides:
  - Listing details: title, price, quantity, views (lifetime), num_favorers,
    should_auto_renew, state
  - Orders/revenue: pulled from receipts filtered by listing and date range

What it does NOT provide (stays manual in etsy_pulse):
  - Shop-level traffic stats and traffic sources
  - Conversion rate at account level
  - Shop follows, cities reached
  - Visibility score, search rank (third-party tools only)

OAuth note:
  Etsy uses OAuth 2.0 with short-lived access tokens (1 hour) and long-lived
  refresh tokens. This module exchanges the refresh token for a new access token
  on every run and saves the new refresh token back to GitHub Secrets.
"""

import requests
from datetime import datetime, timedelta
from typing import Any

import config


BASE = config.ETSY_BASE_URL
SHOP_ID = config.ETSY_SHOP_ID


# ---------------------------------------------------------------------------
# OAuth token management
# ---------------------------------------------------------------------------

def get_access_token() -> tuple[str, str]:
    """
    Exchange the stored refresh token for a new access token.
    Returns (access_token, new_refresh_token).
    """
    url = "https://api.etsy.com/v3/public/oauth/token"
    payload = {
        "grant_type": "refresh_token",
        "client_id": config.ETSY_API_KEY,
        "refresh_token": config.ETSY_REFRESH_TOKEN,
    }
    resp = requests.post(url, data=payload)
    resp.raise_for_status()
    data = resp.json()
    return data["access_token"], data["refresh_token"]


def save_refreshed_etsy_token(new_refresh_token: str) -> None:
    """Write the new refresh token back to GitHub Secrets."""
    import base64
    if not config.GITHUB_TOKEN or not config.GITHUB_REPO:
        print("  GITHUB_TOKEN or GITHUB_REPO not set — skipping Etsy token save.")
        return

    headers = {
        "Authorization": f"Bearer {config.GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    pk_url = f"https://api.github.com/repos/{config.GITHUB_REPO}/actions/secrets/public-key"
    pk_resp = requests.get(pk_url, headers=headers)
    pk_resp.raise_for_status()
    pk_data = pk_resp.json()

    try:
        from nacl import encoding, public
        public_key = public.PublicKey(
            pk_data["key"].encode("utf-8"), encoding.Base64Encoder()
        )
        sealed_box = public.SealedBox(public_key)
        encrypted = base64.b64encode(
            sealed_box.encrypt(new_refresh_token.encode("utf-8"))
        ).decode("utf-8")
    except ImportError:
        print("  PyNaCl not installed — cannot save Etsy refresh token. Skipping.")
        return

    secret_url = f"https://api.github.com/repos/{config.GITHUB_REPO}/actions/secrets/ETSY_REFRESH_TOKEN"
    payload = {"encrypted_value": encrypted, "key_id": pk_data["key_id"]}
    put_resp = requests.put(secret_url, headers=headers, json=payload)
    put_resp.raise_for_status()
    print("  Refreshed ETSY_REFRESH_TOKEN saved to GitHub Secrets.")


# ---------------------------------------------------------------------------
# Listing data
# ---------------------------------------------------------------------------

def _get_active_autorenew_listings(access_token: str) -> list[dict]:
    """
    Fetch all active listings with should_auto_renew=True.
    Paginates automatically.
    """
    url = f"{BASE}/shops/{SHOP_ID}/listings/active"
    headers = {
        "x-api-key": config.ETSY_API_KEY,
        "Authorization": f"Bearer {access_token}",
    }
    params = {
        "limit": 100,
        "offset": 0,
        "includes": ["Images"],
        "fields": [
            "listing_id", "title", "price", "quantity",
            "views", "num_favorers", "should_auto_renew",
            "url", "tags", "state",
        ],
    }

    all_listings = []
    while True:
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        all_listings.extend(r for r in results if r.get("should_auto_renew", False))

        count = data.get("count", 0)
        params["offset"] += len(results)
        if params["offset"] >= count or not results:
            break

    print(f"  Found {len(all_listings)} active auto-renewing listings.")
    return all_listings


def _get_listing_orders(
    access_token: str,
    listing_id: int,
    week_start: datetime,
    week_end: datetime,
) -> tuple[int, float]:
    """
    Count orders and sum revenue for a specific listing within the date range.
    Returns (order_count, revenue).

    Note: Etsy receipts API doesn't filter by listing directly — we pull
    shop receipts for the period and filter by listing_id in the line items.
    This is called once and cached; the per-listing lookup is done in memory.
    """
    # This is handled via the cached receipts in collect_etsy_stars
    raise NotImplementedError("Use the cached receipts approach in collect_etsy_stars.")


def _get_shop_receipts(
    access_token: str,
    week_start: datetime,
    week_end: datetime,
) -> list[dict]:
    """
    Fetch all paid receipts (orders) for the shop within the date window.
    """
    url = f"{BASE}/shops/{SHOP_ID}/receipts"
    headers = {
        "x-api-key": config.ETSY_API_KEY,
        "Authorization": f"Bearer {access_token}",
    }
    params = {
        "min_created": int(week_start.timestamp()),
        "max_created": int(week_end.timestamp()),
        "was_paid": True,
        "limit": 100,
        "offset": 0,
    }

    all_receipts = []
    while True:
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        all_receipts.extend(results)
        params["offset"] += len(results)
        if params["offset"] >= data.get("count", 0) or not results:
            break

    return all_receipts


def _build_listing_sales_map(receipts: list[dict]) -> dict[int, dict]:
    """
    From a list of receipts, build a map of listing_id -> {orders, revenue}.
    """
    sales: dict[int, dict] = {}
    for receipt in receipts:
        for transaction in receipt.get("transactions", []):
            lid = transaction.get("listing_id")
            if lid is None:
                continue
            if lid not in sales:
                sales[lid] = {"orders": 0, "revenue": 0.0}
            sales[lid]["orders"] += transaction.get("quantity", 1)
            # price is in micro-units (e.g. 1500 = $15.00) in some API versions
            # or as a dict with amount/divisor — handle both
            price = transaction.get("price", {})
            if isinstance(price, dict):
                amount = price.get("amount", 0)
                divisor = price.get("divisor", 100)
                sales[lid]["revenue"] += (amount / divisor) * transaction.get("quantity", 1)
            else:
                sales[lid]["revenue"] += float(price) * transaction.get("quantity", 1)
    return sales


# ---------------------------------------------------------------------------
# Main collector
# ---------------------------------------------------------------------------

def collect_etsy_stars(
    week_start: datetime, week_end: datetime
) -> list[dict[str, Any]]:
    """
    Collect per-listing metrics for etsy_stars tab.
    Returns a list of row dicts, one per active auto-renewing listing.
    """
    print("  Fetching Etsy OAuth token...")
    access_token, new_refresh_token = get_access_token()
    save_refreshed_etsy_token(new_refresh_token)

    print("  Fetching active auto-renewing listings...")
    listings = _get_active_autorenew_listings(access_token)

    print("  Fetching shop receipts for the week...")
    receipts = _get_shop_receipts(access_token, week_start, week_end)
    sales_map = _build_listing_sales_map(receipts)

    rows = []
    for listing in listings:
        lid = listing["listing_id"]
        sales = sales_map.get(lid, {"orders": 0, "revenue": 0.0})
        orders = sales["orders"]
        revenue = round(sales["revenue"], 2)
        views = listing.get("views", 0)
        favorites = listing.get("num_favorers", 0)

        # Price formatting
        price_data = listing.get("price", {})
        if isinstance(price_data, dict):
            price = price_data.get("amount", 0) / price_data.get("divisor", 100)
        else:
            price = float(price_data or 0)

        # CR% = orders / views (lifetime, not just this week — weekly views not available)
        cr_pct = round(orders / views * 100, 2) if views else None

        rows.append({
            "week_end_date": week_end.strftime("%Y-%m-%d"),
            "listing_id": lid,
            "listing_name": listing.get("title", ""),
            "listing_url": listing.get("url", ""),
            "price": round(price, 2),
            "quantity_available": listing.get("quantity", 0),
            "lifetime_views": views,
            "lifetime_favorites": favorites,
            "weekly_orders": orders,
            "weekly_revenue": revenue,
            "weekly_cr_pct": cr_pct,
        })

    return rows


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

ETSY_STARS_HEADERS = [
    "week_end_date",
    "listing_id",
    "listing_name",
    "listing_url",
    "price",
    "quantity_available",
    "lifetime_views",
    "lifetime_favorites",
    "weekly_orders",
    "weekly_revenue",
    "weekly_cr_pct",
]


def row_to_list(data: dict, headers: list[str]) -> list[Any]:
    return [data.get(h) for h in headers]
