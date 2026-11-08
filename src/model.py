"""
The forecast, in Python. The Excel workbook does the same sums with live formulas;
check_model.py compares the two, so a broken formula or a broken line of code shows up.

Forecast, one month, one case (low / base / high):
  leads     = lead multiplier x (1 + growth) x seasonal index / 12 x SUM(channel leads x lead adjustment)
  MQLs      = same, x triage multiplier,     channel sum also x triage pass x its adjustment
  calls     = same, x call-rate multiplier,  channel sum also x call rate x its adjustment
  paid      = same, x call-to-paid multiplier, channel sum also x call-to-paid x its adjustment
  (MQLs, calls and paid here are for the leads that ARRIVED in the month)
  calls held in a month   = this month's arrivals x same-month share
                            + last month's arrivals x (1 - same-month share)
  paid clients in a month = the same, with the payment timing share
  revenue                 = paid clients x revenue per client x its multiplier x its adjustment
The first forecast month also gets the calls and payments from May 2026 leads that
actually landed in June 2026 (carry-in).
"""

import math

import pandas as pd

from src.inputs import CASES


def _mult(inp, driver, case):
    return inp["base"]["ranges"][driver][case]


def forecast(inp, case="base"):
    b, lv, s = inp["base"], inp["levers"], inp["settings"]
    lm = _mult(inp, "lead_volume", case) * (1 + lv["growth"])
    m1, m2, m3 = (_mult(inp, d, case) for d in ["mql_rate", "call_rate", "call_to_paid"])
    rows = []
    for j, month in enumerate(inp["months"]):
        k = lm * b["season"][month.month] / 12
        sum_l = sum_m = sum_c = sum_p = 0.0
        for ch in inp["channels"]:
            x = b["leads12"][ch] * lv["lead_adj"][ch][j]
            sum_l += x
            x *= b["mql_rate"][ch] * lv["mql_adj"][ch]
            sum_m += x
            x *= b["call_rate"][ch] * lv["call_adj"][ch]
            sum_c += x
            x *= b["call_to_paid"][ch] * lv["paid_adj"][ch]
            sum_p += x
        rows.append({"month": month, "leads": k * sum_l, "mqls": k * m1 * sum_m,
                     "calls_by_arrival": k * m1 * m2 * sum_c,
                     "paid_by_arrival": k * m1 * m2 * m3 * sum_p})
    fc = pd.DataFrame(rows).set_index("month")
    fc["calls_held"] = _land(fc["calls_by_arrival"], b["calls_same"], inp["carry_in"]["calls"])
    fc["paid_clients"] = _land(fc["paid_by_arrival"], b["paid_same"], inp["carry_in"]["paid"])
    rpc = b["rpc"] * _mult(inp, "revenue_per_client", case) * lv["rpc_adj"]
    fc["revenue_bdt"] = fc["paid_clients"] * rpc
    fc["revenue_cad"] = fc["revenue_bdt"] / s["bdt_per_cad"]
    return fc


def _land(by_arrival, same_share, carry_in):
    """Spread arrivals into the month they land: same month or the month after."""
    values = list(by_arrival)
    landed = []
    for j, v in enumerate(values):
        prior = values[j - 1] * (1 - same_share) if j else carry_in
        landed.append(v * same_share + prior)
    return pd.Series(landed, index=by_arrival.index)


def by_channel(inp):
    """Base case: leads and paid (by arrival month) for each channel."""
    b, lv = inp["base"], inp["levers"]
    lm = (1 + lv["growth"])
    out = {}
    for ch in inp["channels"]:
        leads, paid = [], []
        for j, month in enumerate(inp["months"]):
            x = lm * b["season"][month.month] / 12 * b["leads12"][ch] * lv["lead_adj"][ch][j]
            leads.append(x)
            paid.append(x * b["mql_rate"][ch] * lv["mql_adj"][ch] * b["call_rate"][ch] *
                        lv["call_adj"][ch] * b["call_to_paid"][ch] * lv["paid_adj"][ch])
        out[ch] = {"leads": leads, "paid_by_arrival": paid}
    return out


