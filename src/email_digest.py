"""
email_digest.py — Weekly HTML email digest with per-post breakdown,
week-over-week comparisons, format analysis, and AI-generated insights.
"""

import smtplib
import json
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import config


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt(value: Any, prefix: str = "", suffix: str = "", decimals: int = 0) -> str:
    if value is None or value == "":
        return "—"
    try:
        f = float(value)
        return f"{prefix}{f:,.{decimals}f}{suffix}"
    except (TypeError, ValueError):
        return str(value)


def _pct_change(current: Any, previous: Any) -> str:
    try:
        c, p = float(current), float(previous)
        if p == 0:
            return ""
        change = (c - p) / p * 100
        arrow = "▲" if change >= 0 else "▼"
        colour = "#2e7d32" if change >= 0 else "#c62828"
        return f'<span style="color:{colour};font-size:12px;font-weight:600">{arrow} {abs(change):.1f}%</span>'
    except (TypeError, ValueError):
        return ""


def _ms_to_mmss(ms: Any) -> str:
    """Convert milliseconds to m:ss string."""
    if ms is None or ms == "" or ms == 0:
        return "—"
    try:
        total_seconds = int(float(ms)) // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}m {seconds:02d}s"
    except (TypeError, ValueError):
        return "—"


# ---------------------------------------------------------------------------
# AI insights via Claude API
# ---------------------------------------------------------------------------

def _get_ai_insights(
    week_end: str,
    ig_pulse: dict,
    prev_ig_pulse: dict | None,
    post_rows: list[dict],
) -> str:
    """
    Call Claude API to generate a short analytical + coaching insight paragraph.
    Returns plain HTML string. Falls back to empty string on any error.
    """
    if not post_rows and not ig_pulse:
        return ""

    # Build a concise data summary to send to Claude
    posts_summary = []
    for p in post_rows:
        posts_summary.append({
            "format": p.get("format"),
            "views": p.get("views"),
            "reach": p.get("accounts_reached"),
            "likes": p.get("likes"),
            "saves": p.get("saves"),
            "shares": p.get("shares"),
            "comments": p.get("comments"),
            "avg_watch_time": _ms_to_mmss(p.get("avg_watch_time_ms")),
            "profile_visits": p.get("profile_visits"),
            "follows": p.get("follows"),
        })

    prev_summary = ""
    if prev_ig_pulse:
        prev_summary = f"""
Last week for comparison:
- Reach: {prev_ig_pulse.get('account_reach')}
- Total views: {prev_ig_pulse.get('total_views')}
- Interactions: {prev_ig_pulse.get('total_interactions')}
- Followers: {prev_ig_pulse.get('followers')}
"""

    prompt = f"""You are an expert Instagram growth coach helping a small business owner review their weekly performance data. Your goal is to give them a quick, encouraging, and genuinely useful weekly briefing.

The account's #1 goal is follower growth. Everything should be framed around: what's helping reach new people, what's converting viewers into followers, and what one thing to try next week.

Here is their data for the week ending {week_end}:

ACCOUNT METRICS:
- Reach: {ig_pulse.get('account_reach')}
- Total views: {ig_pulse.get('total_views')}
- Followers: {ig_pulse.get('followers')}
- Profile visits: {ig_pulse.get('profile_visits')}
- Total interactions: {ig_pulse.get('total_interactions')}
- Likes: {ig_pulse.get('likes')}
- Saves: {ig_pulse.get('saves')}
- Shares: {ig_pulse.get('shares')}
- Comments: {ig_pulse.get('comments')}
- Views from posts: {ig_pulse.get('views_from_posts')} ({ig_pulse.get('pct_views_from_posts')}%)
- Views from reels: {ig_pulse.get('views_from_reels')} ({ig_pulse.get('pct_views_from_reels')}%)
{prev_summary}
INDIVIDUAL POSTS THIS WEEK:
{json.dumps(posts_summary, indent=2)}

Background knowledge to inform your advice:
- Saves and shares are the highest-value signals to Instagram's algorithm — they trigger wider distribution
- Reels get the most reach to non-followers; posts/carousels tend to perform better with existing followers
- Profile visits that don't convert to follows usually mean the bio or grid isn't compelling enough
- Watch time in the first 3 seconds is critical for reels — hooks matter enormously
- A direct CTA ("follow for more [X]") at the end of a reel meaningfully increases follow rate
- Posting consistency matters more than volume — 3x/week beats 7x/week then 0x/week

Write exactly 3 short paragraphs in plain HTML only (no headers, no bullet points, no markdown, no preamble):

1. ONE sentence on the most important thing the data shows this week — lead with something positive or a genuine signal, not a problem. Reference a specific number.
2. ONE sentence on what specifically worked and why it matters for growth.
3. ONE concrete, specific action for next week — not "post more reels" but something like "end your next reel with a verbal CTA: say follow for more [topic] before the last second" or "your saves are strong — add a caption that tells people to save this for later to amplify that signal". Make it something she can actually do.

Total under 90 words. Be warm but direct. Never lead with what went wrong.

Return only the 3 HTML paragraphs, nothing else."""

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
# HTML builders
# ---------------------------------------------------------------------------

