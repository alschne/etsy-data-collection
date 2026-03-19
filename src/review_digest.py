"""
review_digest.py — Quarterly and annual review emails.

Reads all historical data from Google Sheets, aggregates by period,
generates AI insights via Gemini, and sends a summary email.

Triggered by separate cron jobs in weekly_pipeline.yml:
  - March 31    → Q1 review
  - June 30     → Q2 review
  - September 30 → Q3 review
  - December 31  → Q4 review + Annual review (two separate emails)
"""

import smtplib
import json
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone
from typing import Any

import config
import sheets


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

QUARTER_RANGES = {
    1: ("01-01", "03-31"),
    2: ("04-01", "06-30"),
    3: ("07-01", "09-30"),
    4: ("10-01", "12-31"),
}

def get_current_quarter() -> int:
    month = datetime.now(timezone.utc).month
    return (month - 1) // 3 + 1

def get_current_year() -> int:
    return datetime.now(timezone.utc).year

def filter_rows_by_period(
    rows: list[dict], start: str, end: str, date_key: str = "week_end_date"
) -> list[dict]:
    """
    Filter sheet rows by a date column within a date range.
    start and end are 'YYYY-MM-DD' strings.
    date_key defaults to 'week_end_date' but can be 'post_date' for ig_stars.
    """
    return [
        r for r in rows
        if start <= str(r.get(date_key, "")) <= end
    ]


# ---------------------------------------------------------------------------
# Data aggregation
# ---------------------------------------------------------------------------

def aggregate_ig_pulse(rows: list[dict]) -> dict:
    """Aggregate ig_pulse rows into period totals and averages."""
    if not rows:
        return {}

    def safe_float_val(val):
        if val in (None, "", "--"):
            return 0.0
        try:
            return float(val)
        except (TypeError, ValueError):
            return 0.0

    def safe_sum(key):
        return sum(safe_float_val(r.get(key)) for r in rows)

    def safe_avg(key):
        vals = [float(r.get(key)) for r in rows if r.get(key) not in (None, "")]
        return round(sum(vals) / len(vals), 1) if vals else None

    # Follower growth: last row - first row
    try:
        follower_start = float(rows[0].get("followers") or 0)
        follower_end = float(rows[-1].get("followers") or 0)
        follower_growth = int(follower_end - follower_start)
    except (TypeError, ValueError):
        follower_growth = None

    return {
        "weeks": len(rows),
        "total_reach": int(safe_sum("account_reach")),
        "total_views": int(safe_sum("total_views")),
        "total_interactions": int(safe_sum("total_interactions")),
        "total_likes": int(safe_sum("likes")),
        "total_saves": int(safe_sum("saves")),
        "total_shares": int(safe_sum("shares")),
        "total_comments": int(safe_sum("comments")),
        "total_profile_visits": int(safe_sum("profile_visits")),
        "avg_weekly_reach": safe_avg("account_reach"),
        "avg_weekly_views": safe_avg("total_views"),
        "avg_weekly_interactions": safe_avg("total_interactions"),
        "follower_start": int(follower_start),
        "follower_end": int(follower_end),
        "follower_growth": follower_growth,
        "best_week_reach": int(max((float(r.get("account_reach") or 0) for r in rows), default=0)),
        "best_week_date": max(rows, key=lambda r: float(r.get("account_reach") or 0)).get("week_end_date"),
    }


