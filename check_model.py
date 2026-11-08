"""
Session 2 check. Run from the project folder:

    python check_model.py

Reads the numbers Excel calculated in zorora_forecast.xlsx and recalculates the same
forecast in Python (src/model.py). Every key figure must match: counts to 0.001,
revenue to the taka. If you changed blue cells in Excel, this compares against the
default inputs, so expect differences; rebuild with build_model.py to reset.
"""

import sys

from openpyxl import load_workbook

import build_model as bm
from src.inputs import CASES, load_inputs
from src.model import run_all, sensitivity


def main():
    if not bm.OUT_FILE.exists():
        sys.exit("zorora_forecast.xlsx is missing. Run python build_model.py first.")
    inp = load_inputs()
    bm.build(inp)  # fills in the cell positions without saving
    py = run_all(inp)
    wb = load_workbook(bm.OUT_FILE, data_only=True)
    if wb["Forecast"]["N8"].value is None:
        sys.exit("The workbook has no calculated values yet. Open it in Excel, press Ctrl+S, "
                 "close it, then run this again.")

    rows = []

    def check(name, excel, python, tol):
        ok = excel is not None and abs(excel - python) <= tol
        rows.append((name, excel, python, "PASS" if ok else "FAIL"))

    fc_ws = wb["Forecast"]
    for case in CASES:
        f = py["cases"][case]
        for name, tol in [("leads", 1e-3), ("paid_clients", 1e-3), ("revenue_bdt", 1)]:
            check(f"{case}: 12-month {name}", fc_ws[f"N{bm.fc_row(case, name)}"].value,
                  f[name].sum(), tol)
        for j, c in enumerate(bm.MONTH_COLS):
            check(f"{case}: paid clients {f.index[j]}",
                  fc_ws[f"{c}{bm.fc_row(case, 'paid_clients')}"].value, f["paid_clients"].iloc[j], 1e-3)

    cap = wb["Capacity"]
    check("Capacity: months short (base)", cap["B19"].value, py["capacity"]["months_short"], 0)
    g = bm.CAPACITY_GRID
    grid = sensitivity(inp, py["cases"]["base"], g["caps"], g["growths"])
    for i, c_val in enumerate(g["caps"]):
        for k, g_val in enumerate(g["growths"]):
            check(f"Capacity grid: {c_val} leads, {g_val:+.0%} growth",
                  cap[f"{bm.col(2 + k)}{g['first_row'] + i}"].value, grid[(c_val, g_val)], 0)

    bt_ws, bt = wb["Backtest"], py["backtest"]
    check("Backtest: carry-in", bt_ws[bm.BACKTEST["carry"]].value, bt["carry_in"], 1e-6)
    for key in ["forecast", "leads", "triage", "call_rate", "call_to_paid", "timing", "actual"]:
        check(f"Backtest bridge: {key}", bt_ws[bm.BACKTEST[key]].value, bt["bridge"][key], 1e-6)

    td_ws, td = wb["Top-down"], py["top_down"]
    for c, k, tol in [("B", "paid_clients", 1e-6), ("C", "revenue_bdt", 1)]:
        check(f"Top-down: flat {k}", td_ws[f"{c}8"].value, td[k]["flat"], tol)
        check(f"Top-down: repeat growth {k}", td_ws[f"{c}9"].value, td[k]["repeat_growth"], tol)

    all_ok = wb["Summary"][bm.SUMMARY["all_checks"]].value is True
    rows.append(("Workbook's own checks (Summary tab)", all_ok, True, "PASS" if all_ok else "FAIL"))

    failed = [r for r in rows if r[3] == "FAIL"]
    for name, excel, python, result in failed:
        print(f"FAIL  {name}: Excel {excel}, Python {python}")
    if failed:
        sys.exit(f"\n{len(failed)} of {len(rows)} checks failed. Send Claude the FAIL lines.")

    base = py["cases"]["base"]
    print(f"ALL {len(rows)} CHECKS PASSED: Excel and Python agree.\n")
    print("Five numbers to look for in Excel (Summary tab):")
    print(f"  1. Base case paid clients, next 12 months: {base['paid_clients'].sum():.1f}")
    print(f"  2. Base case revenue (BDT): {base['revenue_bdt'].sum():,.0f}")
    print(f"  3. Months short of operators (base): {py['capacity']['months_short']}")
    print(f"  4. Backtest forecast for 2025: {bt['bridge']['forecast']:.1f} vs actual "
          f"{bt['bridge']['actual']:.0f}")
    steps = {k: bt["bridge"][k] for k in ["leads", "triage", "call_rate", "call_to_paid", "timing"]}
    top = max(steps, key=steps.get)
    print(f"  5. Biggest driver of the gap: {top.replace('_', '-')}, {steps[top]:+.1f} paid clients")


if __name__ == "__main__":
    main()
