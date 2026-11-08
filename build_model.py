"""
Session 2 command. Run from the project folder (after build_drivers.py):

    python build_model.py

Writes zorora_forecast.xlsx: the forecast as an Excel model with live formulas.
Blue cells are typed-in numbers you can change; everything else is a formula.
Open it in Excel; it calculates when it opens. Then run check_model.py.
"""

import calendar
import json

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import LineChart, Reference
from openpyxl.chart.series import SeriesLabel
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter as col

from src.inputs import DRIVER_LABELS, DRIVERS, load_inputs
from src.load import PROJECT_ROOT
from src.scenario import SLOT

OUT_FILE = PROJECT_ROOT / "zorora_forecast.xlsx"

FONT = "Arial"
BLUE, BLACK, GREEN, GREY = "0000FF", "000000", "008000", "808080"
YELLOW = PatternFill("solid", fgColor="FFFF00")
HEAD = PatternFill("solid", fgColor="D9E1F2")

F_COUNT, F_ONE, F_BDT, F_CAD = "0;(0);-", "0.0;(0.0);-", "#,##0;(#,##0);-", "#,##0;(#,##0);-"
F_PCT, F_MULT, F_INT = "0.0%;(0.0%);-", "0.00", "0"
MONTH_COLS = [col(c) for c in range(2, 14)]  # B..M


# ---------- small helpers ----------
def put(ws, ref, value, color=BLACK, fmt=None, bold=False, fill=None, size=10, italic=False,
        wrap=False, comment=None):
    c = ws[ref]
    c.value = value
    c.font = Font(name=FONT, color=color, bold=bold, size=size, italic=italic)
    if fmt:
        c.number_format = fmt
    if fill:
        c.fill = fill
    if wrap:
        c.alignment = Alignment(wrap_text=True, vertical="top")
    if comment:
        c.comment = Comment(comment, "Model")
    return c


def title(ws, text, note=None):
    put(ws, "A1", text, bold=True, size=14)
    if note:
        put(ws, "A2", note, color=GREY, italic=True)


def section(ws, ref, text):
    put(ws, ref, text, bold=True, size=11)


def header_row(ws, row, labels, start=1):
    for i, label in enumerate(labels):
        put(ws, f"{col(start + i)}{row}", label, bold=True, fill=HEAD, wrap=True)


def widths(ws, first=44, rest=13, n=16):
    ws.column_dimensions["A"].width = first
    for i in range(2, n + 1):
        ws.column_dimensions[col(i)].width = rest


def month_label(p):
    return p.strftime("%b %Y")


def render_slots(text, slots):
    return SLOT.sub(lambda m: slots[m.group(1)], text)


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def approved_notes():
    return _read_json(PROJECT_ROOT / "notes" / "driver_notes_approved.json")


def approved_scenarios():
    folder = PROJECT_ROOT / "scenarios" / "approved"
    return [_read_json(p) for p in sorted(folder.glob("S*.json"))] if folder.exists() else []


# ---------- the workbook ----------
def build(inp):
    wb = Workbook()
    wb.remove(wb.active)
    sheets = {name: wb.create_sheet(name) for name in
              ["Summary", "Inputs", "Forecast", "Capacity", "Backtest", "Top-down", "Scenarios",
               "History", "Notes"]}
    inputs_tab(sheets["Inputs"], inp)
    history_tab(sheets["History"], inp)
    forecast_tab(sheets["Forecast"], inp)
    capacity_tab(sheets["Capacity"], inp)
    backtest_tab(sheets["Backtest"], inp)
    top_down_tab(sheets["Top-down"])
    notes_tab(sheets["Notes"], inp)
    scenarios_tab(sheets["Scenarios"])
    summary_tab(sheets["Summary"])
    wb.calculation.fullCalcOnLoad = True
    return wb


# Fixed positions on the Inputs tab (formulas elsewhere point here)
IN = {
    "mult_row": {d: 6 + i for i, d in enumerate(DRIVERS)},   # rows 6-10
    "case_col": {"low": "B", "base": "C", "high": "D"},
    "growth": "$B$12",
    "ch_first": 16, "ch_last": 21,                            # channel rows
    "season": "$B$25:$B$36", "season_avg": "B37",
    "calls_same": "$B$40", "paid_same": "$B$41",
    "rpc": "$B$44", "rpc_adj": "$B$45",
    "carry_calls": "$B$48", "carry_paid": "$B$49",
    "leads_cap": "$B$52", "calls_cap": "$B$53",
    "planned_row": 57, "adj_first": 61, "adj_last": 66,
    "cad": "$B$69",
}


