"""
main.py — Entry point for the weekly analytics pipeline.

Determines the week window (Mon–Sun), runs all collectors,
writes to Google Sheets, and sends the email digest.

Run manually:  python src/main.py
Scheduled via: .github/workflows/weekly_pipeline.yml
"""

import sys
import traceback
from datetime import datetime, timedelta, timezone

import config
import sheets
import ig_collector
import etsy_collector
import email_digest


def get_week_window() -> tuple[datetime, datetime]:
    """
    Returns (week_start, week_end) for the most recently completed Mon–Sun week.
    Runs on Monday, so 'last week' = the 7 days ending yesterday (Sunday).
    Both timestamps are UTC midnight.
    """
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    # Last Sunday
    days_since_sunday = today.weekday() + 1  # Monday=0, so +1 gives days since Sunday
    week_end = today - timedelta(days=days_since_sunday)
    week_start = week_end - timedelta(days=6)
    return week_start, week_end


def get_previous_ig_pulse(sheet) -> dict | None:
    """Read the last row of ig_pulse to use for week-over-week comparisons in email."""
    try:
        all_rows = sheet.get_all_records()
        if len(all_rows) >= 2:
            return all_rows[-2]  # second to last = previous week (last = current)
        elif len(all_rows) == 1:
            return all_rows[0]
    except Exception:
        pass
    return None


def run():
    week_start, week_end = get_week_window()
    week_end_str = week_end.strftime("%Y-%m-%d")
    print(f"\n{'='*55}")
    print(f"  Analytics pipeline — week ending {week_end_str}")
    print(f"{'='*55}\n")

    errors = []

    # ------------------------------------------------------------------
    # Instagram — ig_pulse
    # ------------------------------------------------------------------
    print("[1/4] IG Pulse (account-level weekly metrics)")
    try:
        ig_pulse_sheet = sheets.get_sheet(config.SHEET_IG_PULSE)
        sheets.ensure_headers(ig_pulse_sheet, ig_collector.IG_PULSE_HEADERS)
        prev_ig = get_previous_ig_pulse(ig_pulse_sheet)

        ig_pulse_data = ig_collector.collect_ig_pulse(week_start, week_end)
        row = ig_collector.row_to_list(ig_pulse_data, ig_collector.IG_PULSE_HEADERS)

        # Upsert by week_end_date (col 0) so re-runs don't duplicate
        sheets.upsert_row(ig_pulse_sheet, row, key_col_index=0)
        print("  ✓ ig_pulse updated\n")
    except Exception as e:
        print(f"  ✗ ig_pulse failed: {e}")
        errors.append(("ig_pulse", str(e)))
        ig_pulse_data = {}
        prev_ig = None

    # ------------------------------------------------------------------
    # Instagram — ig_stars (per-post)
    # ------------------------------------------------------------------
    print("[2/4] IG Stars (per-post metrics)")
    try:
        ig_stars_sheet = sheets.get_sheet(config.SHEET_IG_STARS)
        sheets.ensure_headers(ig_stars_sheet, ig_collector.IG_STARS_HEADERS)
        existing_permalinks = sheets.get_existing_keys(
            ig_stars_sheet,
            key_col_index=ig_collector.IG_STARS_HEADERS.index("permalink"),
        )

        post_rows = ig_collector.collect_ig_stars(week_start, week_end)
        new_posts = 0
        for post in post_rows:
            permalink = post.get("permalink", "")
            if permalink and permalink in existing_permalinks:
                print(f"  Skipping existing post: {permalink}")
                continue
            row = ig_collector.row_to_list(post, ig_collector.IG_STARS_HEADERS)
            sheets.append_row(ig_stars_sheet, row)
            new_posts += 1

        print(f"  ✓ ig_stars updated — {new_posts} new post(s) added\n")
    except Exception as e:
        print(f"  ✗ ig_stars failed: {e}")
        errors.append(("ig_stars", str(e)))
        post_rows = []

    # ------------------------------------------------------------------
    # Etsy — etsy_stars (per-listing)
    # ------------------------------------------------------------------
    print("[3/4] Etsy Stars (per-listing weekly metrics)")
    try:
        etsy_stars_sheet = sheets.get_sheet(config.SHEET_ETSY_STARS)
        sheets.ensure_headers(etsy_stars_sheet, etsy_collector.ETSY_STARS_HEADERS)

        etsy_rows = etsy_collector.collect_etsy_stars(week_start, week_end)

        # Upsert by composite key: week_end_date + listing_id
        # We encode as "date|listing_id" stored in a hidden helper — actually
        # simplest to just check if this week's date already has rows and skip.
        existing_keys = sheets.get_existing_keys(etsy_stars_sheet, key_col_index=0)
        if week_end_str in existing_keys:
            print(f"  Etsy data for {week_end_str} already exists — skipping.")
        else:
            for r in etsy_rows:
                row = etsy_collector.row_to_list(r, etsy_collector.ETSY_STARS_HEADERS)
                sheets.append_row(etsy_stars_sheet, row)
            print(f"  ✓ etsy_stars updated — {len(etsy_rows)} listing(s) written\n")
    except Exception as e:
        print(f"  ✗ etsy_stars failed: {e}")
        errors.append(("etsy_stars", str(e)))
        etsy_rows = []

    # ------------------------------------------------------------------
    # Email digest
    # ------------------------------------------------------------------
    print("[4/4] Sending email digest")
    try:
        email_digest.send_digest(
            week_end=week_end_str,
            ig_pulse=ig_pulse_data,
            etsy_rows=etsy_rows,
            prev_ig_pulse=prev_ig,
        )
        print("  ✓ Email sent\n")
    except Exception as e:
        print(f"  ✗ Email failed: {e}")
        errors.append(("email", str(e)))

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print(f"{'='*55}")
    if errors:
        print(f"  Pipeline finished with {len(errors)} error(s):")
        for step, msg in errors:
            print(f"    • {step}: {msg}")
        sys.exit(1)
    else:
        print("  Pipeline finished successfully ✓")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    run()
