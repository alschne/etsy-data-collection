"""
sheets.py — Google Sheets read/write helpers using gspread.

All tabs are treated the same way:
  - First row is always the header row.
  - The script appends new rows; it never overwrites existing data.
  - For ig_stars and etsy_stars, we upsert by a unique key so re-running
    the script doesn't duplicate rows.
"""

import json
import gspread
from google.oauth2.service_account import Credentials
from typing import Any

import config


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_sheet(tab_name: str) -> gspread.Worksheet:
    creds = Credentials.from_service_account_info(
        config.GOOGLE_SERVICE_ACCOUNT_JSON, scopes=SCOPES
    )
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(config.GOOGLE_SPREADSHEET_ID)
    try:
        return spreadsheet.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        raise ValueError(
            f"Tab '{tab_name}' not found in spreadsheet. "
            "Please create it manually first (see README)."
        )


def ensure_headers(sheet: gspread.Worksheet, headers: list[str]) -> None:
    """Write headers if the sheet is empty."""
    existing = sheet.row_values(1)
    if not existing:
        sheet.append_row(headers, value_input_option="USER_ENTERED")


def append_row(sheet: gspread.Worksheet, row: list[Any]) -> None:
    sheet.append_row(row, value_input_option="USER_ENTERED")


def upsert_row(
    sheet: gspread.Worksheet,
    row: list[Any],
    key_col_index: int = 0,
) -> None:
    """
    Insert the row if the key value (row[key_col_index]) doesn't exist yet.
    If it does exist, skip — we don't overwrite historical data.

    key_col_index is 0-based for the row list, but gspread uses 1-based cols.
    """
    key_value = str(row[key_col_index])
    # Get all values in the key column (col is 1-based)
    col_values = sheet.col_values(key_col_index + 1)
    if key_value in col_values:
        print(f"  Skipping existing row with key: {key_value}")
        return
    sheet.append_row(row, value_input_option="USER_ENTERED")
    print(f"  Appended new row with key: {key_value}")


def get_existing_keys(sheet: gspread.Worksheet, key_col_index: int = 0) -> set[str]:
    """Return all existing values in the key column as a set."""
    return set(sheet.col_values(key_col_index + 1))