def inputs_tab(ws, inp):
    b, lv = inp["base"], inp["levers"]
    title(ws, "Inputs", "Blue = typed-in numbers you can change. Black = formulas. "
                        "Green = links to another tab. Yellow = key assumptions.")
    widths(ws, first=52, rest=12, n=14)

    section(ws, "A4", "1. Low / base / high: each driver's weakest and strongest quarter "
                      "in the last 12 months (Jun 2025 to May 2026), as a multiple of the base")
    header_row(ws, 5, ["Driver", "Low", "Base", "High", "Quarter by quarter"])
    for d, r in IN["mult_row"].items():
        put(ws, f"A{r}", DRIVER_LABELS[d])
        for case, c in IN["case_col"].items():
            put(ws, f"{c}{r}", b["ranges"][d][case], BLUE, F_MULT)
        put(ws, f"E{r}", b["ranges"][d]["quarters"], GREY)

    put(ws, "A12", "Lead growth on top of the last 12 months")
    put(ws, "B12", lv["growth"], BLUE, F_PCT, fill=YELLOW,
        comment="0% = the next 12 months get the same leads as the last 12, "
                "spread by the seasonal pattern.")

    section(ws, "A14", "2. Channel drivers (leads that arrived Jun 2025 to May 2026). "
                       "Adjustments: 100% = no change")
    header_row(ws, 15, ["Channel", "Leads in last 12 months", "Triage pass", "Call rate",
                        "Call-to-paid", "Triage adj.", "Call adj.", "Call-to-paid adj.",
                        "Based on (passed / total)"])
    for i, ch in enumerate(inp["channels"]):
        r = IN["ch_first"] + i
        put(ws, f"A{r}", ch)
        put(ws, f"B{r}", b["leads12"][ch], BLUE, F_COUNT)
        put(ws, f"C{r}", b["mql_rate"][ch], BLUE, F_PCT)
        put(ws, f"D{r}", b["call_rate"][ch], BLUE, F_PCT)
        put(ws, f"E{r}", b["call_to_paid"][ch], BLUE, F_PCT)
        put(ws, f"F{r}", lv["mql_adj"][ch], BLUE, F_PCT)
        put(ws, f"G{r}", lv["call_adj"][ch], BLUE, F_PCT)
        put(ws, f"H{r}", lv["paid_adj"][ch], BLUE, F_PCT)
        src = b["source"][ch]
        bo = b["based_on"][ch]
        parts = [f"triage {bo['mql_rate']}"]
        for k, label in [("call_rate", "calls"), ("call_to_paid", "paid")]:
            parts.append(f"{label} {bo[k]}" + (" (too few: all-channel rate used)"
                                               if src[k] != "own" else ""))
        put(ws, f"I{r}", "; ".join(parts), GREY)
    ws.column_dimensions["I"].width = 70

    section(ws, "A23", "3. Seasonality: each calendar month's leads vs an average month "
                       "(Jan 2024 to May 2026)")
    header_row(ws, 24, ["Month", "Index"])
    for m in range(1, 13):
        put(ws, f"A{24 + m}", calendar.month_name[m])
        put(ws, f"B{24 + m}", b["season"][m], BLUE, F_MULT)
    put(ws, "A37", "Average (must be 1.00)")
    put(ws, "B37", "=AVERAGE(B25:B36)", fmt=F_MULT)

    section(ws, "A39", "4. Timing: share landing in the month the lead arrived "
                       "(the rest land the month after)")
    put(ws, "A40", "Calls")
    put(ws, "B40", b["calls_same"], BLUE, F_PCT)
    put(ws, "A41", "Payments")
    put(ws, "B41", b["paid_same"], BLUE, F_PCT)

    section(ws, "A43", "5. Revenue per paid client (BDT)")
    put(ws, "A44", f"Average of the {b['rpc_based_on']} clients who paid Jun 2025 to May 2026")
    put(ws, "B44", round(b["rpc"], 2), BLUE, F_BDT)
    put(ws, "A45", "Revenue per client adjustment")
    put(ws, "B45", lv["rpc_adj"], BLUE, F_PCT)

    section(ws, "A47", "6. Carry-in: May 2026 leads whose call or payment landed in June 2026 (actual)")
    put(ws, "A48", "Calls")
    put(ws, "B48", inp["carry_in"]["calls"], BLUE, F_COUNT)
    put(ws, "A49", "Paid clients")
    put(ws, "B49", inp["carry_in"]["paid"], BLUE, F_COUNT)

    section(ws, "A51", "7. Capacity per operator per month (assumptions; the Capacity tab "
                       "shows how much they matter)")
    put(ws, "A52", "Leads one operator can handle")
    put(ws, "B52", inp["capacity"]["leads_per_operator"], BLUE, F_COUNT, fill=YELLOW,
        comment="Assumption, not measured. Busiest month in the data: 88 leads for one "
                "operator (Nov 2025).")
    put(ws, "A53", "Diagnostic calls one operator can hold")
    put(ws, "B53", inp["capacity"]["calls_per_operator"], BLUE, F_COUNT, fill=YELLOW,
        comment="Assumption, not measured. Busiest month in the data: 15 calls (Dec 2025).")

    section(ws, "A55", "8. Operators planned")
    put(ws, "A56", "Month", bold=True)
    put(ws, "A57", "Operators")
    for j, (c, m) in enumerate(zip(MONTH_COLS, inp["months"])):
        put(ws, f"{c}56", month_label(m), bold=True, fill=HEAD)
        put(ws, f"{c}57", inp["capacity"]["planned"][j], BLUE, F_INT)

    section(ws, "A59", "9. Lead adjustments by channel and month (100% = no change; "
                       "scenarios change these)")
    put(ws, "A60", "Channel", bold=True, fill=HEAD)
    for c, m in zip(MONTH_COLS, inp["months"]):
        put(ws, f"{c}60", month_label(m), bold=True, fill=HEAD)
    for i, ch in enumerate(inp["channels"]):
        r = IN["adj_first"] + i
        put(ws, f"A{r}", ch)
        for j, c in enumerate(MONTH_COLS):
            put(ws, f"{c}{r}", lv["lead_adj"][ch][j], BLUE, "0%")

    section(ws, "A68", "10. Exchange rate")
    s = inp["settings"]
    put(ws, "A69", f"BDT per CAD ({s['cad_rate_source']}, {s['cad_rate_date']})")
    put(ws, "B69", s["bdt_per_cad"], BLUE, F_COUNT)
    ws.freeze_panes = "B4"


# Forecast tab rows
FC_BLOCKS = {"base": 7, "low": 17, "high": 27}   # header row of each case block
FC_ROWS = ["leads", "mqls", "calls_by_arrival", "paid_by_arrival", "calls_held",
           "paid_clients", "revenue_bdt", "revenue_cad"]
FC_LABELS = {
    "leads": "Leads",
    "mqls": "Passed triage (MQLs), for leads arriving this month",
    "calls_by_arrival": "Diagnostic calls, for leads arriving this month",
    "paid_by_arrival": "Paid clients, for leads arriving this month",
    "calls_held": "Diagnostic calls held this month",
    "paid_clients": "Paid clients this month",
    "revenue_bdt": "Revenue (BDT)",
    "revenue_cad": "Revenue (CAD)",
}
FC_FMT = {"leads": F_COUNT, "mqls": F_ONE, "calls_by_arrival": F_ONE, "paid_by_arrival": F_ONE,
          "calls_held": F_ONE, "paid_clients": F_ONE, "revenue_bdt": F_BDT, "revenue_cad": F_CAD}


def fc_row(case, name):
    return FC_BLOCKS[case] + 1 + FC_ROWS.index(name)