def capacity(inp, fc):
    c = inp["capacity"]
    needed = [math.ceil(max(l / c["leads_per_operator"], k / c["calls_per_operator"]) - 1e-12)
              for l, k in zip(fc["leads"], fc["calls_held"])]
    short = [max(0, n - p) for n, p in zip(needed, c["planned"])]
    return {"needed": needed, "short": short, "months_short": sum(1 for x in short if x > 0)}


def sensitivity(inp, fc, caps, growths):
    """Months (of 12) needing more operators than planned, by lead capacity and lead growth."""
    c, g = inp["capacity"], inp["levers"]["growth"]
    grid = {}
    for cap in caps:
        for gcol in growths:
            f = (1 + gcol) / (1 + g)
            n = 0
            for l, k, p in zip(fc["leads"], fc["calls_held"], c["planned"]):
                if (math.ceil(l * f / cap - 1e-12) > p) or \
                        (math.ceil(k * f / c["calls_per_operator"] - 1e-12) > p):
                    n += 1
            grid[(cap, gcol)] = n
    return grid


def _rates24(inp):
    bt = inp["backtest"]
    p = bt["pooled"]
    pooled = (p["mqls"] / p["leads"], p["calls"] / p["mqls"], p["paid"] / p["calls"])
    out = {}
    for ch in inp["channels"]:
        if ch in bt["channels"]:
            out[ch] = (bt["mql_rate"][ch], bt["call_rate"][ch], bt["call_to_paid"][ch])
        else:
            out[ch] = pooled
    return out


def backtest(inp):
    bt = inp["backtest"]
    months = [pd.Period(f"2025-{m:02d}", "M") for m in range(1, 13)]
    k1 = sum(bt["leads"][ch] for ch in bt["channels"])
    k3 = sum(bt["leads"][ch] * bt["mql_rate"][ch] * bt["call_rate"][ch] * bt["call_to_paid"][ch]
             for ch in bt["channels"])
    carry = sum(bt["dec_leads"][ch] * bt["mql_rate"][ch] * bt["call_rate"][ch] *
                bt["call_to_paid"][ch] for ch in bt["channels"]) * (1 - bt["paid_same"])
    leads = pd.Series([k1 / 12 * bt["season"][m.month] for m in months], index=months)
    by_arrival = pd.Series([k3 / 12 * bt["season"][m.month] for m in months], index=months)
    paid = _land(by_arrival, bt["paid_same"], carry)

    hist = inp["history"].set_index("month")
    actual_paid = hist.loc[months, "paid_clients"].astype(float)
    actual_leads = hist.loc[months, "leads"].astype(float)

    r = _rates24(inp)
    a = bt["actual_2025"]
    f0 = k3
    fcal = paid.sum()
    f1 = sum(a[ch]["leads"] * r[ch][0] * r[ch][1] * r[ch][2] for ch in inp["channels"])
    f2 = sum(a[ch]["mqls"] * r[ch][1] * r[ch][2] for ch in inp["channels"])
    f3 = sum(a[ch]["calls"] * r[ch][2] for ch in inp["channels"])
    f4 = sum(a[ch]["paid"] for ch in inp["channels"])
    actual = actual_paid.sum()
    bridge = {"forecast": fcal, "leads": f1 - f0, "triage": f2 - f1, "call_rate": f3 - f2,
              "call_to_paid": f4 - f3, "timing": (f0 - fcal) + (actual - f4), "actual": actual}
    return {"leads": leads, "paid": paid, "revenue": paid * bt["rpc"], "carry_in": carry,
            "actual_paid": actual_paid, "actual_leads": actual_leads, "bridge": bridge}


def top_down(inp):
    h = inp["history"].set_index("month")
    last = pd.period_range("2025-06", "2026-05", freq="M")
    prior = pd.period_range("2024-06", "2025-05", freq="M")
    out = {}
    for col in ["paid_clients", "revenue_bdt"]:
        l, p = h.loc[last, col].sum(), h.loc[prior, col].sum()
        out[col] = {"last12": l, "prior12": p, "growth": l / p - 1,
                    "repeat_growth": l * (l / p), "flat": l}
    return out


def run_all(inp):
    cases = {c: forecast(inp, c) for c in CASES}
    return {"cases": cases, "by_channel": by_channel(inp),
            "capacity": capacity(inp, cases["base"]), "backtest": backtest(inp),
            "top_down": top_down(inp)}
