"""
ig_collector.py — Pulls Instagram Business account data via the Instagram Graph API
(Instagram Login flow, graph.instagram.com endpoints).

Metric names as of March 2025 (post-deprecation):
  Account-level: reach, views, profile_views, follower_count
  Post-level:    views, reach, likes, comments, saved, shares, follows, profile_visits
  Reel-specific: ig_reels_avg_watch_time, ig_reels_video_view_total_time

Deprecated and NOT used:
  impressions (replaced by views), profile_views/website_clicks (removed Jan 2025),
  reel_plays, reel_replays (removed Mar 2025)
"""

import requests
from datetime import datetime, timedelta, timezone
from typing import Any

import config


BASE = config.IG_BASE_URL
ACCOUNT_ID = config.IG_ACCOUNT_ID


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------

def refresh_access_token(current_token: str) -> str:
    """Refresh a long-lived token. Call on every run to keep it alive."""
    resp = requests.get(
        f"{BASE}/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": current_token},
    )
    resp.raise_for_status()
    new_token = resp.json()["access_token"]
    print(f"  IG token refreshed.")
    return new_token


def save_refreshed_token(new_token: str) -> None:
    """Write refreshed token back to GitHub Secrets."""
    import base64
    if not config.GITHUB_TOKEN or not config.GITHUB_REPO:
        print("  GITHUB_TOKEN or GITHUB_REPO not set — skipping token save.")
        return
    try:
        from nacl import encoding, public
        headers = {
            "Authorization": f"Bearer {config.GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        }
        pk_url = f"https://api.github.com/repos/{config.GITHUB_REPO}/actions/secrets/public-key"
        pk_data = requests.get(pk_url, headers=headers).json()
        pub_key = public.PublicKey(pk_data["key"].encode(), encoding.Base64Encoder())
        encrypted = base64.b64encode(
            public.SealedBox(pub_key).encrypt(new_token.encode())
        ).decode()
        requests.put(
            f"https://api.github.com/repos/{config.GITHUB_REPO}/actions/secrets/IG_ACCESS_TOKEN",
            headers=headers,
            json={"encrypted_value": encrypted, "key_id": pk_data["key_id"]},
        ).raise_for_status()
        print("  Refreshed IG_ACCESS_TOKEN saved to GitHub Secrets.")
    except ImportError:
        print("  PyNaCl not installed — skipping GitHub Secrets update.")


# ---------------------------------------------------------------------------
# Account-level insights (ig_pulse)
# ---------------------------------------------------------------------------

def _get_account_insights(token: str, since: datetime, until: datetime) -> dict:
    """Fetch daily account insights and aggregate over the date range."""
    resp = requests.get(
        f"{BASE}/{ACCOUNT_ID}/insights",
        params={
            "metric": "reach,views,profile_views",
            "period": "day",
            "since": int(since.timestamp()),
            "until": int(until.timestamp()),
            "access_token": token,
        },
    )
    resp.raise_for_status()
    aggregated = {}
    for metric_obj in resp.json().get("data", []):
        name = metric_obj["name"]
        aggregated[name] = sum(v["value"] for v in metric_obj.get("values", []))
    return aggregated


def _get_follower_count(token: str) -> int:
    """Point-in-time follower count."""
    resp = requests.get(
        f"{BASE}/{ACCOUNT_ID}",
        params={"fields": "followers_count", "access_token": token},
    )
    resp.raise_for_status()
    return resp.json().get("followers_count", 0)


def collect_ig_pulse(week_start: datetime, week_end: datetime) -> dict[str, Any]:
    """Collect weekly account-level metrics for ig_pulse tab."""
    token = config.IG_ACCESS_TOKEN
    print("  Fetching IG account insights...")
    insights = _get_account_insights(token, week_start, week_end)
    followers = _get_follower_count(token)
    post_metrics = _get_content_type_breakdown(token, week_start, week_end)

    reach = insights.get("reach", 0)
    total_views = insights.get("views", 0)
    profile_views = insights.get("profile_views", 0)
    interactions = post_metrics.get("total_interactions", 0)
    post_interactions = post_metrics.get("post_interactions", 0)
    reel_interactions = post_metrics.get("reel_interactions", 0)
    post_views = post_metrics.get("post_views", 0)
    reel_views = post_metrics.get("reel_views", 0)
    content_views = post_views + reel_views

    def pct(part, whole):
        return round(part / whole * 100, 1) if whole else None

    return {
        "week_end_date": week_end.strftime("%Y-%m-%d"),
        "account_reach": reach,
        "total_views": total_views,
        "followers": followers,
        "profile_visits": profile_views,
        "views_from_posts": post_views,
        "views_from_reels": reel_views,
        "pct_views_from_posts": pct(post_views, content_views),
        "pct_views_from_reels": pct(reel_views, content_views),
        "total_interactions": interactions,
        "interactions_from_posts": post_interactions,
        "interactions_from_reels": reel_interactions,
        "pct_interactions_from_posts": pct(post_interactions, interactions),
        "pct_interactions_from_reels": pct(reel_interactions, interactions),
        "likes": post_metrics.get("likes", 0),
        "comments": post_metrics.get("comments", 0),
        "saves": post_metrics.get("saves", 0),
        "shares": post_metrics.get("shares", 0),
    }


def _get_content_type_breakdown(
    token: str, week_start: datetime, week_end: datetime
) -> dict[str, int]:
    """Sum post metrics by content type (posts vs reels) for the week."""
    posts = _get_media_in_window(token, week_start, week_end)
    totals = {k: 0 for k in [
        "total_interactions", "post_interactions", "reel_interactions",
        "post_views", "reel_views", "likes", "comments", "saves", "shares",
    ]}
    for post in posts:
        is_reel = _is_reel(post)
        m = post.get("_metrics", {})
        likes = m.get("likes", 0)
        comments = m.get("comments", 0)
        saves = m.get("saved", 0)
        shares = m.get("shares", 0)
        views = m.get("views", 0)
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

def _is_reel(item: dict) -> bool:
    return (
        item.get("media_type") in ("VIDEO", "REEL")
        or item.get("media_product_type") == "REELS"
    )


def _get_media_in_window(
    token: str, week_start: datetime, week_end: datetime
) -> list[dict]:
    """Return all media published in the window with metrics attached."""
    url = f"{BASE}/{ACCOUNT_ID}/media"
    params = {
        "fields": "id,timestamp,media_type,media_product_type,permalink",
        "access_token": token,
        "limit": 50,
    }
    all_media = []
    while url:
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        page = resp.json()
        stop = False
        for item in page.get("data", []):
            ts = datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00"))
            if week_start <= ts <= week_end:
                all_media.append(item)
            elif ts < week_start:
                stop = True
                break
        if stop:
            break
        url = page.get("paging", {}).get("next")
        params = {}

    for item in all_media:
        item["_metrics"] = _get_post_metrics(token, item["id"], item)
    return all_media


def _get_post_metrics(token: str, media_id: str, item: dict) -> dict:
    """
    Fetch insights for a single media object.

    Valid metrics per media type (per official Meta docs):
      FEED posts : views, reach, likes, comments, saved, shares, profile_visits,
                   follows, total_interactions
      REELS      : views, reach, likes, comments, saved, shares,
                   ig_reels_avg_watch_time, ig_reels_video_view_total_time,
                   total_interactions
                   NOTE: follows/profile_visits are NOT valid for reels
      CAROUSEL   : insights not available for individual album children;
                   use limited metrics on the album itself
    """
    is_reel = _is_reel(item)
    is_carousel = item.get("media_type") == "CAROUSEL_ALBUM"

    if is_carousel:
        metrics = ["reach", "likes", "comments", "saved", "shares", "total_interactions"]
    elif is_reel:
        # follows and profile_visits are NOT available for reels
        metrics = [
            "views", "reach", "likes", "comments", "saved", "shares",
            "total_interactions",
            "ig_reels_avg_watch_time", "ig_reels_video_view_total_time",
        ]
    else:
        # FEED posts
        metrics = [
            "views", "reach", "likes", "comments", "saved", "shares",
            "total_interactions", "profile_visits", "follows",
        ]

    try:
        resp = requests.get(
            f"{BASE}/{media_id}/insights",
            params={"metric": ",".join(metrics), "access_token": token},
        )
        resp.raise_for_status()
        return {
            m["name"]: (m["values"][0]["value"] if m.get("values") else m.get("value", 0))
            for m in resp.json().get("data", [])
        }
    except requests.HTTPError as e:
        print(f"    Warning: could not fetch metrics for {media_id}: {e}")
        return {}


def collect_ig_stars(week_start: datetime, week_end: datetime) -> list[dict[str, Any]]:
    """Collect per-post metrics for all posts published in the week window."""
    token = config.IG_ACCESS_TOKEN
    print("  Fetching IG post-level metrics...")
    posts = _get_media_in_window(token, week_start, week_end)
    rows = []
    for post in posts:
        ts = datetime.fromisoformat(post["timestamp"].replace("Z", "+00:00"))
        m = post.get("_metrics", {})
        is_reel = _is_reel(post)
        likes = m.get("likes", 0)
        comments = m.get("comments", 0)
        saves = m.get("saved", 0)
        shares = m.get("shares", 0)

        rows.append({
            "post_date": ts.strftime("%Y-%m-%d"),
            "post_time": ts.strftime("%H:%M"),
            "format": "Reel" if is_reel else post.get("media_type", "").title(),
            "permalink": post.get("permalink", ""),
            "views": m.get("views", 0),
            "accounts_reached": m.get("reach", 0),
            "total_interactions": likes + comments + saves + shares,
            "likes": likes,
            "comments": comments,
            "saves": saves,
            "shares": shares,
            "profile_visits": m.get("profile_visits", 0),
            "follows": m.get("follows", 0),
            "avg_watch_time_ms": m.get("ig_reels_avg_watch_time") if is_reel else None,
            "total_watch_time_ms": m.get("ig_reels_video_view_total_time") if is_reel else None,
        })
    return rows


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

IG_PULSE_HEADERS = [
    "week_end_date", "account_reach", "total_views", "followers",
    "profile_visits", "views_from_posts", "views_from_reels",
    "pct_views_from_posts", "pct_views_from_reels",
    "total_interactions", "interactions_from_posts", "interactions_from_reels",
    "pct_interactions_from_posts", "pct_interactions_from_reels",
    "likes", "comments", "saves", "shares",
]

IG_STARS_HEADERS = [
    "post_date", "post_time", "format", "permalink",
    "views", "accounts_reached", "total_interactions",
    "likes", "comments", "saves", "shares",
    "profile_visits", "follows",
    "avg_watch_time_ms", "total_watch_time_ms",
]


def row_to_list(data: dict, headers: list[str]) -> list[Any]:
    return [data.get(h) for h in headers]
# Note: carousel (CAROUSEL_ALBUM) media type added to _get_post_metrics handling