def forecast_tab(ws, inp):
    title(ws, "Forecast: Jun 2026 to May 2027",
          "Every cell is a formula on the Inputs tab. Low and high put every driver at its "
          "weakest or strongest quarter at once, so they are outer bounds.")
    widths(ws, first=50, rest=11, n=15)
    put(ws, "A4", "Month", bold=True)
    put(ws, "A5", "Calendar month (1-12)", GREY)
    for c, m in zip(MONTH_COLS, inp["months"]):
        put(ws, f"{c}4", month_label(m), bold=True, fill=HEAD)
        put(ws, f"{c}5", m.month, GREY)
    put(ws, "N4", "12 months", bold=True, fill=HEAD)

    L = f"Inputs!$B${IN['ch_first']}:$B${IN['ch_last']}"
    rate = {k: f"Inputs!${k}${IN['ch_first']}:${k}${IN['ch_last']}" for k in "CDEFGH"}
    for case, start in FC_BLOCKS.items():
        put(ws, f"A{start}", f"{case.upper()} CASE", bold=True)
        cc = IN["case_col"][case]
        m = {d: f"Inputs!${cc}${r}" for d, r in IN["mult_row"].items()}
        for name in FC_ROWS:
            r = fc_row(case, name)
            put(ws, f"A{r}", FC_LABELS[name])
            for j, c in enumerate(MONTH_COLS):
                adj = f"Inputs!{c}${IN['adj_first']}:{c}${IN['adj_last']}"
                k = (f"{m['lead_volume']}*(1+Inputs!{IN['growth']})"
                     f"*INDEX(Inputs!{IN['season']},{c}$5)/12")
                prev = MONTH_COLS[j - 1] if j else None
                f = {
                    "leads": f"={k}*SUMPRODUCT({L},{adj})",
                    "mqls": f"={k}*{m['mql_rate']}*SUMPRODUCT({L},{adj},{rate['C']},{rate['F']})",
                    "calls_by_arrival": f"={k}*{m['mql_rate']}*{m['call_rate']}*SUMPRODUCT("
                                        f"{L},{adj},{rate['C']},{rate['F']},{rate['D']},{rate['G']})",
                    "paid_by_arrival": f"={k}*{m['mql_rate']}*{m['call_rate']}*{m['call_to_paid']}"
                                       f"*SUMPRODUCT({L},{adj},{rate['C']},{rate['F']},{rate['D']},"
                                       f"{rate['G']},{rate['E']},{rate['H']})",
                }.get(name)
                if name == "calls_held":
                    a = fc_row(case, "calls_by_arrival")
                    f = (f"={c}{a}*Inputs!{IN['calls_same']}+" +
                         (f"{prev}{a}*(1-Inputs!{IN['calls_same']})" if prev
                          else f"Inputs!{IN['carry_calls']}"))
                if name == "paid_clients":
                    a = fc_row(case, "paid_by_arrival")
                    f = (f"={c}{a}*Inputs!{IN['paid_same']}+" +
                         (f"{prev}{a}*(1-Inputs!{IN['paid_same']})" if prev
                          else f"Inputs!{IN['carry_paid']}"))
                if name == "revenue_bdt":
                    f = (f"={c}{fc_row(case, 'paid_clients')}*Inputs!{IN['rpc']}"
                         f"*{m['revenue_per_client']}*Inputs!{IN['rpc_adj']}")
                if name == "revenue_cad":
                    f = f"={c}{fc_row(case, 'revenue_bdt')}/Inputs!{IN['cad']}"
                put(ws, f"{c}{r}", f, fmt=FC_FMT[name])
            put(ws, f"N{r}", f"=SUM(B{r}:M{r})", fmt=FC_FMT[name], bold=True)

    # Base case by channel
    r0 = 37
    put(ws, f"A{r0}", "BASE CASE BY CHANNEL", bold=True)
    base_m = {d: f"Inputs!$C${r}" for d, r in IN["mult_row"].items()}
    lead_rows, paid_rows = [], []
    for i, ch in enumerate(inp["channels"]):
        rl, rp = r0 + 1 + 2 * i, r0 + 2 + 2 * i
        lead_rows.append(rl)
        paid_rows.append(rp)
        ir = IN["ch_first"] + i
        put(ws, f"A{rl}", f"{ch}: leads")
        put(ws, f"A{rp}", f"{ch}: paid clients, for leads arriving this month")
        for c in MONTH_COLS:
            put(ws, f"{c}{rl}", f"={base_m['lead_volume']}*(1+Inputs!{IN['growth']})"
                                f"*INDEX(Inputs!{IN['season']},{c}$5)/12*Inputs!$B${ir}"
                                f"*Inputs!{c}${IN['adj_first'] + i}", fmt=F_ONE)
            put(ws, f"{c}{rp}", f"={c}{rl}*Inputs!$C${ir}*Inputs!$F${ir}*Inputs!$D${ir}"
                                f"*Inputs!$G${ir}*Inputs!$E${ir}*Inputs!$H${ir}"
                                f"*{base_m['mql_rate']}*{base_m['call_rate']}*{base_m['call_to_paid']}",
                fmt=F_ONE)
        for r in (rl, rp):
            put(ws, f"N{r}", f"=SUM(B{r}:M{r})", fmt=F_ONE, bold=True)
    rc1, rc2 = r0 + 2 * len(inp["channels"]) + 1, r0 + 2 * len(inp["channels"]) + 2
    put(ws, f"A{rc1}", "Check: channel leads add up to the base case", GREY)
    put(ws, f"A{rc2}", "Check: channel paid clients add up to the base case", GREY)
    for c in MONTH_COLS:
        put(ws, f"{c}{rc1}", f"=ABS({'+'.join(f'{c}{r}' for r in lead_rows)}"
                             f"-{c}{fc_row('base', 'leads')})<0.000001", GREY)
        put(ws, f"{c}{rc2}", f"=ABS({'+'.join(f'{c}{r}' for r in paid_rows)}"
                             f"-{c}{fc_row('base', 'paid_by_arrival')})<0.000001", GREY)
    FORECAST_CHECK_ROWS[:] = [rc1, rc2]

    # Quarters
    q0 = rc2 + 2
    put(ws, f"A{q0}", "QUARTERS", bold=True)
    header_row(ws, q0 + 1, ["Quarter", "Paid clients: low", "Paid clients: base",
                            "Paid clients: high", "Revenue (BDT): low", "Revenue (BDT): base",
                            "Revenue (BDT): high"])
    months = inp["months"]
    for q in range(4):
        r = q0 + 2 + q
        cs = MONTH_COLS[3 * q:3 * q + 3]
        put(ws, f"A{r}", f"{month_label(months[3 * q])} to {month_label(months[3 * q + 2])}")
        for k, case in enumerate(["low", "base", "high"]):
            put(ws, f"{col(2 + k)}{r}", f"=SUM({cs[0]}{fc_row(case, 'paid_clients')}:"
                                       f"{cs[-1]}{fc_row(case, 'paid_clients')})", fmt=F_ONE)
            put(ws, f"{col(5 + k)}{r}", f"=SUM({cs[0]}{fc_row(case, 'revenue_bdt')}:"
                                       f"{cs[-1]}{fc_row(case, 'revenue_bdt')})", fmt=F_BDT)
    rt = q0 + 6
    put(ws, f"A{rt}", "12 months", bold=True)
    for k in range(6):
        c = col(2 + k)
        put(ws, f"{c}{rt}", f"=SUM({c}{q0 + 2}:{c}{q0 + 5})", fmt=F_ONE if k < 3 else F_BDT, bold=True)

    chart = LineChart()
    chart.title = "Paid clients per month: low, base, high"
    chart.height, chart.width = 8, 22
    for case in ["low", "base", "high"]:
        r = fc_row(case, "paid_clients")
        data = Reference(ws, min_col=2, max_col=13, min_row=r, max_row=r)
        chart.add_data(data, from_rows=True, titles_from_data=False)
    for s, name in zip(chart.series, ["Low", "Base", "High"]):
        s.tx = SeriesLabel(v=name)
        s.smooth = False
    chart.set_categories(Reference(ws, min_col=2, max_col=13, min_row=4, max_row=4))
    ws.add_chart(chart, f"A{rt + 3}")
    ws.freeze_panes = "B6"