def _post_row_html(post: dict, rank: int) -> str:
    is_reel = str(post.get("format", "")).lower() == "reel"
    format_badge = (
        '<span style="background:#e91e63;color:white;padding:2px 6px;border-radius:10px;font-size:11px">Reel</span>'
        if is_reel else
        '<span style="background:#1976d2;color:white;padding:2px 6px;border-radius:10px;font-size:11px">Post</span>'
    )
    permalink = post.get("permalink", "")
    link = f'<a href="{permalink}" style="color:#555;font-size:11px">View ↗</a>' if permalink else ""

    watch_time = _ms_to_mmss(post.get("avg_watch_time_ms")) if is_reel else "—"

    return f"""
    <tr style="border-bottom:1px solid #f0f0f0">
      <td style="padding:10px 8px;font-size:13px">
        {format_badge}<br>
        <span style="color:#aaa;font-size:11px;margin-top:4px;display:block">{post.get('post_date','')}</span>
        <span style="margin-top:2px;display:block">{link}</span>
      </td>
      <td style="padding:10px 8px;text-align:right;font-size:13px">
        <strong>{_fmt(post.get('views'))}</strong>
        <span style="display:block;color:#aaa;font-size:11px">reach: {_fmt(post.get('accounts_reached'))}</span>
      </td>
      <td style="padding:10px 8px;text-align:right;font-size:13px">
        <span title="saves">🔖 {_fmt(post.get('saves'))}</span><br>
        <span title="shares" style="color:#aaa;font-size:11px">↗ {_fmt(post.get('shares'))} shares</span>
      </td>
      <td style="padding:10px 8px;text-align:right;font-size:13px">
        {watch_time if is_reel else f'👍 {_fmt(post.get("likes"))}<br><span style="color:#aaa;font-size:11px">💬 {_fmt(post.get("comments"))}</span>'}
      </td>
    </tr>"""


def _mini_bar(value: Any, max_value: Any, color: str = "#e91e63") -> str:
    """Render a tiny inline bar as an HTML table cell background."""
    try:
        pct = min(100, int(float(value) / float(max_value) * 100)) if float(max_value) > 0 else 0
    except (TypeError, ValueError, ZeroDivisionError):
        pct = 0
    return (
        f'<div style="background:#f5f5f5;border-radius:3px;height:6px;width:80px;display:inline-block">'
        f'<div style="background:{color};border-radius:3px;height:6px;width:{pct}%"></div>'
        f'</div>'
    )


