"""
Step 1 of the forecast: turn the raw data into monthly history.

Two views, and they are never mixed:
  EVENT view  - what happened in each calendar month (leads that arrived, calls held,
                clients who paid, revenue booked). This is what a manager sees.
  COHORT view - for the leads that ARRIVED in a month, how many went on to pass
                triage, take a call and pay, and how many months later each happened.
                Drivers (rates, timing) are always measured on cohorts.
"""

import pandas as pd

from src.metrics import monthly_activity, snapshot

FULL_DATA_AS_OF = "2026-06-30"


def _months_after(later, earlier):
    """Whole calendar months between two dates (0 = same month)."""
    return (later.dt.year - earlier.dt.year) * 12 + (later.dt.month - earlier.dt.month)


def event_history(leads, revenue, start, end):
    """Calendar-month counts for all channels, start to end (inclusive)."""
    snap = snapshot(leads, FULL_DATA_AS_OF)
    table = monthly_activity(snap, revenue, FULL_DATA_AS_OF)
    months = pd.period_range(start, end, freq="M")
    return table.reindex(months, fill_value=0).rename_axis("month")


def channel_history(leads, revenue, start, end):
    """Calendar-month counts by channel: leads by arrival month, paid and revenue by close month."""
    months = pd.period_range(start, end, freq="M")
    arrived = leads.groupby([leads["inquiry_date"].dt.to_period("M"), "channel_source"]).size()
    won = leads[leads["closed_won"]]
    paid = won.groupby([won["close_date"].dt.to_period("M"), "channel_source"]).size()
    rev = revenue.groupby([revenue["close_date"].dt.to_period("M"), "channel_source"])[
        "total_revenue_bdt"].sum()
    table = pd.DataFrame({"leads": arrived, "paid_clients": paid, "revenue_bdt": rev})
    table.index.names = ["month", "channel"]
    table = table.fillna(0).astype(int).reset_index()
    return table[table["month"].isin(months)].sort_values(["month", "channel"])


def cohort_history(leads):
    """One row per arrival month and channel, with final outcomes and their timing."""
    d = leads.copy()
    d["month"] = d["inquiry_date"].dt.to_period("M")
    d["call_lag"] = _months_after(d["diag_date"], d["inquiry_date"])
    d["close_lag"] = _months_after(d["close_date"], d["inquiry_date"])
    won = d["closed_won"]
    table = d.groupby(["month", "channel_source"]).agg(
        leads=("lead_id", "size"),
        mqls=("reached_mql", "sum"),
        calls=("reached_opp", "sum"),
        paid=("closed_won", "sum"),
        calls_same_month=("call_lag", lambda s: int((s == 0).sum())),
        calls_next_month=("call_lag", lambda s: int((s == 1).sum())),
        paid_same_month=("close_lag", lambda s: int(((s == 0) & won.loc[s.index]).sum())),
        paid_next_month=("close_lag", lambda s: int(((s == 1) & won.loc[s.index]).sum())),
    ).reset_index().rename(columns={"channel_source": "channel"})
    lags = pd.concat([d["call_lag"], d.loc[won, "close_lag"]]).dropna()
    if len(lags) and (lags.max() > 1 or lags.min() < 0):
        raise SystemExit("\nDATA PROBLEM: a call or payment happened outside the month the lead arrived "
                         "or the month after. The forecast timing assumes 0 or 1 month.\n")
    return table