FORECAST_CHECK_ROWS = []


def capacity_tab(ws, inp):
    title(ws, "Capacity: do we need another operator?",
          "Base case unless marked. Operators needed = the higher of leads / lead capacity "
          "and calls / call capacity, rounded up.")
    widths(ws, first=50, rest=11, n=14)
    put(ws, "A4", "Month", bold=True)
    for c in MONTH_COLS:
        put(ws, f"{c}4", f"=Forecast!{c}4", GREEN, bold=True, fill=HEAD)
    rows = [
        (5, "Leads (base)", lambda c: f"=Forecast!{c}{fc_row('base', 'leads')}", F_COUNT, GREEN),
        (6, "Diagnostic calls held (base)", lambda c: f"=Forecast!{c}{fc_row('base', 'calls_held')}",
         F_ONE, GREEN),
        (7, "Operators needed for leads", lambda c: f"={c}5/Inputs!{IN['leads_cap']}", "0.00", BLACK),
        (8, "Operators needed for calls", lambda c: f"={c}6/Inputs!{IN['calls_cap']}", "0.00", BLACK),
        (9, "Operators needed", lambda c: f"=ROUNDUP(MAX({c}7,{c}8),0)", F_INT, BLACK),
        (10, "Operators planned", lambda c: f"=Inputs!{c}{IN['planned_row']}", F_INT, GREEN),
        (11, "Short by", lambda c: f"=MAX(0,{c}9-{c}10)", F_INT, BLACK),
        (12, "Lead load vs planned capacity", lambda c: f"={c}5/({c}10*Inputs!{IN['leads_cap']})",
         F_PCT, BLACK),
        (14, "Leads (high case)", lambda c: f"=Forecast!{c}{fc_row('high', 'leads')}", F_COUNT, GREEN),
        (15, "Diagnostic calls held (high case)",
         lambda c: f"=Forecast!{c}{fc_row('high', 'calls_held')}", F_ONE, GREEN),
        (16, "Operators needed (high case)",
         lambda c: f"=ROUNDUP(MAX({c}14/Inputs!{IN['leads_cap']},{c}15/Inputs!{IN['calls_cap']}),0)",
         F_INT, BLACK),
        (17, "Short by (high case)", lambda c: f"=MAX(0,{c}16-{c}10)", F_INT, BLACK),
    ]
    for r, label, f, fmt, color in rows:
        put(ws, f"A{r}", label)
        for c in MONTH_COLS:
            put(ws, f"{c}{r}", f(c), color, fmt)

    put(ws, "A19", "Months short of operators, base case", bold=True)
    put(ws, "B19", '=COUNTIF(B11:M11,">0")', fmt=F_INT, bold=True)
    put(ws, "A20", "Months short of operators, high case")
    put(ws, "B20", '=COUNTIF(B17:M17,">0")', fmt=F_INT)
    put(ws, "A21", "Busiest month (base)")
    put(ws, "B21", "=INDEX(B4:M4,MATCH(MAX(B5:M5),B5:M5,0))")
    put(ws, "A22", "Busiest month's lead load vs capacity (base)")
    put(ws, "B22", "=MAX(B12:M12)", fmt=F_PCT)

    section(ws, "A24", "How much the answer depends on the assumptions: months (of 12) short "
                       "of operators, base case")
    put(ws, "A25", "Leads one operator can handle (down) / lead growth (across)", bold=True, fill=HEAD)
    growths = [-0.2, -0.1, 0.0, 0.1, 0.2]
    caps = [65, 70, 75, 80, 85, 90, 95, 100]
    for k, g in enumerate(growths):
        put(ws, f"{col(2 + k)}25", g, BLUE, "+0%;-0%;0%", bold=True, fill=HEAD)
    for i, cap in enumerate(caps):
        r = 26 + i
        put(ws, f"A{r}", cap, BLUE, F_COUNT)
        ws[f"A{r}"].alignment = Alignment(horizontal="left")
        for k in range(len(growths)):
            g = f"{col(2 + k)}$25"
            put(ws, f"{col(2 + k)}{r}",
                f"=SUMPRODUCT(--(((ROUNDUP($B$5:$M$5*(1+{g})/(1+Inputs!{IN['growth']})/$A{r},0)"
                f">$B$10:$M$10)+(ROUNDUP($B$6:$M$6*(1+{g})/(1+Inputs!{IN['growth']})"
                f"/Inputs!{IN['calls_cap']},0)>$B$10:$M$10))>0))", fmt="0")
    put(ws, "A35", "Read across a row to see how lead growth changes the answer; down a column "
                   "for the capacity assumption. Calls scale with leads.", GREY, italic=True)
    ws.freeze_panes = "B5"
    CAPACITY_GRID.update({"caps": caps, "growths": growths, "first_row": 26})


CAPACITY_GRID = {}


def history_tab(ws, inp):
    title(ws, "History: what actually happened, Jan 2024 to May 2026",
          "Counts by the month each thing happened. Values from the data (build_drivers.py).")
    widths(ws, first=16, rest=14, n=7)
    header_row(ws, 4, ["Month", "Leads", "Passed triage (MQLs)", "Diagnostic calls held",
                       "Paid clients", "Revenue (BDT)"])
    h = inp["history"]
    for i, row in enumerate(h.itertuples()):
        r = 5 + i
        put(ws, f"A{r}", row.month.to_timestamp().to_pydatetime(), BLUE, "mmm yyyy")
        ws[f"A{r}"].alignment = Alignment(horizontal="left")
        put(ws, f"B{r}", int(row.leads), BLUE, F_COUNT)
        put(ws, f"C{r}", int(row.mqls), BLUE, F_COUNT)
        put(ws, f"D{r}", int(row.diagnostic_calls), BLUE, F_COUNT)
        put(ws, f"E{r}", int(row.paid_clients), BLUE, F_COUNT)
        put(ws, f"F{r}", int(row.revenue_bdt), BLUE, F_BDT)
    last = 4 + len(h)
    HISTORY.update({"first": 5, "last": last})
    section(ws, f"A{last + 2}", "Year totals")
    for k, (yr, note) in enumerate([("2024", ""), ("2025", ""), ("2026", " (Jan to May)")]):
        r = last + 3 + k
        put(ws, f"A{r}", yr + note)
        for c in "BCDEF":
            put(ws, f"{c}{r}", f"=SUMPRODUCT((YEAR($A$5:$A${last})={yr})*{c}$5:{c}${last})",
                fmt=F_BDT if c == "F" else F_COUNT)
        HISTORY[yr] = r
    ws.freeze_panes = "B5"