def build_html(
    week_end: str,
    ig_pulse: dict[str, Any],
    post_rows: list[dict[str, Any]],
    etsy_rows: list[dict[str, Any]],
    prev_ig_pulse: dict[str, Any] | None = None,
    etsy_skipped: bool = False,
) -> str:

    ig = ig_pulse
    p = prev_ig_pulse or {}

    # AI insights
    ai_html = _get_ai_insights(week_end, ig_pulse, prev_ig_pulse, post_rows)
    ai_section = ""
    if ai_html:
        ai_section = f"""
  <div style="background:#f8f4ff;border-left:4px solid #7c4dff;padding:14px 16px;margin-bottom:24px;border-radius:0 6px 6px 0">
    <p style="margin:0 0 6px 0;font-size:12px;color:#7c4dff;font-weight:600;text-transform:uppercase;letter-spacing:0.5px">✦ Weekly Insights</p>
    <div style="font-size:13px;color:#333;line-height:1.6">{ai_html}</div>
  </div>"""

    # Format breakdown
    post_views = ig.get('views_from_posts') or 0
    reel_views = ig.get('views_from_reels') or 0
    max_views = max(float(post_views), float(reel_views), 1)
    format_section = f"""
  <div style="margin-bottom:24px">
    <p style="font-size:13px;color:#555;margin-bottom:8px;font-weight:600">Views by format</p>
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <tr>
        <td style="padding:4px 0;width:60px;color:#1976d2;font-weight:600">Posts</td>
        <td style="padding:4px 8px">{_mini_bar(post_views, max_views, '#1976d2')}</td>
        <td style="padding:4px 0;text-align:right;color:#555">{_fmt(post_views)} views ({_fmt(ig.get('pct_views_from_posts'))}%)</td>
      </tr>
      <tr>
        <td style="padding:4px 0;color:#e91e63;font-weight:600">Reels</td>
        <td style="padding:4px 8px">{_mini_bar(reel_views, max_views, '#e91e63')}</td>
        <td style="padding:4px 0;text-align:right;color:#555">{_fmt(reel_views)} views ({_fmt(ig.get('pct_views_from_reels'))}%)</td>
      </tr>
    </table>
  </div>"""

    # Per-post table
    post_rows_html = ""
    if post_rows:
        for i, post in enumerate(sorted(post_rows, key=lambda x: float(x.get('views') or 0), reverse=True)):
            post_rows_html += _post_row_html(post, i + 1)
    else:
        post_rows_html = '<tr><td colspan="4" style="padding:16px;text-align:center;color:#aaa">No posts this week</td></tr>'

    # Etsy section
    total_etsy_orders = sum(r.get("weekly_orders") or 0 for r in etsy_rows)
    total_etsy_revenue = sum(r.get("weekly_revenue") or 0 for r in etsy_rows)
    top_listings = sorted(etsy_rows, key=lambda r: r.get("weekly_revenue") or 0, reverse=True)[:5]
    listing_rows_html = ""
    for r in top_listings:
        if (r.get("weekly_orders") or 0) > 0:
            listing_rows_html += f"""
        <tr style="border-bottom:1px solid #f5f5f5">
          <td style="padding:7px 8px;font-size:13px">{str(r.get('listing_name',''))[:45]}</td>
          <td style="padding:7px 8px;text-align:right;font-size:13px">{_fmt(r.get('weekly_orders'))}</td>
          <td style="padding:7px 8px;text-align:right;font-size:13px">{_fmt(r.get('weekly_revenue'), prefix='$', decimals=2)}</td>
          <td style="padding:7px 8px;text-align:right;font-size:13px;color:#aaa">{_fmt(r.get('weekly_views'))} views</td>
        </tr>"""

    etsy_note = '<em style="font-size:12px;color:#aaa">(skipped this run)</em>' if etsy_skipped else ""
    etsy_content = ""
    if not etsy_skipped:
        etsy_content = f"""
  <table style="width:100%;border-collapse:collapse;margin-bottom:12px">
    <tr style="background:#fff3e0">
      <td style="padding:8px;font-size:13px"><strong>Total Orders</strong></td>
      <td style="padding:8px;text-align:right;font-size:15px;font-weight:700">{_fmt(total_etsy_orders)}</td>
      <td style="padding:8px;font-size:13px"><strong>Total Revenue</strong></td>
      <td style="padding:8px;text-align:right;font-size:15px;font-weight:700">{_fmt(total_etsy_revenue, prefix='$', decimals=2)}</td>
    </tr>
  </table>
  {"" if not listing_rows_html else f"""
  <p style="font-size:12px;color:#888;margin-bottom:6px">Top listings with sales this week</p>
  <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:24px">
    <tr style="background:#fff8f0;font-size:12px;color:#888">
      <th style="padding:6px 8px;text-align:left;font-weight:600">Listing</th>
      <th style="padding:6px 8px;text-align:right;font-weight:600">Orders</th>
      <th style="padding:6px 8px;text-align:right;font-weight:600">Revenue</th>
      <th style="padding:6px 8px;text-align:right;font-weight:600">Views</th>
    </tr>
    {listing_rows_html}
  </table>"""}"""

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;max-width:640px;margin:0 auto;color:#1a1a1a;padding:24px 16px;background:#ffffff">

  <table style="width:100%;margin-bottom:24px">
    <tr>
      <td>
        <h2 style="margin:0;color:#1a1a1a;font-size:22px">Weekly Analytics</h2>
        <p style="margin:4px 0 0 0;color:#aaa;font-size:13px">Week ending {week_end}</p>
      </td>
      <td style="text-align:right;vertical-align:top">
        <a href="https://docs.google.com/spreadsheets/d/{config.GOOGLE_SPREADSHEET_ID}" 
           style="font-size:12px;color:#aaa;text-decoration:none">View full data ↗</a>
      </td>
    </tr>
  </table>

  {ai_section}

  <!-- IG ACCOUNT METRICS -->
  <h3 style="color:#e91e63;margin:0 0 12px 0;font-size:15px;text-transform:uppercase;letter-spacing:0.5px">📸 Instagram</h3>
  <table style="width:100%;border-collapse:collapse;margin-bottom:20px">
    <tr style="background:#fce4ec">
      <th style="padding:8px;text-align:left;font-size:12px;color:#888;font-weight:600;text-transform:uppercase">Metric</th>
      <th style="padding:8px;text-align:right;font-size:12px;color:#888;font-weight:600;text-transform:uppercase">This Week</th>
      <th style="padding:8px;text-align:right;font-size:12px;color:#888;font-weight:600;text-transform:uppercase">vs Last Week</th>
    </tr>
    <tr>
      <td style="padding:9px 8px;font-size:13px">Reach</td>
      <td style="padding:9px 8px;text-align:right;font-size:14px;font-weight:700">{_fmt(ig.get('account_reach'))}</td>
      <td style="padding:9px 8px;text-align:right">{_pct_change(ig.get('account_reach'), p.get('account_reach'))}</td>
    </tr>
    <tr style="background:#fafafa">
      <td style="padding:9px 8px;font-size:13px">Total Views</td>
      <td style="padding:9px 8px;text-align:right;font-size:14px;font-weight:700">{_fmt(ig.get('total_views'))}</td>
      <td style="padding:9px 8px;text-align:right">{_pct_change(ig.get('total_views'), p.get('total_views'))}</td>
    </tr>
    <tr>
      <td style="padding:9px 8px;font-size:13px">Followers</td>
      <td style="padding:9px 8px;text-align:right;font-size:14px;font-weight:700">{_fmt(ig.get('followers'))}</td>
      <td style="padding:9px 8px;text-align:right">{_pct_change(ig.get('followers'), p.get('followers'))}</td>
    </tr>
    <tr style="background:#fafafa">
      <td style="padding:9px 8px;font-size:13px">Saves</td>
      <td style="padding:9px 8px;text-align:right;font-size:14px;font-weight:700">{_fmt(ig.get('saves'))}</td>
      <td style="padding:9px 8px;text-align:right">{_pct_change(ig.get('saves'), p.get('saves'))}</td>
    </tr>
    <tr>
      <td style="padding:9px 8px;font-size:13px">Shares</td>
      <td style="padding:9px 8px;text-align:right;font-size:14px;font-weight:700">{_fmt(ig.get('shares'))}</td>
      <td style="padding:9px 8px;text-align:right">{_pct_change(ig.get('shares'), p.get('shares'))}</td>
    </tr>
    <tr style="background:#fafafa">
      <td style="padding:9px 8px;font-size:13px">Profile Visits</td>
      <td style="padding:9px 8px;text-align:right;font-size:14px;font-weight:700">{_fmt(ig.get('profile_visits'))}</td>
      <td style="padding:9px 8px;text-align:right">{_pct_change(ig.get('profile_visits'), p.get('profile_visits'))}</td>
    </tr>
    <tr>
      <td style="padding:9px 8px;font-size:13px">Total Interactions</td>
      <td style="padding:9px 8px;text-align:right;font-size:14px;font-weight:700">{_fmt(ig.get('total_interactions'))}</td>
      <td style="padding:9px 8px;text-align:right">{_pct_change(ig.get('total_interactions'), p.get('total_interactions'))}</td>
    </tr>
  </table>

  {format_section}

  <!-- PER POST TABLE -->
  <p style="font-size:13px;color:#555;margin-bottom:8px;font-weight:600">Posts this week <span style="color:#aaa;font-weight:400">(sorted by views)</span></p>
  <table style="width:100%;border-collapse:collapse;margin-bottom:24px;font-size:13px">
    <tr style="background:#fce4ec;font-size:11px;color:#888;text-transform:uppercase">
      <th style="padding:7px 8px;text-align:left;font-weight:600">Format / Date</th>
      <th style="padding:7px 8px;text-align:right;font-weight:600">Views</th>
      <th style="padding:7px 8px;text-align:right;font-weight:600">Saves / Shares</th>
      <th style="padding:7px 8px;text-align:right;font-weight:600">Likes / Watch</th>
    </tr>
    {post_rows_html}
  </table>

  <!-- ETSY -->
  <h3 style="color:#f57c00;margin:0 0 12px 0;font-size:15px;text-transform:uppercase;letter-spacing:0.5px">🛍️ Etsy Shop {etsy_note}</h3>
  {etsy_content if not etsy_skipped else '<p style="color:#aaa;font-size:13px;margin-bottom:24px">Etsy data collection is pending API approval.</p>'}

  <p style="font-size:11px;color:#ccc;border-top:1px solid #f0f0f0;padding-top:12px;margin-top:8px">
    Auto-generated weekly analytics · {week_end}
  </p>

</body>
</html>"""
    return html


# ---------------------------------------------------------------------------
# Send
# ---------------------------------------------------------------------------

def send_digest(
    week_end: str,
    ig_pulse: dict[str, Any],
    post_rows: list[dict[str, Any]],
    etsy_rows: list[dict[str, Any]],
    prev_ig_pulse: dict[str, Any] | None = None,
    etsy_skipped: bool = False,
) -> None:
    print("  Sending weekly email digest...")
    html = build_html(week_end, ig_pulse, post_rows, etsy_rows, prev_ig_pulse, etsy_skipped)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📊 Weekly Analytics — week ending {week_end}"
    msg["From"] = config.EMAIL_SENDER
    msg["To"] = config.EMAIL_RECIPIENT
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(config.EMAIL_SENDER, config.EMAIL_PASSWORD)
        server.sendmail(config.EMAIL_SENDER, config.EMAIL_RECIPIENT, msg.as_string())

    print(f"  Email sent to {config.EMAIL_RECIPIENT}")