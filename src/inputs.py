"""
Collects every input the forecast needs, from the Session 1 outputs, into one dictionary.

Both the Excel builder (build_model.py) and the Python copy of the model (src/model.py)
read from here, so the workbook and the check always start from the same numbers.
"""

import pandas as pd

from src.load import PROJECT_ROOT, load_settings

DRIVERS = ["lead_volume", "mql_rate", "call_rate", "call_to_paid", "revenue_per_client"]
DRIVER_LABELS = {
    "lead_volume": "Lead volume",
    "mql_rate": "Triage pass",
    "call_rate": "Call rate",
    "call_to_paid": "Call-to-paid",
    "revenue_per_client": "Revenue per client",
}
CASES = ["low", "base", "high"]


def _out(name):
    path = PROJECT_ROOT / "outputs" / name
    if not path.exists():
        raise SystemExit(f"\n{name} is missing. Run python build_drivers.py first.\n")
    return pd.read_csv(path)


def forecast_months(settings):
    start = pd.Period(settings["forecast_start_month"], "M")
    return [start + i for i in range(settings["forecast_months"])]


def load_inputs():
    s = load_settings()
    months = forecast_months(s)

    base_ch = _out("drivers_base_channels.csv").set_index("channel")
    base_season = _out("drivers_base_seasonality.csv").set_index("month_of_year")["index"]
    base_ranges = _out("drivers_base_ranges.csv").set_index("driver")
    base_other = _out("drivers_base_other.csv").iloc[0]

    bt_ch = _out("drivers_backtest_channels.csv").set_index("channel")
    bt_season = _out("drivers_backtest_seasonality.csv").set_index("month_of_year")["index"]
    bt_other = _out("drivers_backtest_other.csv").iloc[0]

    cohorts = _out("history_cohorts.csv")
    cohorts["month"] = cohorts["month"].map(lambda m: pd.Period(m, "M"))
    events = _out("history_monthly.csv")
    events["month"] = events["month"].map(lambda m: pd.Period(m, "M"))

    last_hist = pd.Period(s["history_end_month"], "M")
    carry = cohorts[cohorts["month"] == last_hist]

    y2024 = cohorts[cohorts["month"].map(lambda m: m.year) == 2024]
    y2025 = cohorts[cohorts["month"].map(lambda m: m.year) == 2025]
    dec2024 = cohorts[cohorts["month"] == pd.Period("2024-12", "M")]
    all_hist = cohorts[(cohorts["month"] >= pd.Period(s["history_start_month"], "M")) &
                       (cohorts["month"] <= last_hist)]

    channels = list(base_ch.index)
    bt_channels = list(bt_ch.index)
    sums = lambda df: df.groupby("channel")[["leads", "mqls", "calls", "paid"]].sum()

    return {
        "settings": s,
        "months": months,
        "channels": channels,
        "base": {
            "leads12": base_ch["leads_in_window"].astype(float).to_dict(),
            "mql_rate": base_ch["mql_rate"].to_dict(),
            "call_rate": base_ch["call_rate"].to_dict(),
            "call_to_paid": base_ch["call_to_paid"].to_dict(),
            "based_on": {c: {k: base_ch.loc[c, f"{k}_based_on"] for k in
                             ["mql_rate", "call_rate", "call_to_paid"]} for c in channels},
            "source": {c: {k: base_ch.loc[c, f"{k}_source"] for k in
                           ["mql_rate", "call_rate", "call_to_paid"]} for c in channels},
            "season": {int(k): v for k, v in base_season.items()},
            "ranges": {d: {"low": base_ranges.loc[d, "low"], "base": 1.0,
                           "high": base_ranges.loc[d, "high"],
                           "quarters": base_ranges.loc[d, "quarters"]} for d in DRIVERS},
            "calls_same": float(base_other["calls_same_month_share"]),
            "paid_same": float(base_other["paid_same_month_share"]),
            "rpc": float(base_other["revenue_per_client"]),
            "rpc_based_on": int(base_other["revenue_per_client_based_on"]),
        },
        # Scenario levers (100% = no change). Session 3's AI scenarios change these.
        "levers": {
            "growth": 0.0,
            "lead_adj": {c: [1.0] * len(months) for c in channels},
            "mql_adj": {c: 1.0 for c in channels},
            "call_adj": {c: 1.0 for c in channels},
            "paid_adj": {c: 1.0 for c in channels},
            "rpc_adj": 1.0,
        },
        "carry_in": {"calls": int(carry["calls_next_month"].sum()),
                     "paid": int(carry["paid_next_month"].sum())},
        "capacity": {"leads_per_operator": s["leads_per_operator"],
                     "calls_per_operator": s["calls_per_operator"],
                     "planned": [1] * len(months)},
        "backtest": {
            "channels": bt_channels,
            "leads": bt_ch["leads_in_window"].astype(float).to_dict(),
            "mql_rate": bt_ch["mql_rate"].to_dict(),
            "call_rate": bt_ch["call_rate"].to_dict(),
            "call_to_paid": bt_ch["call_to_paid"].to_dict(),
            "pooled": {"leads": int(y2024["leads"].sum()), "mqls": int(y2024["mqls"].sum()),
                       "calls": int(y2024["calls"].sum()), "paid": int(y2024["paid"].sum())},
            "season": {int(k): v for k, v in bt_season.items()},
            "calls_same": float(bt_other["calls_same_month_share"]),
            "paid_same": float(bt_other["paid_same_month_share"]),
            "rpc": float(bt_other["revenue_per_client"]),
            "dec_leads": sums(dec2024)["leads"].reindex(bt_channels, fill_value=0).astype(int).to_dict(),
            "actual_2025": sums(y2025).reindex(channels, fill_value=0).astype(int).to_dict("index"),
        },
        "history": events,
        "full_history_rates": sums(all_hist).reindex(channels).to_dict("index"),
    }
