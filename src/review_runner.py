"""
review_runner.py — Entry point for quarterly and annual review emails.

Called by GitHub Actions on schedule, or manually with flags.

Usage:
    python src/review_runner.py --quarterly        # current quarter
    python src/review_runner.py --annual           # current year
    python src/review_runner.py --quarterly --q 1 --year 2026   # specific quarter
    python src/review_runner.py --annual --year 2025             # specific year
    python src/review_runner.py --all              # quarterly + annual (Dec 31 use)
"""

import argparse
import sys
from datetime import datetime, timezone

import review_digest


def run():
    parser = argparse.ArgumentParser(description="Quarterly/annual review email")
    parser.add_argument("--quarterly", action="store_true")
    parser.add_argument("--annual", action="store_true")
    parser.add_argument("--all", action="store_true", help="Run both quarterly and annual")
    parser.add_argument("--q", type=int, choices=[1, 2, 3, 4], help="Quarter number")
    parser.add_argument("--year", type=int, help="Year (defaults to current)")
    args = parser.parse_args()

    if not any([args.quarterly, args.annual, args.all]):
        parser.print_help()
        sys.exit(1)

    errors = []

    if args.quarterly or args.all:
        try:
            review_digest.run_quarterly_review(quarter=args.q, year=args.year)
        except Exception as e:
            print(f"  ✗ Quarterly review failed: {e}")
            errors.append(str(e))

    if args.annual or args.all:
        try:
            review_digest.run_annual_review(year=args.year)
        except Exception as e:
            print(f"  ✗ Annual review failed: {e}")
            errors.append(str(e))

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    run()
