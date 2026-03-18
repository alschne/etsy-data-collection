"""
ig_collector.py — Pulls Instagram Business account data via the Graph API.

Produces two datasets:
  1. ig_pulse  — weekly account-level metrics (one row per week)
  2. ig_stars  — per-post metrics for posts published in the collection window

Instagram Graph API notes:
  - Account insights (reach, impressions, etc.) are returned as daily metrics.
    We aggregate them over the week window.
  - Follower count is a point-in-time snapshot taken at run time.
  - Per-post metrics are lifetime totals. For "this week's posts" we filter
    by posts with a timestamp within the week window.
  - Percentage breakdowns are calculated here from raw counts — the API does
    not return pre-calculated percentages.
  - Reel-specific fields (avg_watch_time, ig_reels_avg_watch_time) are only
    populated when the media_type is VIDEO/REEL.
"""

import requests
from datetime import datetime, timedelta, timezone
from typing import Any

import config


BASE = config.IG_BASE_URL
TOKEN = config.IG_ACCESS_TOKEN
ACCOUNT_ID = config.IG_ACCOUNT_ID


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------

def refresh_access_token() -> str:
    """
    Refresh a long-lived Instagram access token. Long-lived tokens are valid
    for 60 days and can be refreshed any time they have more than a few days
    remaining. Call this on every run to keep the token alive indefinitely.
    """
    url = f"{BASE}/oauth/access_token"
    params = {
        "grant_type": "ig_refresh_token",
        "access_token": TOKEN,
    }
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    new_token = resp.json()["access_token"]
    print(f"  IG token refreshed. Expires in {resp.json().get('expires_in', '?')}s")
    return new_token