def aggregate_ig_stars(rows: list[dict]) -> dict:
    """Aggregate ig_stars rows into period totals."""
    if not rows:
        return {}

    posts = [r for r in rows if str(r.get("format", "")).lower() != "reel"]
    reels = [r for r in rows if str(r.get("format", "")).lower() == "reel"]

    def top_by(metric, n=3):
        return sorted(rows, key=lambda r: float(r.get(metric) or 0), reverse=True)[:n]

    def safe_float(val):
        """Convert a value to float, returning None if it can't be converted."""
        if val in (None, "", "--"):
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    def avg(items, key):
        vals = [safe_float(r.get(key)) for r in items]
        vals = [v for v in vals if v is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    top_posts = top_by("views")

    return {
        "total_posts": len(rows),
        "total_image_posts": len(posts),
        "total_reels": len(reels),
        "avg_views_per_post": avg(rows, "views"),
        "avg_views_posts": avg(posts, "views"),
        "avg_views_reels": avg(reels, "views"),
        "avg_watch_time_ms": avg(reels, "avg_watch_time_ms"),
        "top_posts": [
            {
                "date": r.get("post_date"),
                "format": r.get("format"),
                "views": r.get("views"),
                "saves": r.get("saves"),
                "shares": r.get("shares"),
                "permalink": r.get("permalink"),
            }
            for r in top_posts
        ],
    }


def aggregate_etsy_stars(rows: list[dict]) -> dict:
    """Aggregate etsy_stars rows into period totals."""
    if not rows:
        return {}

    # Get unique weeks
    weeks = sorted(set(r.get("week_end_date") for r in rows if r.get("week_end_date")))

    total_orders = sum(float(r.get("weekly_orders") or 0) for r in rows)
    total_revenue = sum(float(r.get("weekly_revenue") or 0) for r in rows)
    aov = round(total_revenue / total_orders, 2) if total_orders > 0 else None

    # Top listings by revenue
    listing_totals: dict[str, dict] = {}
    for r in rows:
        name = r.get("listing_name", "Unknown")
        if name not in listing_totals:
            listing_totals[name] = {"orders": 0, "revenue": 0.0}
        listing_totals[name]["orders"] += float(r.get("weekly_orders") or 0)
        listing_totals[name]["revenue"] += float(r.get("weekly_revenue") or 0)

    top_listings = sorted(listing_totals.items(), key=lambda x: x[1]["revenue"], reverse=True)[:5]

    return {
        "weeks_tracked": len(weeks),
        "total_orders": int(total_orders),
        "total_revenue": round(total_revenue, 2),
        "avg_weekly_orders": round(total_orders / len(weeks), 1) if weeks else None,
        "avg_weekly_revenue": round(total_revenue / len(weeks), 2) if weeks else None,
        "aov": aov,
        "top_listings": [
            {"name": name[:50], "orders": int(d["orders"]), "revenue": round(d["revenue"], 2)}
            for name, d in top_listings
        ],
    }


# ---------------------------------------------------------------------------
# AI insights
# ---------------------------------------------------------------------------

def _get_review_insights(
    period_label: str,
    ig_pulse_agg: dict,
    ig_stars_agg: dict,
    etsy_agg: dict,
    is_annual: bool = False,
) -> str:
    """Generate AI insights for a quarterly or annual review."""

    period_type = "year" if is_annual else "quarter"
    etsy_section = ""
    if etsy_agg:
        etsy_section = f"""
ETSY PERFORMANCE:
- Total orders: {etsy_agg.get('total_orders')}
- Total revenue: ${etsy_agg.get('total_revenue')}
- Avg weekly orders: {etsy_agg.get('avg_weekly_orders')}
- Avg weekly revenue: ${etsy_agg.get('avg_weekly_revenue')}
- Avg order value: ${etsy_agg.get('aov')}
- Top listings: {json.dumps(etsy_agg.get('top_listings', []))}
"""

    prompt = f"""You are an expert Instagram growth coach and small business analyst reviewing a {period_type} of performance data.

Period: {period_label}
{"This is an annual review — look for year-long trends, seasonal patterns, and strategic direction for next year." if is_annual else "This is a quarterly review — focus on what worked this quarter and one clear priority for next quarter."}

INSTAGRAM ACCOUNT METRICS ({period_label}):
- Weeks of data: {ig_pulse_agg.get('weeks')}
- Total reach: {ig_pulse_agg.get('total_reach')}
- Total views: {ig_pulse_agg.get('total_views')}
- Follower growth: {ig_pulse_agg.get('follower_start')} → {ig_pulse_agg.get('follower_end')} ({ig_pulse_agg.get('follower_growth'):+d} followers)
- Avg weekly reach: {ig_pulse_agg.get('avg_weekly_reach')}
- Total saves: {ig_pulse_agg.get('total_saves')}
- Total shares: {ig_pulse_agg.get('total_shares')}
- Total profile visits: {ig_pulse_agg.get('total_profile_visits')}
- Best week reach: {ig_pulse_agg.get('best_week_reach')} (week ending {ig_pulse_agg.get('best_week_date')})

CONTENT BREAKDOWN:
- Total posts published: {ig_stars_agg.get('total_posts')} ({ig_stars_agg.get('total_image_posts')} images, {ig_stars_agg.get('total_reels')} reels)
- Avg views per image post: {ig_stars_agg.get('avg_views_posts')}
- Avg views per reel: {ig_stars_agg.get('avg_views_reels')}
- Top performing posts: {json.dumps(ig_stars_agg.get('top_posts', []))}
{etsy_section}
Primary goal: follower growth.

Write a {period_type} review in plain HTML paragraphs only (no headers, bullets, markdown, preamble).
{"Write 4 paragraphs: (1) Overall story of the year in 2 sentences with key numbers. (2) Biggest win of the year — what drove it. (3) Biggest opportunity — what held growth back and what to fix. (4) One strategic priority for next year, specific and actionable." if is_annual else "Write 3 paragraphs: (1) Overall story of the quarter in 1-2 sentences with key numbers. (2) What worked best this quarter — tie to follower growth. (3) One clear priority for next quarter, specific and actionable."}

Be warm, direct, and specific. Reference actual numbers. Total {"under 200" if is_annual else "under 150"} words.
Return only the HTML paragraphs."""

    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={config.GOOGLE_AI_API_KEY}",
            headers={"content-type": "application/json"},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        print(f"  Warning: AI insights unavailable: {e}")
        return ""


# ---------------------------------------------------------------------------
# HTML builder
# ---------------------------------------------------------------------------

def _fmt(value: Any, prefix: str = "", suffix: str = "", decimals: int = 0) -> str:
    if value is None or value == "":
        return "—"
    try:
        f = float(value)
        return f"{prefix}{f:,.{decimals}f}{suffix}"
    except (TypeError, ValueError):
        return str(value)


def build_review_html(
    period_label: str,
    ig_pulse_agg: dict,
    ig_stars_agg: dict,
    etsy_agg: dict,
    insights_html: str,
    is_annual: bool = False,
) -> str:
    review_type = "Annual Review" if is_annual else "Quarterly Review"
    accent = "#4a148c" if is_annual else "#1565c0"

    # Top posts rows
    top_posts_html = ""
    for p in ig_stars_agg.get("top_posts", []):
        link = f'<a href="{p.get("permalink","")}" style="color:#aaa;font-size:11px">View ↗</a>' if p.get("permalink") else ""
        top_posts_html += (
            f'<tr style="border-bottom:1px solid #f5f5f5">'
            f'<td style="padding:7px 8px;font-size:13px">{p.get("format","")}<br>'
            f'<span style="color:#aaa;font-size:11px">{p.get("date","")}</span><br>{link}</td>'
            f'<td style="padding:7px 8px;text-align:right;font-size:13px;font-weight:700">{_fmt(p.get("views"))}</td>'
            f'<td style="padding:7px 8px;text-align:right;font-size:13px">🔖 {_fmt(p.get("saves"))}</td>'
            f'<td style="padding:7px 8px;text-align:right;font-size:13px">↗ {_fmt(p.get("shares"))}</td>'
            f'</tr>'
        )

    # Etsy section
    etsy_html = ""
    if etsy_agg and etsy_agg.get("total_orders", 0) > 0:
        top_listings_rows = ""
        for l in etsy_agg.get("top_listings", []):
            top_listings_rows += (
                f'<tr style="border-bottom:1px solid #f5f5f5">'
                f'<td style="padding:7px 8px;font-size:13px">{l.get("name","")}</td>'
                f'<td style="padding:7px 8px;text-align:right;font-size:13px">{_fmt(l.get("orders"))}</td>'
                f'<td style="padding:7px 8px;text-align:right;font-size:13px">{_fmt(l.get("revenue"), prefix="$", decimals=2)}</td>'
                f'</tr>'
            )
        etsy_html = f"""
  <h3 style="color:#f57c00;margin:24px 0 12px 0;font-size:15px;text-transform:uppercase;letter-spacing:0.5px">🛍️ Etsy Shop</h3>
  <table style="width:100%;border-collapse:collapse;margin-bottom:16px">
    <tr style="background:#fff3e0">
      <td style="padding:10px;text-align:center">
        <div style="font-size:22px;font-weight:700">{_fmt(etsy_agg.get('total_orders'))}</div>
        <div style="font-size:12px;color:#888">Total Orders</div>
      </td>
      <td style="padding:10px;text-align:center">
        <div style="font-size:22px;font-weight:700">{_fmt(etsy_agg.get('total_revenue'), prefix='$', decimals=2)}</div>
        <div style="font-size:12px;color:#888">Total Revenue</div>
      </td>
      <td style="padding:10px;text-align:center">
        <div style="font-size:22px;font-weight:700">{_fmt(etsy_agg.get('aov'), prefix='$', decimals=2)}</div>
        <div style="font-size:12px;color:#888">Avg Order Value</div>
      </td>
    </tr>
  </table>
  <p style="font-size:12px;color:#888;margin-bottom:6px">Top listings by revenue</p>
  <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:24px">
    <tr style="background:#fff8f0;font-size:12px;color:#888">
      <th style="padding:6px 8px;text-align:left">Listing</th>
      <th style="padding:6px 8px;text-align:right">Orders</th>
      <th style="padding:6px 8px;text-align:right">Revenue</th>
    </tr>
    {top_listings_rows}
  </table>"""

    follower_growth = ig_pulse_agg.get('follower_growth', 0) or 0
    growth_color = "#2e7d32" if follower_growth >= 0 else "#c62828"
    growth_sign = "+" if follower_growth >= 0 else ""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;max-width:640px;margin:0 auto;color:#1a1a1a;padding:24px 16px">

  <div style="border-bottom:3px solid {accent};padding-bottom:12px;margin-bottom:20px">
    <h2 style="margin:0;color:{accent};font-size:24px">{"🏆" if is_annual else "📅"} {review_type}</h2>
    <p style="margin:4px 0 0 0;color:#aaa;font-size:13px">{period_label}</p>
  </div>

  {"" if not insights_html else f'''
  <div style="background:#f3e5f5;border-left:4px solid {accent};padding:14px 16px;margin-bottom:24px;border-radius:0 6px 6px 0">
    <p style="margin:0 0 8px 0;font-size:12px;color:{accent};font-weight:600;text-transform:uppercase;letter-spacing:0.5px">✦ {"Year in Review" if is_annual else "Quarter in Review"}</p>
    <div style="font-size:13px;color:#333;line-height:1.7">{insights_html}</div>
  </div>'''}

  <h3 style="color:#e91e63;margin:0 0 12px 0;font-size:15px;text-transform:uppercase;letter-spacing:0.5px">📸 Instagram — {period_label}</h3>

  <table style="width:100%;border-collapse:collapse;margin-bottom:20px">
    <tr style="background:#fce4ec">
      <td style="padding:10px;text-align:center">
        <div style="font-size:22px;font-weight:700">{_fmt(ig_pulse_agg.get('total_reach'))}</div>
        <div style="font-size:12px;color:#888">Total Reach</div>
      </td>
      <td style="padding:10px;text-align:center">
        <div style="font-size:22px;font-weight:700">{_fmt(ig_pulse_agg.get('total_views'))}</div>
        <div style="font-size:12px;color:#888">Total Views</div>
      </td>
      <td style="padding:10px;text-align:center">
        <div style="font-size:22px;font-weight:700" style="color:{growth_color}">{growth_sign}{_fmt(follower_growth)}</div>
        <div style="font-size:12px;color:#888">Follower Growth</div>
      </td>
    </tr>
  </table>

  <table style="width:100%;border-collapse:collapse;margin-bottom:20px;font-size:13px">
    <tr style="background:#fafafa">
      <td style="padding:8px">Avg weekly reach</td>
      <td style="padding:8px;text-align:right;font-weight:600">{_fmt(ig_pulse_agg.get('avg_weekly_reach'))}</td>
      <td style="padding:8px">Total saves</td>
      <td style="padding:8px;text-align:right;font-weight:600">{_fmt(ig_pulse_agg.get('total_saves'))}</td>
    </tr>
    <tr>
      <td style="padding:8px">Total interactions</td>
      <td style="padding:8px;text-align:right;font-weight:600">{_fmt(ig_pulse_agg.get('total_interactions'))}</td>
      <td style="padding:8px">Total shares</td>
      <td style="padding:8px;text-align:right;font-weight:600">{_fmt(ig_pulse_agg.get('total_shares'))}</td>
    </tr>
    <tr style="background:#fafafa">
      <td style="padding:8px">Posts published</td>
      <td style="padding:8px;text-align:right;font-weight:600">{_fmt(ig_stars_agg.get('total_posts'))} ({_fmt(ig_stars_agg.get('total_image_posts'))} posts / {_fmt(ig_stars_agg.get('total_reels'))} reels)</td>
      <td style="padding:8px">Best week reach</td>
      <td style="padding:8px;text-align:right;font-weight:600">{_fmt(ig_pulse_agg.get('best_week_reach'))}</td>
    </tr>
    <tr>
      <td style="padding:8px">Avg views / image post</td>
      <td style="padding:8px;text-align:right;font-weight:600">{_fmt(ig_stars_agg.get('avg_views_posts'))}</td>
      <td style="padding:8px">Avg views / reel</td>
      <td style="padding:8px;text-align:right;font-weight:600">{_fmt(ig_stars_agg.get('avg_views_reels'))}</td>
    </tr>
  </table>

  <p style="font-size:13px;color:#555;margin-bottom:8px;font-weight:600">Top performing posts</p>
  <table style="width:100%;border-collapse:collapse;margin-bottom:24px;font-size:13px">
    <tr style="background:#fce4ec;font-size:11px;color:#888;text-transform:uppercase">
      <th style="padding:7px 8px;text-align:left;font-weight:600">Post</th>
      <th style="padding:7px 8px;text-align:right;font-weight:600">Views</th>
      <th style="padding:7px 8px;text-align:right;font-weight:600">Saves</th>
      <th style="padding:7px 8px;text-align:right;font-weight:600">Shares</th>
    </tr>
    {top_posts_html if top_posts_html else '<tr><td colspan="4" style="padding:12px;text-align:center;color:#aaa">No post data for this period</td></tr>'}
  </table>

  {etsy_html}

  <p style="font-size:11px;color:#ccc;border-top:1px solid #f0f0f0;padding-top:12px;margin-top:8px">
    Auto-generated {review_type.lower()} · {period_label} ·
    <a href="https://docs.google.com/spreadsheets/d/{config.GOOGLE_SPREADSHEET_ID}" style="color:#ccc">View full data ↗</a>
  </p>

</body>
</html>"""


# ---------------------------------------------------------------------------
# Send
# ---------------------------------------------------------------------------

def send_review(period_label: str, html: str, is_annual: bool = False) -> None:
    review_type = "Annual Review 🏆" if is_annual else "Quarterly Review 📅"
    subject = f"{review_type} — {period_label}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Expressions Analytics Pipeline <{config.EMAIL_SENDER}>"
    msg["To"] = config.EMAIL_RECIPIENT
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(config.EMAIL_SENDER, config.EMAIL_PASSWORD)
        server.sendmail(config.EMAIL_SENDER, config.EMAIL_RECIPIENT, msg.as_string())

    print(f"  {review_type} email sent to {config.EMAIL_RECIPIENT}")


# ---------------------------------------------------------------------------
# Main entry points
# ---------------------------------------------------------------------------

def run_quarterly_review(quarter: int | None = None, year: int | None = None) -> None:
    q = quarter or get_current_quarter()
    y = year or get_current_year()
    start_suffix, end_suffix = QUARTER_RANGES[q]
    start = f"{y}-{start_suffix}"
    end = f"{y}-{end_suffix}"
    period_label = f"Q{q} {y}"

    print(f"\n  Running quarterly review for {period_label} ({start} → {end})")

    ig_pulse_rows = filter_rows_by_period(
        sheets.get_sheet(config.SHEET_IG_PULSE).get_all_records(), start, end
    )
    ig_stars_rows = filter_rows_by_period(
        sheets.get_sheet(config.SHEET_IG_STARS).get_all_records(), start, end,
        date_key="post_date"
    )
    try:
        etsy_rows = filter_rows_by_period(
            sheets.get_sheet(config.SHEET_ETSY_STARS).get_all_records(), start, end
        )
    except Exception:
        etsy_rows = []

    ig_pulse_agg = aggregate_ig_pulse(ig_pulse_rows)
    ig_stars_agg = aggregate_ig_stars(ig_stars_rows)
    etsy_agg = aggregate_etsy_stars(etsy_rows)

    insights = _get_review_insights(period_label, ig_pulse_agg, ig_stars_agg, etsy_agg)
    html = build_review_html(period_label, ig_pulse_agg, ig_stars_agg, etsy_agg, insights)
    send_review(period_label, html)
    print(f"  ✓ Quarterly review sent for {period_label}")


def run_annual_review(year: int | None = None) -> None:
    y = year or get_current_year()
    start = f"{y}-01-01"
    end = f"{y}-12-31"
    period_label = f"Full Year {y}"

    print(f"\n  Running annual review for {period_label}")

    ig_pulse_rows = filter_rows_by_period(
        sheets.get_sheet(config.SHEET_IG_PULSE).get_all_records(), start, end
    )
    ig_stars_rows = filter_rows_by_period(
        sheets.get_sheet(config.SHEET_IG_STARS).get_all_records(), start, end,
        date_key="post_date"
    )
    try:
        etsy_rows = filter_rows_by_period(
            sheets.get_sheet(config.SHEET_ETSY_STARS).get_all_records(), start, end
        )
    except Exception:
        etsy_rows = []

    ig_pulse_agg = aggregate_ig_pulse(ig_pulse_rows)
    ig_stars_agg = aggregate_ig_stars(ig_stars_rows)
    etsy_agg = aggregate_etsy_stars(etsy_rows)

    insights = _get_review_insights(
        period_label, ig_pulse_agg, ig_stars_agg, etsy_agg, is_annual=True
    )
    html = build_review_html(
        period_label, ig_pulse_agg, ig_stars_agg, etsy_agg, insights, is_annual=True
    )
    send_review(period_label, html, is_annual=True)
    print(f"  ✓ Annual review sent for {period_label}")