HISTORY = {}


def hist_row(period):
    first = pd.Period("2024-01", "M")
    return HISTORY["first"] + (period - first).n


def backtest_tab(ws, inp):
    bt = inp["backtest"]
    title(ws, "Backtest: forecasting 2025 with only what was known at the end of 2024",
          "Same method as the main forecast, fed with 2024's drivers, then compared with what "
          "2025 actually did.")
    widths(ws, first=50, rest=11, n=15)

    section(ws, "A4", "1. Drivers from 2024")
    header_row(ws, 5, ["Channel", "Leads in 2024", "Triage pass", "Call rate", "Call-to-paid",
                       "Leads in Dec 2024"])
    chs = bt["channels"]
    for i, ch in enumerate(chs):
        r = 6 + i
        put(ws, f"A{r}", ch)
        put(ws, f"B{r}", bt["leads"][ch], BLUE, F_COUNT)
        put(ws, f"C{r}", bt["mql_rate"][ch], BLUE, F_PCT)
        put(ws, f"D{r}", bt["call_rate"][ch], BLUE, F_PCT)
        put(ws, f"E{r}", bt["call_to_paid"][ch], BLUE, F_PCT)
        put(ws, f"F{r}", bt["dec_leads"][ch], BLUE, F_COUNT)
    last_ch = 5 + len(chs)
    rng = lambda c: f"${c}$6:${c}${last_ch}"
    rc, rr = last_ch + 1, last_ch + 2
    p = bt["pooled"]
    put(ws, f"A{rc}", "All channels, 2024 (leads, MQLs, calls, paid)")
    for c, k in zip("BCDE", ["leads", "mqls", "calls", "paid"]):
        put(ws, f"{c}{rc}", p[k], BLUE, F_COUNT)
    put(ws, f"A{rr}", "All channels, 2024 (rates)")
    put(ws, f"C{rr}", f"=C{rc}/B{rc}", fmt=F_PCT)
    put(ws, f"D{rr}", f"=D{rc}/C{rc}", fmt=F_PCT)
    put(ws, f"E{rr}", f"=E{rc}/D{rc}", fmt=F_PCT)

    rs = rr + 2
    put(ws, f"A{rs}", "Seasonality, 2024", bold=True)
    for m in range(1, 13):
        c = MONTH_COLS[m - 1]
        put(ws, f"{c}{rs}", calendar.month_abbr[m], bold=True, fill=HEAD)
        put(ws, f"{c}{rs + 1}", bt["season"][m], BLUE, F_MULT)
    put(ws, f"A{rs + 1}", "Index")
    t = rs + 3
    put(ws, f"A{t}", "Timing, 2024: share of payments in the arrival month")
    put(ws, f"B{t}", bt["paid_same"], BLUE, F_PCT)
    put(ws, f"A{t + 1}", "Revenue per paid client, 2024 (BDT)")
    put(ws, f"B{t + 1}", round(bt["rpc"], 2), BLUE, F_BDT)
    put(ws, f"A{t + 2}", "Carry-in: Dec 2024 leads expected to pay in Jan 2025")
    put(ws, f"B{t + 2}", f"=SUMPRODUCT({rng('F')},{rng('C')},{rng('D')},{rng('E')})*(1-B{t})",
        fmt=F_ONE)

    # 2. Monthly forecast vs actual
    s2 = t + 4
    section(ws, f"A{s2}", "2. 2025: forecast vs actual")
    put(ws, f"A{s2 + 1}", "Month", bold=True)
    months = [pd.Period(f"2025-{m:02d}", "M") for m in range(1, 13)]
    for c, m in zip(MONTH_COLS, months):
        put(ws, f"{c}{s2 + 1}", month_label(m), bold=True, fill=HEAD)
    put(ws, f"N{s2 + 1}", "2025", bold=True, fill=HEAD)
    R = {k: s2 + 2 + i for i, k in enumerate(
        ["f_leads", "a_leads", "f_arrival", "f_paid", "a_paid", "diff", "f_rev", "a_rev"])}
    labels = {"f_leads": "Forecast leads", "a_leads": "Actual leads",
              "f_arrival": "Forecast paid clients, for leads arriving this month",
              "f_paid": "Forecast paid clients this month", "a_paid": "Actual paid clients",
              "diff": "Forecast minus actual (paid clients)", "f_rev": "Forecast revenue (BDT)",
              "a_rev": "Actual revenue (BDT)"}
    for k, r in R.items():
        put(ws, f"A{r}", labels[k], bold=k in ("f_paid", "a_paid"))
    for j, (c, m) in enumerate(zip(MONTH_COLS, months)):
        season = f"{c}${rs + 1}"
        hr = hist_row(m)
        put(ws, f"{c}{R['f_leads']}", f"=SUM({rng('B')})/12*{season}", fmt=F_COUNT)
        put(ws, f"{c}{R['a_leads']}", f"=History!B{hr}", GREEN, F_COUNT)
        put(ws, f"{c}{R['f_arrival']}",
            f"=SUMPRODUCT({rng('B')},{rng('C')},{rng('D')},{rng('E')})/12*{season}", fmt=F_ONE)
        prev = MONTH_COLS[j - 1] if j else None
        put(ws, f"{c}{R['f_paid']}", f"={c}{R['f_arrival']}*$B${t}+" +
            (f"{prev}{R['f_arrival']}*(1-$B${t})" if prev else f"$B${t + 2}"), fmt=F_ONE)
        put(ws, f"{c}{R['a_paid']}", f"=History!E{hr}", GREEN, F_COUNT)
        put(ws, f"{c}{R['diff']}", f"={c}{R['f_paid']}-{c}{R['a_paid']}", fmt=F_ONE)
        put(ws, f"{c}{R['f_rev']}", f"={c}{R['f_paid']}*$B${t + 1}", fmt=F_BDT)
        put(ws, f"{c}{R['a_rev']}", f"=History!F{hr}", GREEN, F_BDT)
    for k, r in R.items():
        fmt = F_BDT if "rev" in k else (F_COUNT if k in ("f_leads", "a_leads", "a_paid") else F_ONE)
        put(ws, f"N{r}", f"=SUM(B{r}:M{r})", fmt=fmt, bold=True)
    re_ = R["a_rev"] + 1
    put(ws, f"A{re_}", "Forecast error, paid clients (forecast vs actual)", bold=True)
    put(ws, f"N{re_}", f"=(N{R['f_paid']}-N{R['a_paid']})/N{R['a_paid']}", fmt=F_PCT, bold=True)

    # 3. Rates (kept apart from counts)
    s3 = re_ + 2
    section(ws, f"A{s3}", "3. Rates: what the forecast assumed vs what 2025's leads did "
                          "(kept apart from the counts above)")
    header_row(ws, s3 + 1, ["Rate", "Assumed (2024)", "Actual (2025 arrivals)"])

    # 4. Bridge table first, so the rate rows can point at it
    s4 = s3 + 6
    section(ws, f"A{s4}", "4. Bridge: from the forecast to the actual 2025 paid clients")
    put(ws, f"A{s4 + 1}", "Each step swaps one 2024 driver for what 2025's leads actually did, "
                          "in funnel order. A different order would split the steps slightly "
                          "differently.", GREY, italic=True)
    header_row(ws, s4 + 2, ["Channel (2025 arrivals)", "Leads", "MQLs", "Calls", "Paid",
                            "2024 triage pass", "2024 call rate", "2024 call-to-paid"])
    first_b = s4 + 3
    a = bt["actual_2025"]
    for i, ch in enumerate(inp["channels"]):
        r = first_b + i
        put(ws, f"A{r}", ch)
        for c, k in zip("BCDE", ["leads", "mqls", "calls", "paid"]):
            put(ws, f"{c}{r}", a[ch][k], BLUE, F_COUNT)
        for c, src in zip("FGH", "CDE"):
            put(ws, f"{c}{r}", f"=IFERROR(INDEX({rng(src)},MATCH($A{r},$A$6:$A${last_ch},0)),"
                               f"${src}${rr})", fmt=F_PCT)
    last_b = first_b + len(inp["channels"]) - 1
    tot = last_b + 1
    put(ws, f"A{tot}", "All channels", bold=True)
    for c in "BCDE":
        put(ws, f"{c}{tot}", f"=SUM({c}{first_b}:{c}{last_b})", fmt=F_COUNT, bold=True)
    br = lambda c: f"{c}{first_b}:{c}{last_b}"
    sumprod_24 = f"SUMPRODUCT({rng('B')},{rng('C')},{rng('D')},{rng('E')})"
    f1 = f"SUMPRODUCT({br('B')},{br('F')},{br('G')},{br('H')})"
    f2 = f"SUMPRODUCT({br('C')},{br('G')},{br('H')})"
    f3 = f"SUMPRODUCT({br('D')},{br('H')})"
    steps = [
        ("forecast", "Forecast for 2025, made with 2024 drivers", f"=N{R['f_paid']}"),
        ("leads", "More leads, and the new educator channel", f"={f1}-{sumprod_24}"),
        ("triage", "Triage pass", f"={f2}-{f1}"),
        ("call_rate", "Call rate", f"={f3}-{f2}"),
        ("call_to_paid", "Call-to-paid", f"=E{tot}-{f3}"),
        ("timing", "Timing: arrival month vs payment month",
         f"=({sumprod_24}-N{R['f_paid']})+(N{R['a_paid']}-E{tot})"),
        ("actual", "Actual paid clients in 2025", f"=N{R['a_paid']}"),
    ]
    s5 = tot + 2
    header_row(ws, s5, ["Step", "Paid clients"])
    for i, (key, label, f) in enumerate(steps):
        r = s5 + 1 + i
        put(ws, f"A{r}", label, bold=key in ("forecast", "actual"))
        put(ws, f"B{r}", f, fmt="+0.0;-0.0;0.0" if key not in ("forecast", "actual") else F_ONE,
            bold=key in ("forecast", "actual"))
        BACKTEST[key] = f"B{r}"
    rchk = s5 + 1 + len(steps)
    put(ws, f"A{rchk}", "Check: forecast + steps = actual", GREY)
    first_step, last_step = s5 + 2, s5 + 6
    put(ws, f"B{rchk}", f"=ABS(B{s5 + 1}+SUM(B{first_step}:B{last_step})-B{s5 + 7})<0.000001", GREY)
    BACKTEST.update({"check": f"B{rchk}", "steps": (first_step, last_step),
                     "f_paid": f"N{R['f_paid']}", "a_paid": f"N{R['a_paid']}",
                     "error": f"N{re_}", "carry": f"B{t + 2}"})

    # Rates rows now that the bridge exists
    for i, (label, num, den, c24) in enumerate([("Triage pass", "C", "B", "C"),
                                                ("Call rate", "D", "C", "D"),
                                                ("Call-to-paid", "E", "D", "E")]):
        r = s3 + 2 + i
        put(ws, f"A{r}", label)
        put(ws, f"B{r}", f"={c24}{rr}", fmt=F_PCT)
        put(ws, f"C{r}", f"={num}{tot}/{den}{tot}", fmt=F_PCT)

    chart = LineChart()
    chart.title = "Paid clients per month, 2025: forecast vs actual"
    chart.height, chart.width = 8, 22
    for r, name in [(R["f_paid"], "Forecast"), (R["a_paid"], "Actual")]:
        chart.add_data(Reference(ws, min_col=2, max_col=13, min_row=r, max_row=r),
                       from_rows=True, titles_from_data=False)
    for s, name in zip(chart.series, ["Forecast (2024 drivers)", "Actual"]):
        s.tx = SeriesLabel(v=name)
        s.smooth = False
    chart.set_categories(Reference(ws, min_col=2, max_col=13, min_row=s2 + 1, max_row=s2 + 1))
    ws.add_chart(chart, f"D{s5}")
    ws.freeze_panes = "B4"


