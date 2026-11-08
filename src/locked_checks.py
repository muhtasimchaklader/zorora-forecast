"""
Step 0 of every run: prove the pipeline reproduces Zorora's locked numbers.

The locked numbers were verified in July 2026 and must never change.
If the code produces anything different, the CODE is wrong, so the run stops.

There are two kinds of check here:
  A. Full-data checks: on all the data, every locked number must come out exactly.
  B. As-of checks: a report dated in the past must not "see" anything after its date.
"""

import pandas as pd

from src.metrics import funnel, funnel_by, snapshot

FULL_DATA_AS_OF = "2026-06-30"   # end of the last month in the files


def run_locked_checks(leads, revenue):
    """Run every check. Returns a table of results (one row per check)."""
    results = []

    def check(name, expected, actual):
        results.append({"check": name, "expected": expected, "actual": actual,
                        "result": "PASS" if expected == actual else "FAIL"})

    def pct(x):
        return None if x is None else round(x * 100, 1)

    # ---------- A. Full-data checks ----------
    snap = snapshot(leads, FULL_DATA_AS_OF)
    check("Total leads", 1458, len(snap))
    check("Lifetime paid students", 120, int(snap["won"].sum()))
    check("Lifetime revenue (BDT)", 3_610_000, int(revenue["total_revenue_bdt"].sum()))

    closes = snap.loc[snap["won"], "close_date"]
    check("Paid clients closed in 2024", 27, int((closes.dt.year == 2024).sum()))
    check("Paid clients closed in 2025", 50, int((closes.dt.year == 2025).sum()))
    # Label corrected 27 Oct 2026 (option A): the locked 30 covers Jan-Jun 2026,
    # because 4 clients closed in June 2026 under the CSV dates.
    check("Paid clients closed Jan-Jun 2026", 30,
          int(((closes >= "2026-01-01") & (closes <= "2026-06-30")).sum()))

    by_gate = funnel_by(snap, "gate_version")
    for gate, expected_rate in [("v0b", 4.9), ("v1", 5.7), ("v2", 10.3), ("v3", 12.1)]:
        check(f"Close rate, gate {gate} (%)", expected_rate, pct(by_gate.loc[gate, "close_rate"]))
    check("Gate v0b: paid / leads", "37/750",
          f"{int(by_gate.loc['v0b', 'won'])}/{int(by_gate.loc['v0b', 'leads'])}")
    check("Gate v3: paid / leads", "48/396",
          f"{int(by_gate.loc['v3', 'won'])}/{int(by_gate.loc['v3', 'leads'])}")
    for gate, expected_calls in [("v0b", 67), ("v1", 11), ("v2", 27), ("v3", 58)]:
        check(f"Diagnostic calls, gate {gate}", expected_calls, int(by_gate.loc[gate, "diag"]))

    cohort = snap[(snap["inquiry_date"] >= "2026-01-01") & (snap["inquiry_date"] <= "2026-05-31")]
    c = funnel(cohort)
    check("Jan-May 2026 cohort: leads -> MQL -> paid", "151 -> 58 -> 22",
          f"{c['leads']} -> {c['mql']} -> {c['won']}")
    check("Jan-May 2026 cohort close rate (%)", 14.6, pct(c["close_rate"]))

    by_channel = funnel_by(snap, "channel_source")
    for channel, expected in [("Educator Referral", 45.7), ("Warm Referral", 61.4), ("Facebook", 5.5)]:
        check(f"Triage pass, {channel} (%)", expected, pct(by_channel.loc[channel, "mql_rate"]))

    by_handler = funnel_by(snap, "handled_by")
    # Operators are shown by role, not name, in the public data
    check("Operator 2 (from Mar 2025): paid / leads", "74/687",
          f"{int(by_handler.loc['Operator 2', 'won'])}/{int(by_handler.loc['Operator 2', 'leads'])}")
    check("Operator 1 (to Feb 2025): paid / leads", "37/750",
          f"{int(by_handler.loc['Operator 1', 'won'])}/{int(by_handler.loc['Operator 1', 'leads'])}")

    # ---------- B. As-of checks ----------
    # A report dated 31 Dec 2024 must count exactly the 27 closes of 2024 plus
    # earlier ones, and nothing dated later.
    snap_2024 = snapshot(leads, "2024-12-31")
    won_2024 = snap_2024.loc[snap_2024["won"], "close_date"]
    check("As of 31 Dec 2024: closes in 2024", 27, int((won_2024.dt.year == 2024).sum()))
    check("As of 31 Dec 2024: no dates after 31 Dec 2024", True,
          bool(won_2024.max() <= pd.Timestamp("2024-12-31")
               and snap_2024["inquiry_date"].max() <= pd.Timestamp("2024-12-31")))

    # A report dated 31 May 2026 must not count the June 2026 closes yet.
    # Expected value is counted straight from the raw file, separately from snapshot().
    raw = leads[(leads["inquiry_date"] >= "2026-01-01") & (leads["inquiry_date"] <= "2026-05-31")]
    expected_may = int((raw["closed_won"] & (raw["close_date"] <= "2026-05-31")).sum())
    snap_may = snapshot(leads, "2026-05-31")
    cohort_may = snap_may[snap_may["inquiry_date"] >= "2026-01-01"]
    check("As of 31 May 2026: Jan-May cohort paid so far", expected_may, int(cohort_may["won"].sum()))

    return pd.DataFrame(results)
