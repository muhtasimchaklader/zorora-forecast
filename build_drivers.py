"""
Session 1 command. Run from the project folder:

    python build_drivers.py

What it does, in order:
  1. Loads the data (names removed) and runs the 26 locked-number checks. Stops if any fail.
  2. Builds the monthly history (event view and cohort view).
  3. Measures two driver sets: base (Jun 2025 - May 2026) and backtest (2024 only).
  4. Runs the Session 1 checks. Stops if any fail.
  5. Saves everything to outputs/ for the Excel model (Session 2).
"""

import sys

import pandas as pd

from src.drivers import build_driver_set, rebuild_paid
from src.history import channel_history, cohort_history, event_history
from src.load import PROJECT_ROOT, load_data, load_settings
from src.locked_checks import run_locked_checks


def main():
    s = load_settings()
    leads, revenue = load_data(s)
    out = PROJECT_ROOT / "outputs"
    out.mkdir(exist_ok=True)

    # 1. Locked numbers first
    locked = run_locked_checks(leads, revenue)
    locked.to_csv(out / "locked_checks.csv", index=False)
    if (locked["result"] == "FAIL").any():
        print(locked[locked["result"] == "FAIL"].to_string(index=False))
        sys.exit("\nSTOPPED: locked numbers do not match. Send Claude the lines above.")
    print(f"1. Locked numbers: all {len(locked)} checks passed.")

    # 2. History
    start, end = s["history_start_month"], s["history_end_month"]
    events = event_history(leads, revenue, start, end)
    by_channel = channel_history(leads, revenue, start, end)
    cohorts = cohort_history(leads)
    events.to_csv(out / "history_monthly.csv")
    by_channel.to_csv(out / "history_by_channel.csv", index=False)
    cohorts.to_csv(out / "history_cohorts.csv", index=False)
    print(f"2. History: {len(events)} months, {start} to {end}.")

    # 3. Driver sets
    md = s["min_denominator"]
    sets = {
        "base": build_driver_set(cohorts, revenue, s["base_window"], md,
                                 season_window=(start, end)),
        "backtest": build_driver_set(cohorts, revenue, s["backtest_window"], md),
    }
    for name, d in sets.items():
        d["channels"].assign(driver_set=name).to_csv(out / f"drivers_{name}_channels.csv", index=False)
        d["seasonality"].to_csv(out / f"drivers_{name}_seasonality.csv", index=False)
        d["ranges"].to_csv(out / f"drivers_{name}_ranges.csv", index=False)
        pd.DataFrame([{**d["timing"], "revenue_per_client": round(d["revenue_per_client"]),
                       "revenue_per_client_based_on": d["revenue_per_client_based_on"]}]
                     ).to_csv(out / f"drivers_{name}_other.csv", index=False)
    print("3. Drivers measured: base (Jun 2025 to May 2026) and backtest (2024).")

    # 4. Checks
    results = run_session_checks(leads, revenue, events, cohorts, sets, s)
    results.to_csv(out / "session1_checks.csv", index=False)
    print("4. Session 1 checks:")
    print(results.to_string(index=False))
    if (results["result"] == "FAIL").any():
        sys.exit("\nSTOPPED: a check failed. Send Claude the FAIL lines.")

    print_summary(sets, cohorts, s)
    print("\nALL CHECKS PASSED. Files saved in outputs/. Session 1 done.")


def run_session_checks(leads, revenue, events, cohorts, sets, s):
    rows = []

    def check(name, ok, detail):
        rows.append({"check": name, "result": "PASS" if ok else "FAIL", "detail": detail})

    # History ties back to the raw data and the locked figures
    check("Cohort table holds every lead", cohorts["leads"].sum() == len(leads),
          f"{cohorts['leads'].sum()} of {len(leads)}")
    check("Cohort table holds every paid client", cohorts["paid"].sum() == leads["closed_won"].sum(),
          f"{cohorts['paid'].sum()} of {int(leads['closed_won'].sum())}")
    timed = (cohorts["calls_same_month"] + cohorts["calls_next_month"] == cohorts["calls"]).all() and \
        (cohorts["paid_same_month"] + cohorts["paid_next_month"] == cohorts["paid"]).all()
    check("Every call and payment is in the arrival month or the next", timed,
          "timing columns add up to the totals")
    by_year = events.groupby(events.index.year)["paid_clients"].sum()
    check("History: paid clients in 2024 = 27 (locked)", by_year.get(2024) == 27, by_year.get(2024))
    check("History: paid clients in 2025 = 50 (locked)", by_year.get(2025) == 50, by_year.get(2025))
    check("History: revenue Jan 2024 to May 2026 = BDT 3,160,500",
          events["revenue_bdt"].sum() == 3_160_500, f"{events['revenue_bdt'].sum():,}")

    tol = s["rebuild_tolerance"]
    for name, d in sets.items():
        ch = d["channels"]
        rates = ch[["mql_rate", "call_rate", "call_to_paid"]].stack()
        check(f"{name}: every rate between 0 and 100%", rates.between(0, 1).all(),
              f"min {rates.min():.1%}, max {rates.max():.1%}")
        season = d["seasonality"]["index"]
        check(f"{name}: seasonality averages exactly 1", abs(season.mean() - 1) < 1e-9,
              f"{season.mean():.6f}")
        t = d["timing"]
        check(f"{name}: timing shares between 0 and 1",
              all(0 <= v <= 1 for v in t.values()),
              ", ".join(f"{k} {v:.0%}" for k, v in t.items()))
        r = d["ranges"]
        check(f"{name}: low <= base <= high for every driver",
              ((r["low"] <= 1) & (r["high"] >= 1)).all(),
              "; ".join(f"{x.driver} {x.low:.2f}-{x.high:.2f}" for x in r.itertuples()))
        window = s["base_window"] if name == "base" else s["backtest_window"]
        w = cohorts[(cohorts["month"] >= pd.Period(window[0], "M")) &
                    (cohorts["month"] <= pd.Period(window[1], "M"))]
        actual = int(w["paid"].sum())
        rebuilt = rebuild_paid(ch)
        check(f"{name}: drivers rebuild the window's paid clients within {tol:.0%}",
              abs(rebuilt - actual) <= tol * actual, f"rebuilt {rebuilt:.1f} vs actual {actual}")
    return pd.DataFrame(rows)


def print_summary(sets, cohorts, s):
    print("\nWhat the drivers say (base = Jun 2025 to May 2026):")
    ch = sets["base"]["channels"]
    show = ch[["channel", "leads_in_window", "mql_rate", "mql_rate_source", "call_rate",
               "call_rate_source", "call_to_paid", "call_to_paid_source"]].copy()
    for c in ["mql_rate", "call_rate", "call_to_paid"]:
        show[c] = show[c].map(lambda x: f"{x:.1%}")
    print(show.to_string(index=False))
    b = sets["base"]
    print(f"Revenue per paid client: BDT {b['revenue_per_client']:,.0f} "
          f"(average of {b['revenue_per_client_based_on']} clients)")
    print(f"Timing: {b['timing']['calls_same_month_share']:.0%} of calls and "
          f"{b['timing']['paid_same_month_share']:.0%} of payments land in the month the lead "
          "arrived; the rest land the month after.")
    bt = sets["backtest"]["channels"]
    print(f"\nBacktest drivers (2024 only) know {len(bt)} channels: {', '.join(bt['channel'])}.")


if __name__ == "__main__":
    main()