BACKTEST = {}


def top_down_tab(ws):
    title(ws, "Top-down check: last 12 months, then a growth rate",
          "A quick outside view to set next to the bottom-up forecast.")
    widths(ws, first=52, rest=16, n=4)
    header_row(ws, 4, ["", "Paid clients", "Revenue (BDT)"])
    last = (hist_row(pd.Period("2025-06", "M")), hist_row(pd.Period("2026-05", "M")))
    prior = (hist_row(pd.Period("2024-06", "M")), hist_row(pd.Period("2025-05", "M")))
    rows = [
        (5, "Last 12 months (Jun 2025 to May 2026)",
         lambda c: f"=SUM(History!{c}{last[0]}:{c}{last[1]})", GREEN),
        (6, "The 12 months before (Jun 2024 to May 2025)",
         lambda c: f"=SUM(History!{c}{prior[0]}:{c}{prior[1]})", GREEN),
        (7, "Growth", lambda c: None, BLACK),
        (8, "Top-down A: last 12 months, flat", lambda c: None, BLACK),
        (9, "Top-down B: last year's growth repeats", lambda c: None, BLACK),
        (10, "Bottom-up base (Forecast tab)", lambda c: None, GREEN),
        (11, "A minus bottom-up", lambda c: None, BLACK),
        (12, "B minus bottom-up", lambda c: None, BLACK),
    ]
    src = {"B": "E", "C": "F"}
    fc = {"B": fc_row("base", "paid_clients"), "C": fc_row("base", "revenue_bdt")}
    for r, label, f, color in rows:
        put(ws, f"A{r}", label, bold=r in (8, 9, 10))
        for c in "BC":
            fmt = F_ONE if c == "B" else F_BDT
            formula = {
                5: f(src[c]), 6: f(src[c]), 7: f"={c}5/{c}6-1", 8: f"={c}5", 9: f"={c}5*(1+{c}7)",
                10: f"=Forecast!N{fc[c]}", 11: f"={c}8-{c}10", 12: f"={c}9-{c}10"}[r]
            put(ws, f"{c}{r}", formula, color, F_PCT if r == 7 else fmt, bold=r in (8, 9, 10))
    put(ws, "A14", "Reading (default inputs):", bold=True)
    put(ws, "A15", "Flat (A) lands close to the bottom-up base, so the business-as-usual answer "
                   "agrees. Repeating last year's growth (B) gives an implausible figure: that "
                   "jump came from one-off changes (gates v2 and v3, the educator channel and "
                   "higher-priced Full Mentorship sales; see the Backtest tab). Those are already "
                   "inside the base rates, so they cannot add the same growth a second time.",
        wrap=True)
    ws.merge_cells("A15:C19")
    ws.row_dimensions[15].height = 30