def save_refreshed_token(new_token: str) -> None:
    """Write the refreshed token back to GitHub Secrets so it persists."""
    import base64, json
    if not config.GITHUB_TOKEN or not config.GITHUB_REPO:
        print("  GITHUB_TOKEN or GITHUB_REPO not set — skipping token save.")
        return

    # Get the repo's public key for secret encryption
    headers = {
        "Authorization": f"Bearer {config.GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    pk_url = f"https://api.github.com/repos/{config.GITHUB_REPO}/actions/secrets/public-key"
    pk_resp = requests.get(pk_url, headers=headers)
    pk_resp.raise_for_status()
    pk_data = pk_resp.json()

    # Encrypt the secret value using PyNaCl
    try:
        from nacl import encoding, public
        public_key = public.PublicKey(pk_data["key"].encode("utf-8"), encoding.Base64Encoder())
        sealed_box = public.SealedBox(public_key)
        encrypted = base64.b64encode(sealed_box.encrypt(new_token.encode("utf-8"))).decode("utf-8")
    except ImportError:
        print("  PyNaCl not installed — cannot encrypt token for GitHub Secrets. Skipping.")
        return

    secret_url = f"https://api.github.com/repos/{config.GITHUB_REPO}/actions/secrets/IG_ACCESS_TOKEN"
    payload = {"encrypted_value": encrypted, "key_id": pk_data["key_id"]}
    put_resp = requests.put(secret_url, headers=headers, json=payload)
    put_resp.raise_for_status()
    print("  Refreshed IG_ACCESS_TOKEN saved to GitHub Secrets.")


# ---------------------------------------------------------------------------
# Account-level insights (ig_pulse)
# ---------------------------------------------------------------------------

def _get_account_insights(since: datetime, until: datetime) -> dict[str, Any]:
    """
    Fetch daily account insights and aggregate over the date range.
    Returns a flat dict of metric_name -> value.
    """
    metrics = [
        "reach",
        "impressions",
        "profile_views",
        "website_clicks",
        "follower_count",
    ]

    url = f"{BASE}/{ACCOUNT_ID}/insights"
    params = {
        "metric": ",".join(metrics),
        "period": "day",
        "since": int(since.timestamp()),
        "until": int(until.timestamp()),
        "access_token": TOKEN,
    }

    resp = requests.get(url, params=params)
    resp.raise_for_status()
    data = resp.json().get("data", [])

    aggregated: dict[str, int] = {}
    for metric_obj in data:
        name = metric_obj["name"]
        total = sum(v["value"] for v in metric_obj.get("values", []))
        aggregated[name] = total

    return aggregated


def _get_follower_count() -> int:
    """Point-in-time follower count."""
    url = f"{BASE}/{ACCOUNT_ID}"
    params = {
        "fields": "followers_count",
        "access_token": TOKEN,
    }
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    return resp.json().get("followers_count", 0)


def collect_ig_pulse(week_start: datetime, week_end: datetime) -> dict[str, Any]:
    """
    Collect weekly account-level metrics for ig_pulse tab.
    week_end is the Sunday that closes the week (inclusive).
    """
    print("  Fetching IG account insights...")
    insights = _get_account_insights(week_start, week_end)
    followers = _get_follower_count()

    # Fetch post-type breakdown for the week
    post_metrics = _get_content_type_breakdown(week_start, week_end)

    reach = insights.get("reach", 0)
    impressions = insights.get("impressions", 0)
    interactions = post_metrics.get("total_interactions", 0)
    post_interactions = post_metrics.get("post_interactions", 0)
    reel_interactions = post_metrics.get("reel_interactions", 0)
    post_views = post_metrics.get("post_views", 0)
    reel_views = post_metrics.get("reel_views", 0)
    total_views = post_views + reel_views

    def pct(part, whole):
        return round(part / whole * 100, 1) if whole else None

    return {
        "week_end_date": week_end.strftime("%Y-%m-%d"),
        "account_reach": reach,
        "impressions": impressions,
        "followers": followers,
        "profile_visits": insights.get("profile_views", 0),
        "external_link_taps": insights.get("website_clicks", 0),
        # Views breakdown
        "views_from_posts": post_views,
        "views_from_reels": reel_views,
        "pct_views_from_posts": pct(post_views, total_views),
        "pct_views_from_reels": pct(reel_views, total_views),
        # Interactions breakdown
        "total_interactions": interactions,
        "interactions_from_posts": post_interactions,
        "interactions_from_reels": reel_interactions,
        "pct_interactions_from_posts": pct(post_interactions, interactions),
        "pct_interactions_from_reels": pct(reel_interactions, interactions),
        # Individual interaction types (summed from post-level)
        "likes": post_metrics.get("likes", 0),
        "comments": post_metrics.get("comments", 0),
        "saves": post_metrics.get("saves", 0),
        "shares": post_metrics.get("shares", 0),
    }


def _get_content_type_breakdown(
    week_start: datetime, week_end: datetime
) -> dict[str, int]:
    """
    Fetch all posts published this week and sum their metrics by content type.
    Used to build the posts vs reels breakdown in ig_pulse.
    """
    posts = _get_media_in_window(week_start, week_end)

    totals = {
        "total_interactions": 0,
        "post_interactions": 0,
        "reel_interactions": 0,
        "post_views": 0,
        "reel_views": 0,
        "likes": 0,
        "comments": 0,
        "saves": 0,
        "shares": 0,
    }

    for post in posts:
        is_reel = post.get("media_type") in ("VIDEO", "REEL") or post.get(
            "media_product_type"
        ) == "REELS"
        metrics = post.get("_metrics", {})

        likes = metrics.get("like_count", 0)
        comments = metrics.get("comments_count", 0)
        saves = metrics.get("saved", 0)
        shares = metrics.get("shares", 0)
        views = metrics.get("impressions", 0) or metrics.get("video_views", 0)
        interactions = likes + comments + saves + shares

        totals["likes"] += likes
        totals["comments"] += comments
        totals["saves"] += saves
        totals["shares"] += shares
        totals["total_interactions"] += interactions

        if is_reel:
            totals["reel_interactions"] += interactions
            totals["reel_views"] += views
        else:
            totals["post_interactions"] += interactions
            totals["post_views"] += views

    return totals


# ---------------------------------------------------------------------------
# Per-post metrics (ig_stars)
# ---------------------------------------------------------------------------

def _get_media_in_window(
    week_start: datetime, week_end: datetime
) -> list[dict[str, Any]]:
    """
    Return all media objects published between week_start and week_end,
    with their metrics pre-fetched and attached as '_metrics'.
    """
    url = f"{BASE}/{ACCOUNT_ID}/media"
    params = {
        "fields": "id,timestamp,media_type,media_product_type,permalink",
        "access_token": TOKEN,
        "limit": 50,
    }

    all_media = []
    while url:
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        page = resp.json()
        for item in page.get("data", []):
            ts = datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00"))
            if week_start <= ts <= week_end:
                all_media.append(item)
            elif ts < week_start:
                # Media is sorted newest-first; once we're past the window, stop
                url = None
                break
        else:
            url = page.get("paging", {}).get("next")
            params = {}  # next URL already has params baked in
            continue
        break

    # Fetch metrics for each post
    for item in all_media:
        item["_metrics"] = _get_post_metrics(item["id"], item)

    return all_media


def _get_post_metrics(media_id: str, item: dict) -> dict[str, Any]:
    """Fetch insights for a single media object."""
    is_reel = item.get("media_type") in ("VIDEO", "REEL") or item.get(
        "media_product_type"
    ) == "REELS"

    # Base metrics available for all post types
    base_metrics = [
        "impressions",
        "reach",
        "like_count",
        "comments_count",
        "saved",
        "shares",
        "profile_visits",
        "follows",
        "profile_activity",
    ]

    # Reel-specific metrics
    reel_metrics = [
        "plays",
        "ig_reels_avg_watch_time",
        "ig_reels_video_view_total_time",
        "clips_replays_count",
    ]

    metrics_to_fetch = base_metrics + (reel_metrics if is_reel else [])

    url = f"{BASE}/{media_id}/insights"
    params = {
        "metric": ",".join(metrics_to_fetch),
        "access_token": TOKEN,
    }

    try:
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return {m["name"]: m["values"][0]["value"] if m.get("values") else m.get("value", 0)
                for m in data}
    except requests.HTTPError as e:
        print(f"    Warning: could not fetch metrics for {media_id}: {e}")
        return {}


def collect_ig_stars(week_start: datetime, week_end: datetime) -> list[dict[str, Any]]:
    """
    Collect per-post metrics for all posts published in the week window.
    Returns a list of row dicts, one per post.
    """
    print("  Fetching IG post-level metrics...")
    posts = _get_media_in_window(week_start, week_end)
    rows = []

    for post in posts:
        ts = datetime.fromisoformat(post["timestamp"].replace("Z", "+00:00"))
        metrics = post.get("_metrics", {})
        is_reel = post.get("media_type") in ("VIDEO", "REEL") or post.get(
            "media_product_type"
        ) == "REELS"

        reach = metrics.get("reach", 0)
        impressions = metrics.get("impressions", 0)
        likes = metrics.get("like_count", 0)
        comments = metrics.get("comments_count", 0)
        saves = metrics.get("saved", 0)
        shares = metrics.get("shares", 0)
        follows = metrics.get("follows", 0)
        profile_visits = metrics.get("profile_visits", 0)
        interactions = likes + comments + saves + shares

        def pct(part, whole):
            return round(part / whole * 100, 1) if whole else None

        row = {
            "post_date": ts.strftime("%Y-%m-%d"),
            "post_time": ts.strftime("%H:%M"),
            "format": "Reel" if is_reel else post.get("media_type", "").title(),
            "permalink": post.get("permalink", ""),
            # Views / reach
            "views": impressions,
            "accounts_reached": reach,
            # Interactions
            "total_interactions": interactions,
            "likes": likes,
            "comments": comments,
            "saves": saves,
            "shares": shares,
            # Discovery
            "profile_visits": profile_visits,
            "follows": follows,
            # Reel-specific (None for non-reels)
            "avg_watch_time_ms": metrics.get("ig_reels_avg_watch_time") if is_reel else None,
            "total_watch_time_ms": metrics.get("ig_reels_video_view_total_time") if is_reel else None,
            "replays": metrics.get("clips_replays_count") if is_reel else None,
        }
        rows.append(row)

    return rows


# ---------------------------------------------------------------------------
# Schema (column headers for Google Sheets)
# ---------------------------------------------------------------------------

IG_PULSE_HEADERS = [
    "week_end_date",
    "account_reach",
    "impressions",
    "followers",
    "profile_visits",
    "external_link_taps",
    "views_from_posts",
    "views_from_reels",
    "pct_views_from_posts",
    "pct_views_from_reels",
    "total_interactions",
    "interactions_from_posts",
    "interactions_from_reels",
    "pct_interactions_from_posts",
    "pct_interactions_from_reels",
    "likes",
    "comments",
    "saves",
    "shares",
]

IG_STARS_HEADERS = [
    "post_date",
    "post_time",
    "format",
    "permalink",
    "views",
    "accounts_reached",
    "total_interactions",
    "likes",
    "comments",
    "saves",
    "shares",
    "profile_visits",
    "follows",
    "avg_watch_time_ms",
    "total_watch_time_ms",
    "replays",
]


def row_to_list(data: dict, headers: list[str]) -> list[Any]:
    """Convert a dict to a list aligned to the given headers."""
    return [data.get(h) for h in headers]
