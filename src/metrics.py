"""
Step 2 of the pipeline: the as-of view and the metric calculations.

THE AS-OF IDEA
A monthly report is written at month end. On that day you only know what has
happened so far. A lead that pays two weeks later is still "open" in that report.
snapshot() rebuilds that view: it keeps leads that had arrived by the as-of date,
and marks each stage as reached only if its date is on or before the as-of date.

METRIC DEFINITIONS (locked, from the Zorora project files)
  Paid clients        = closed-won leads, counted in the month they closed
  MQL rate            = leads that reached MQL / all leads in the group
  Triage pass         = MQL rate, split by channel
  Close rate          = closed-won leads / all leads in the group
  Diagnostic-to-close = closed-won leads / leads that reached a diagnostic call
Counts use the month an event happened. Rates use the month the lead arrived
(the inquiry cohort). The two are never mixed in one figure.
"""

import pandas as pd

# Stage flag name -> the date column that proves it happened
STAGES = {
    "mql": "mql_date",
    "sql": "sql_date",
    "diag": "diag_date",
    "won": "close_date",
}


def snapshot(leads, as_of):
    """Return the leads known at the as-of date, with stage flags as of that date.

    Adds columns: mql, sql, diag, won (True/False as of the date).
    """
    as_of = pd.Timestamp(as_of)
    known = leads[leads["inquiry_date"] <= as_of].copy()
    for flag, date_col in STAGES.items():
        known[flag] = known[date_col].notna() & (known[date_col] <= as_of)
    # A lead only counts as won if the pipeline file says it was won
    known["won"] = known["won"] & known["closed_won"]
    return known


def funnel(group):
    """Counts and rates for any group of leads (already passed through snapshot)."""
    n = len(group)
    mql = int(group["mql"].sum())
    diag = int(group["diag"].sum())
    won = int(group["won"].sum())
    return {
        "leads": n,
        "mql": mql,
        "diag": diag,
        "won": won,
        "mql_rate": _rate(mql, n),
        "close_rate": _rate(won, n),
        "diag_to_close": _rate(won, diag),
    }


def funnel_by(snap, column):
    """funnel() for each value of a column, e.g. channel_source or gate_version."""
    rows = {key: funnel(g) for key, g in snap.groupby(column)}
    return pd.DataFrame(rows).T


def monthly_activity(snap, revenue, as_of):
    """Counts per calendar month, up to the as-of date.

    Each count uses the month the event happened:
    leads by inquiry month, MQLs by MQL month, calls by call month,
    paid clients and revenue by close month.
    """
    as_of = pd.Timestamp(as_of)
    parts = {
        "leads": snap["inquiry_date"],
        "mqls": snap.loc[snap["mql"], "mql_date"],
        "diagnostic_calls": snap.loc[snap["diag"], "diag_date"],
        "paid_clients": snap.loc[snap["won"], "close_date"],
    }
    table = pd.DataFrame({
        name: dates.dt.to_period("M").value_counts() for name, dates in parts.items()
    })
    paid_revenue = revenue[revenue["close_date"] <= as_of]
    table["revenue_bdt"] = paid_revenue.groupby(
        paid_revenue["close_date"].dt.to_period("M"))["total_revenue_bdt"].sum()
    table = table.fillna(0).astype(int).sort_index()
    table.index.name = "month"
    return table


def _rate(numerator, denominator):
    """Share as a decimal. Returns None when there is nothing to divide by."""
    return None if denominator == 0 else numerator / denominator