def notes_tab(ws, inp):
    title(ws, "Notes: where each assumption comes from",
          "Flags: 'Thin' = fewer than 10 people behind the rate; 'Far from history' = 10 points "
          "(or 10%) or more away from Jan 2024 to May 2026. AI notes are added in Session 3.")
    header_row(ws, 4, ["Driver", "Channel", "Value used", "Based on (passed / total)",
                       "People behind it", "All history (Jan 2024 to May 2026)", "Difference",
                       "Flag", "Note (AI draft, Session 3)", "Approved by"])
    for c, w in zip("ABCDEFGHIJ", [20, 18, 12, 30, 12, 16, 12, 22, 60, 14]):
        ws.column_dimensions[c].width = w
    b, full = inp["base"], inp["full_history_rates"]
    approved = approved_notes()

    def ai_note(row, key):
        if approved and key in approved["notes"]:
            put(ws, f"I{row}", approved["notes"][key], wrap=True)
            put(ws, f"J{row}", f"{approved['approved_by']}, {approved['approved_on']}", GREY)
        else:
            put(ws, f"I{row}", "(not drafted yet: run draft_notes.py)", GREY, italic=True)
    r = 5
    stage = {"mql_rate": ("mqls", "leads", "C"), "call_rate": ("calls", "mqls", "D"),
             "call_to_paid": ("paid", "calls", "E")}
    for i, ch in enumerate(inp["channels"]):
        ir = IN["ch_first"] + i
        for d, (num, den, c_in) in stage.items():
            put(ws, f"A{r}", DRIVER_LABELS[d])
            put(ws, f"B{r}", ch)
            put(ws, f"C{r}", f"=Inputs!{c_in}{ir}", GREEN, F_PCT)
            bo, own = b["based_on"][ch][d], b["source"][ch][d] == "own"
            put(ws, f"D{r}", bo if own else f"{bo} too few; all-channel rate used", GREY)
            n_behind = int(bo.split("/")[0]) if own else None
            put(ws, f"E{r}", n_behind if own else "all channels", BLUE, F_COUNT)
            f = full[ch]
            put(ws, f"F{r}", f[num] / f[den] if f[den] else 0, BLUE, F_PCT)
            put(ws, f"G{r}", f"=C{r}-F{r}", fmt="+0.0%;-0.0%;0.0%")
            put(ws, f"H{r}", f'=IF(AND(ISNUMBER(E{r}),E{r}<10),"Thin",'
                             f'IF(ABS(G{r})>=0.1,"Far from history",""))')
            ai_note(r, f"{DRIVER_LABELS[d]}|{ch}")
            r += 1
    # revenue per client
    hist = inp["history"]
    window = hist[(hist["month"] >= pd.Period("2024-01", "M")) & (hist["month"] <= pd.Period("2026-05", "M"))]
    put(ws, f"A{r}", "Revenue per client")
    put(ws, f"B{r}", "All")
    put(ws, f"C{r}", f"=Inputs!{IN['rpc']}", GREEN, F_BDT)
    put(ws, f"D{r}", f"{b['rpc_based_on']} clients, Jun 2025 to May 2026", GREY)
    put(ws, f"E{r}", b["rpc_based_on"], BLUE, F_COUNT)
    put(ws, f"F{r}", window["revenue_bdt"].sum() / window["paid_clients"].sum(), BLUE, F_BDT)
    put(ws, f"G{r}", f"=C{r}/F{r}-1", fmt="+0.0%;-0.0%;0.0%")
    put(ws, f"H{r}", f'=IF(ABS(G{r})>=0.1,"Far from history","")')
    ai_note(r, "Revenue per client|All")
    r += 1
    for label, ref, basis in [("Leads per operator", IN["leads_cap"],
                               "Assumption: busiest month in the data was 88"),
                              ("Calls per operator", IN["calls_cap"],
                               "Assumption: busiest month in the data was 15")]:
        put(ws, f"A{r}", label)
        put(ws, f"B{r}", "All")
        put(ws, f"C{r}", f"=Inputs!{ref}", GREEN, F_COUNT)
        put(ws, f"D{r}", basis, GREY)
        put(ws, f"H{r}", "Assumption, not measured")
        ai_note(r, f"{label}|All")
        r += 1
    NOTES.update({"first": 5, "last": r - 1})
    ws.freeze_panes = "C5"


NOTES = {}


