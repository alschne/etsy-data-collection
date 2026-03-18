"""
email_digest.py — Sends a weekly HTML email summarising key metrics.
Uses Gmail via smtplib + an App Password (no third-party email service needed).
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from typing import Any

import config


def _fmt(value: Any, prefix: str = "", suffix: str = "", decimals: int = 0) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{prefix}{value:,.{decimals}f}{suffix}"
    return f"{prefix}{value:,}{suffix}"


def _pct_change(current: float | None, previous: float | None) -> str:
    if current is None or previous is None or previous == 0:
        return ""
    change = (current - previous) / previous * 100
    arrow = "▲" if change >= 0 else "▼"
    colour = "#2e7d32" if change >= 0 else "#c62828"
    return f' <span style="color:{colour};font-size:12px">{arrow} {abs(change):.1f}%</span>'


def build_html(
    week_end: str,
    ig_pulse: dict[str, Any],
    etsy_rows: list[dict[str, Any]],
    prev_ig_pulse: dict[str, Any] | None = None,
) -> str:
    """Build the HTML email body."""

    ig = ig_pulse
    p = prev_ig_pulse or {}

    total_etsy_orders = sum(r.get("weekly_orders", 0) for r in etsy_rows)
    total_etsy_revenue = sum(r.get("weekly_revenue", 0) for r in etsy_rows)
    top_listings = sorted(etsy_rows, key=lambda r: r.get("weekly_revenue", 0), reverse=True)[:5]

    # Build listing rows HTML
    listing_rows_html = ""
    for r in top_listings:
        listing_rows_html += f"""
        <tr>
          <td style="padding:6px 8px;border-bottom:1px solid #f0f0f0">{r.get('listing_name','')[:45]}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #f0f0f0;text-align:right">{_fmt(r.get('weekly_orders'))}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #f0f0f0;text-align:right">{_fmt(r.get('weekly_revenue'), prefix='$', decimals=2)}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #f0f0f0;text-align:right">{_fmt(r.get('lifetime_views'))}</td>
        </tr>"""

    html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:620px;margin:0 auto;color:#1a1a1a;padding:20px">

  <h2 style="color:#1a1a1a;border-bottom:3px solid #e91e63;padding-bottom:8px;margin-bottom:4px">
    Weekly Analytics Digest
  </h2>
  <p style="color:#777;margin-top:4px;margin-bottom:28px">Week ending {week_end}</p>

  <!-- INSTAGRAM -->
  <h3 style="color:#e91e63;margin-bottom:12px">📸 Instagram</h3>
  <table style="width:100%;border-collapse:collapse;margin-bottom:24px">
    <tr style="background:#fce4ec">
      <th style="padding:8px;text-align:left;font-size:13px">Metric</th>
      <th style="padding:8px;text-align:right;font-size:13px">This Week</th>
      <th style="padding:8px;text-align:right;font-size:13px">vs Last Week</th>
    </tr>
    <tr>
      <td style="padding:8px;border-bottom:1px solid #f5f5f5">Reach</td>
      <td style="padding:8px;border-bottom:1px solid #f5f5f5;text-align:right">{_fmt(ig.get('account_reach'))}</td>
      <td style="padding:8px;border-bottom:1px solid #f5f5f5;text-align:right">{_pct_change(ig.get('account_reach'), p.get('account_reach'))}</td>
    </tr>
    <tr style="background:#fafafa">
      <td style="padding:8px;border-bottom:1px solid #f5f5f5">Impressions</td>
      <td style="padding:8px;border-bottom:1px solid #f5f5f5;text-align:right">{_fmt(ig.get('impressions'))}</td>
      <td style="padding:8px;border-bottom:1px solid #f5f5f5;text-align:right">{_pct_change(ig.get('impressions'), p.get('impressions'))}</td>
    </tr>
    <tr>
      <td style="padding:8px;border-bottom:1px solid #f5f5f5">Followers</td>
      <td style="padding:8px;border-bottom:1px solid #f5f5f5;text-align:right">{_fmt(ig.get('followers'))}</td>
      <td style="padding:8px;border-bottom:1px solid #f5f5f5;text-align:right">{_pct_change(ig.get('followers'), p.get('followers'))}</td>
    </tr>
    <tr style="background:#fafafa">
      <td style="padding:8px;border-bottom:1px solid #f5f5f5">Total Interactions</td>
      <td style="padding:8px;border-bottom:1px solid #f5f5f5;text-align:right">{_fmt(ig.get('total_interactions'))}</td>
      <td style="padding:8px;border-bottom:1px solid #f5f5f5;text-align:right">{_pct_change(ig.get('total_interactions'), p.get('total_interactions'))}</td>
    </tr>
    <tr>
      <td style="padding:8px;border-bottom:1px solid #f5f5f5">Profile Visits</td>
      <td style="padding:8px;border-bottom:1px solid #f5f5f5;text-align:right">{_fmt(ig.get('profile_visits'))}</td>
      <td style="padding:8px;border-bottom:1px solid #f5f5f5;text-align:right">{_pct_change(ig.get('profile_visits'), p.get('profile_visits'))}</td>
    </tr>
    <tr style="background:#fafafa">
      <td style="padding:8px">Link Taps</td>
      <td style="padding:8px;text-align:right">{_fmt(ig.get('external_link_taps'))}</td>
      <td style="padding:8px;text-align:right">{_pct_change(ig.get('external_link_taps'), p.get('external_link_taps'))}</td>
    </tr>
  </table>

  <!-- ETSY -->
  <h3 style="color:#f57c00;margin-bottom:12px">🛍️ Etsy Shop</h3>
  <table style="width:100%;border-collapse:collapse;margin-bottom:16px">
    <tr style="background:#fff3e0">
      <th style="padding:8px;text-align:left;font-size:13px">Summary</th>
      <th style="padding:8px;text-align:right;font-size:13px">This Week</th>
    </tr>
    <tr>
      <td style="padding:8px;border-bottom:1px solid #f5f5f5">Total Orders</td>
      <td style="padding:8px;border-bottom:1px solid #f5f5f5;text-align:right">{_fmt(total_etsy_orders)}</td>
    </tr>
    <tr style="background:#fafafa">
      <td style="padding:8px">Total Revenue</td>
      <td style="padding:8px;text-align:right">{_fmt(total_etsy_revenue, prefix='$', decimals=2)}</td>
    </tr>
  </table>

  <p style="font-size:13px;color:#555;margin-bottom:6px"><strong>Top Listings by Revenue</strong></p>
  <table style="width:100%;border-collapse:collapse;margin-bottom:24px;font-size:13px">
    <tr style="background:#fff3e0">
      <th style="padding:6px 8px;text-align:left">Listing</th>
      <th style="padding:6px 8px;text-align:right">Orders</th>
      <th style="padding:6px 8px;text-align:right">Revenue</th>
      <th style="padding:6px 8px;text-align:right">Lifetime Views</th>
    </tr>
    {listing_rows_html}
  </table>

  <p style="font-size:12px;color:#aaa;border-top:1px solid #eee;padding-top:12px;margin-top:8px">
    Auto-generated by your analytics pipeline · 
    <a href="https://docs.google.com/spreadsheets/d/{config.GOOGLE_SPREADSHEET_ID}" style="color:#aaa">View full spreadsheet</a>
  </p>

</body>
</html>
"""
    return html


def send_digest(
    week_end: str,
    ig_pulse: dict[str, Any],
    etsy_rows: list[dict[str, Any]],
    prev_ig_pulse: dict[str, Any] | None = None,
) -> None:
    print("  Sending weekly email digest...")
    html = build_html(week_end, ig_pulse, etsy_rows, prev_ig_pulse)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📊 Weekly Analytics — week ending {week_end}"
    msg["From"] = config.EMAIL_SENDER
    msg["To"] = config.EMAIL_RECIPIENT
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(config.EMAIL_SENDER, config.EMAIL_PASSWORD)
        server.sendmail(config.EMAIL_SENDER, config.EMAIL_RECIPIENT, msg.as_string())

    print(f"  Email sent to {config.EMAIL_RECIPIENT}")
