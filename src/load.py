"""
Step 1 of the pipeline: load the three Zorora files and join them into one table.

What this file does, in order:
  1. Reads settings from config/settings.json.
  2. Reads the contacts, pipeline and revenue CSVs.
  3. Drops personal columns (names) as soon as the file is read.
  4. Joins contacts onto the pipeline so each lead is one row with all its dates
     and attributes (channel, gate version, handler, destination, student type).
  5. Runs basic sanity checks and stops with a clear message if the files are wrong.
"""

import json
from pathlib import Path

import pandas as pd

# The project folder is the folder above src/
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Columns that identify a person. Removed on load and never used anywhere.
PERSONAL_COLUMNS = ["first_name", "last_name", "company"]

# Stage dates in the pipeline file, in funnel order
STAGE_DATES = ["inquiry_date", "mql_date", "sql_date", "diag_date", "close_date"]


def load_settings():
    """Read config/settings.json and return it as a dictionary."""
    with open(PROJECT_ROOT / "config" / "settings.json", encoding="utf-8") as f:
        return json.load(f)


def _read_csv(path, date_columns):
    """Read one CSV with fixed encoding and fixed date format (YYYY-MM-DD).

    Fixing the format means Windows regional settings can't change how dates are read.
    """
    df = pd.read_csv(path, encoding="utf-8")
    for col in date_columns:
        df[col] = pd.to_datetime(df[col], format="%Y-%m-%d", errors="raise")
    return df


def load_data(settings=None):
    """Return two tables: leads (one row per lead) and revenue (one row per paid client)."""
    settings = settings or load_settings()
    folder = PROJECT_ROOT / settings["data_folder"]
    files = settings["files"]

    contacts = _read_csv(folder / files["contacts"], ["inquiry_date"])
    pipeline = _read_csv(folder / files["pipeline"], STAGE_DATES)
    revenue = _read_csv(folder / files["revenue"], ["close_date"])

    # Drop names straight away
    contacts = contacts.drop(columns=[c for c in PERSONAL_COLUMNS if c in contacts.columns])

    # Sanity checks: stop early with a plain message if something is off
    _check(contacts["lead_id"].is_unique, "contacts file has duplicate lead IDs")
    _check(pipeline["lead_id"].is_unique, "pipeline file has duplicate lead IDs")
    _check(set(contacts["lead_id"]) == set(pipeline["lead_id"]),
           "contacts and pipeline files do not contain the same leads")
    won_ids = set(pipeline.loc[pipeline["closed_won"], "lead_id"])
    _check(set(revenue["lead_id"]) == won_ids,
           "revenue file does not match the closed-won leads in the pipeline")

    # One row per lead: pipeline dates + contact attributes
    attributes = contacts.drop(columns=["inquiry_date"])
    leads = pipeline.merge(attributes, on="lead_id", how="left", validate="one_to_one")

    # Every stage a lead reached must have a date (the as-of logic depends on this)
    for flag, date_col in [("reached_mql", "mql_date"), ("reached_sql", "sql_date"),
                           ("reached_opp", "diag_date"), ("closed_won", "close_date")]:
        _check(leads.loc[leads[flag], date_col].notna().all(),
               f"some leads have {flag} = True but no {date_col}")

    return leads, revenue


def _check(condition, message):
    if not condition:
        raise SystemExit(f"\nDATA PROBLEM: {message}. Nothing was calculated.\n")