def scenarios_tab(ws):
    title(ws, "Scenarios: approved what-if runs",
          "Each row was asked in plain English, read into lever changes by Claude, checked and "
          "calculated by code, explained by Claude with figures filled in by code, and approved "
          "by a person. Figures are from that run, not live formulas: to see one live, type its "
          "changes into the adjustment cells on the Inputs tab.")
    header_row(ws, 4, ["ID", "Question", "Read as (by code)", "Paid clients: base",
                       "Paid clients: scenario", "Revenue (BDT): base", "Revenue (BDT): scenario",
                       "Months short: base", "Months short: scenario", "Notes", "Approved by"])
    for c, w in zip("ABCDEFGHIJK", [6, 40, 40, 12, 12, 14, 14, 11, 11, 70, 18]):
        ws.column_dimensions[c].width = w
    rows = approved_scenarios()
    if not rows:
        put(ws, "A5", "No approved scenarios yet: run ask_scenario.py, then approve.py.", GREY,
            italic=True)
    for i, rec in enumerate(rows):
        r, raw = 5 + i, rec["raw"]
        put(ws, f"A{r}", rec["id"])
        put(ws, f"B{r}", rec["question"], wrap=True)
        put(ws, f"C{r}", rec["changes_text"], wrap=True)
        put(ws, f"D{r}", raw["paid_base"], BLUE, F_ONE)
        put(ws, f"E{r}", raw["paid_scenario"], BLUE, F_ONE)
        put(ws, f"F{r}", raw["revenue_base"], BLUE, F_BDT)
        put(ws, f"G{r}", raw["revenue_scenario"], BLUE, F_BDT)
        put(ws, f"H{r}", raw["months_short_base"], BLUE, F_INT)
        put(ws, f"I{r}", raw["months_short_scenario"], BLUE, F_INT)
        put(ws, f"J{r}", "\n".join(f"- {b}" for b in rec["bullets"]), wrap=True)
        put(ws, f"K{r}", f"{rec['approved_by']}, {rec['approved_on']}", GREY)
    ws.freeze_panes = "B5"


def summary_tab(ws):
    title(ws, "Zorora Academy: 12-month forecast, Jun 2026 to May 2027",
          "Reconstructed operating dataset calibrated to Zorora's real patterns, not a CRM "
          "export. Drivers measured on Jan 2024 to May 2026.")
    widths(ws, first=58, rest=16, n=5)
    put(ws, "A4", "How to use it: change the blue cells on the Inputs tab; every other number "
                  "recalculates. Blue = typed-in numbers. Black = formulas. Green = links to "
                  "another tab. Yellow = key assumptions.", wrap=True)
    ws.merge_cells("A4:D5")
    ws.row_dimensions[4].height = 28

    section(ws, "A7", "Next 12 months")
    header_row(ws, 8, ["", "Low", "Base", "High"])
    lines = [(9, "Leads", "leads", F_COUNT), (10, "Paid clients", "paid_clients", F_ONE),
             (11, "Revenue (BDT)", "revenue_bdt", F_BDT), (12, "Revenue (CAD)", "revenue_cad", F_CAD)]
    for r, label, name, fmt in lines:
        put(ws, f"A{r}", label)
        for c, case in zip("BCD", ["low", "base", "high"]):
            put(ws, f"{c}{r}", f"=Forecast!N{fc_row(case, name)}", GREEN, fmt, bold=case == "base")
    put(ws, "A13", "Low and high put every driver at its weakest or strongest quarter of the "
                   "last 12 months at the same time: outer bounds, not likely outcomes.",
        GREY, italic=True)

    section(ws, "A15", "Capacity (base case)")
    put(ws, "A16", "Months short of operators (operators planned on the Inputs tab)")
    put(ws, "B16", "=Capacity!B19", GREEN, F_INT)
    put(ws, "A17", "Busiest month")
    put(ws, "B17", "=Capacity!B21", GREEN)
    put(ws, "A18", "Busiest month's lead load vs capacity")
    put(ws, "B18", "=Capacity!B22", GREEN, F_PCT)
    put(ws, "A19", "Months short in the high case")
    put(ws, "B19", "=Capacity!B20", GREEN, F_INT)

    section(ws, "A21", "Backtest: 2025 forecast from 2024 drivers")
    put(ws, "A22", "Forecast paid clients, 2025")
    put(ws, "B22", f"=Backtest!{BACKTEST['f_paid']}", GREEN, F_ONE)
    put(ws, "A23", "Actual paid clients, 2025")
    put(ws, "B23", f"=Backtest!{BACKTEST['a_paid']}", GREEN, F_COUNT)
    put(ws, "A24", "Forecast error")
    put(ws, "B24", f"=Backtest!{BACKTEST['error']}", GREEN, F_PCT)
    first, last = BACKTEST["steps"]
    put(ws, "A25", "Biggest driver of the gap")
    put(ws, "B25", f"=INDEX(Backtest!A{first}:A{last},MATCH(MAX(Backtest!B{first}:B{last}),"
                   f"Backtest!B{first}:B{last},0))")

    section(ws, "A27", "Checks (all must be TRUE)")
    rc1, rc2 = FORECAST_CHECK_ROWS
    hi = IN["case_col"]["high"]
    rng = lambda c: f"Inputs!{c}{IN['ch_first']}:{c}{IN['ch_last']}"
    checks = [
        ("Seasonality averages 1", f"=ABS(Inputs!{IN['season_avg']}-1)<0.000001"),
        ("Channel detail adds up to the base case", f"=AND(Forecast!B{rc1}:M{rc2})"),
        ("No rate goes above 100% in any case",
         f"=SUMPRODUCT(--({rng('C')}*{rng('F')}*Inputs!{hi}{IN['mult_row']['mql_rate']}>1))"
         f"+SUMPRODUCT(--({rng('D')}*{rng('G')}*Inputs!{hi}{IN['mult_row']['call_rate']}>1))"
         f"+SUMPRODUCT(--({rng('E')}*{rng('H')}*Inputs!{hi}{IN['mult_row']['call_to_paid']}>1))=0"),
        ("Low <= base <= high (paid clients)", "=AND(B10<=C10,C10<=D10)"),
        ("History: 27 paid clients in 2024 and 50 in 2025 (locked)",
         f"=AND(History!E{HISTORY['2024']}=27,History!E{HISTORY['2025']}=50)"),
        ("Backtest bridge adds up", f"=Backtest!{BACKTEST['check']}"),
    ]
    for i, (label, f) in enumerate(checks):
        put(ws, f"A{28 + i}", label)
        put(ws, f"B{28 + i}", f)
    r_all = 28 + len(checks)
    put(ws, f"A{r_all}", "All checks", bold=True)
    put(ws, f"B{r_all}", f"=AND(B28:B{r_all - 1})", bold=True)
    SUMMARY["all_checks"] = f"B{r_all}"


SUMMARY = {}


def main():
    inp = load_inputs()
    wb = build(inp)
    wb.save(OUT_FILE)
    print(f"Saved {OUT_FILE.name}. Open it in Excel; it calculates when it opens.")
    print("Then run: python check_model.py")


if __name__ == "__main__":
    main()
