"""
Step 2 of the forecast: measure the drivers from the cohort history.

THE DRIVER CHAIN (one channel, one month)
  leads  x  triage pass (MQL rate)  =  MQLs
  MQLs   x  call rate               =  diagnostic calls
  calls  x  call-to-paid rate       =  paid clients
  paid   x  revenue per client      =  revenue
Calls and payments land in the arrival month or the month after (timing shares).

WHERE EACH DRIVER COMES FROM
  Lead volume       each channel's leads in the window (12 months)
  Seasonality       each calendar month's share of a normal year, all channels together
  Rates             the window's cohorts; a channel uses its own rate only when at least
                    min_denominator (20) leads, MQLs or calls sit behind it, otherwise
                    the all-channel rate for that stage
  Revenue/client    average revenue of clients who paid in the window
  Low / high        the weakest and strongest quarter inside the window, as a multiplier
                    on the base (one multiplier per driver, applied to every channel)

Two driver sets are built the same way:
  base      Jun 2025 - May 2026, the current process (gates v2 and v3)
  backtest  Jan - Dec 2024, what a forecaster knew at the end of 2024
"""

import pandas as pd

STAGES = [  # (driver name, numerator column, denominator column)
    ("mql_rate", "mqls", "leads"),
    ("call_rate", "calls", "mqls"),
    ("call_to_paid", "paid", "calls"),
]


def _window(table, window, column="month"):
    start, end = (pd.Period(w, "M") for w in window)
    return table[(table[column] >= start) & (table[column] <= end)]


def channel_drivers(cohorts, window, min_den):
    """Leads per year and stage rates for each channel in the window."""
    w = _window(cohorts, window)
    by_ch = w.groupby("channel")[["leads", "mqls", "calls", "paid"]].sum()
    total = by_ch.sum()
    rows = []
    for ch, r in by_ch.iterrows():
        row = {"channel": ch, "leads_in_window": int(r["leads"])}
        for name, num, den in STAGES:
            if r[den] >= min_den:
                row[name], row[f"{name}_source"] = r[num] / r[den], "own"
            else:
                row[name], row[f"{name}_source"] = total[num] / total[den], "all channels"
            row[f"{name}_based_on"] = f"{int(r[num])}/{int(r[den])}"
        rows.append(row)
    return pd.DataFrame(rows)


def seasonality(cohorts, window_or_range):
    """Each calendar month's lead volume as a multiple of an average month (average = 1)."""
    w = _window(cohorts, window_or_range)
    monthly = w.groupby("month")["leads"].sum()
    by_month_of_year = monthly.groupby(monthly.index.month).mean()
    if len(by_month_of_year) != 12:
        raise SystemExit("\nSeasonality needs every calendar month at least once.\n")
    index = by_month_of_year / by_month_of_year.mean()
    return index.rename_axis("month_of_year").rename("index").reset_index()


def timing(cohorts, window):
    """Share of calls and payments that land in the arrival month (the rest land a month later)."""
    w = _window(cohorts, window)
    calls_0, calls_1 = w["calls_same_month"].sum(), w["calls_next_month"].sum()
    paid_0, paid_1 = w["paid_same_month"].sum(), w["paid_next_month"].sum()
    return {"calls_same_month_share": calls_0 / (calls_0 + calls_1),
            "paid_same_month_share": paid_0 / (paid_0 + paid_1)}


def revenue_per_client(revenue, window):
    r = revenue.assign(month=revenue["close_date"].dt.to_period("M"))
    w = _window(r, window)
    return w["total_revenue_bdt"].mean(), len(w)


def _quarters(window):
    months = pd.period_range(*window, freq="M")
    return [(months[i], months[i + 2]) for i in range(0, len(months), 3)]


def ranges(cohorts, revenue, window, season, lead_range_measurable=True):
    """Low and high multipliers from the weakest and strongest quarter in the window.

    Lead volume is judged against the seasonal pattern. When that pattern was measured on
    the same single year (the backtest), every quarter matches it by construction, so no
    lead range can be measured and lead volume stays at the base.
    """
    w = _window(cohorts, window)
    season_by_moy = season.set_index("month_of_year")["index"]
    base_monthly_leads = w["leads"].sum() / 12
    base = {name: w[num].sum() / w[den].sum() for name, num, den in STAGES}
    rpc_base, _ = revenue_per_client(revenue, window)

    rows = {"lead_volume": [], "mql_rate": [], "call_rate": [], "call_to_paid": [],
            "revenue_per_client": []}
    for first, last in _quarters(window):
        q = _window(cohorts, (str(first), str(last)))
        months = pd.period_range(first, last, freq="M")
        expected = base_monthly_leads * season_by_moy.loc[[m.month for m in months]].sum()
        rows["lead_volume"].append(q["leads"].sum() / expected)
        for name, num, den in STAGES:
            rows[name].append((q[num].sum() / q[den].sum()) / base[name])
        rpc_q, _ = revenue_per_client(revenue, (str(first), str(last)))
        rows["revenue_per_client"].append(rpc_q / rpc_base)

    table = pd.DataFrame([{"driver": k, "low": min(v), "base": 1.0, "high": max(v),
                           "quarters": " / ".join(f"{x:.2f}" for x in v)}
                          for k, v in rows.items()])
    if not lead_range_measurable:
        table.loc[table["driver"] == "lead_volume", ["low", "high", "quarters"]] = [
            1.0, 1.0, "not measurable: only one year of history"]
    return table


def build_driver_set(cohorts, revenue, window, min_den, season_window=None):
    """Everything the model needs for one driver set."""
    season = seasonality(cohorts, season_window or window)
    rpc, n_paid = revenue_per_client(revenue, window)
    return {
        "channels": channel_drivers(cohorts, window, min_den),
        "seasonality": season,
        "timing": timing(cohorts, window),
        "revenue_per_client": rpc,
        "revenue_per_client_based_on": n_paid,
        "ranges": ranges(cohorts, revenue, window, season,
                         lead_range_measurable=season_window is not None),
    }


def rebuild_paid(channels):
    """Paid clients the drivers imply for the window they were measured on."""
    c = channels
    return float((c["leads_in_window"] * c["mql_rate"] * c["call_rate"] * c["call_to_paid"]).sum())
