# Driver-based forecast for Zorora Academy

**Asef Chaklader** · Excel, Python, Claude API · Built on 29 months of data, tested with a backtest

## The task
Zorora Academy is a study abroad consultancy in Dhaka. Before peak season, leadership needs
three answers: how many clients will pay over the next 12 months, what revenue that brings,
and whether one intake operator can handle the busiest months.

## What I built
An Excel model with live formulas: every figure traces back to a blue input cell.

1. **Driver chain.** For each of six channels and each month: leads, times triage pass,
   times call rate, times call-to-paid, gives paid clients; times revenue per client gives
   revenue. Drivers come from the last 12 months of data. Seasonality comes from the real
   monthly pattern, and calls and payments land in the arrival month or the month after,
   as they did in the data. A channel with fewer than 20 people behind a rate uses the
   all-channel rate instead.
2. **Low, base and high.** The range comes from the weakest and strongest quarter of the
   last 12 months, so it reflects how much each driver actually moved.
3. **Capacity.** Operators needed each month, from leads and calls per operator, plus a
   grid showing when the answer flips as lead growth and the capacity assumption change.
4. **Backtest.** The same method, fed only what was known at the end of 2024, forecasts
   2025. It is then compared with what happened, and a bridge splits the gap by driver.
5. **Top-down check.** Last 12 months flat, and with last year's growth, next to the
   bottom-up forecast.
6. **AI scenarios and notes.** A question in plain English ("what if Facebook leads drop
   20% in November and December?") becomes lever changes, which code checks before the
   model recalculates. Claude explains the result using placeholders that code fills in,
   so it never types a figure. Claude also drafts a note for each assumption. A person
   approves both before they go into the workbook.

## Results (default inputs)
- **Next 12 months, base case:** about 69 paid clients and BDT 2.60M (about CAD 30,000),
  close to the last 12 months.
- **Capacity:** one operator copes, but November runs at 98% of one operator's lead
  capacity. With 10% more leads, or a real capacity of 80 leads a month, November needs a
  second person. The high case needs one in October and November.
- **Backtest:** forecasting 2025 from 2024's drivers gives 31 paid clients against an actual 50.
  The bridge shows where the gap came from: call-to-paid +14, call rate +4.5, triage
  pass +3.5, more leads and the new educator channel +2, and payment timing -5. Most of
  the gap came from what happened after the first call, not from more leads.
- **Top-down:** last 12 months flat lands next to the bottom-up base. Repeating last
  year's growth gives an implausible figure, because that jump came from one-off
  changes that are already in the base rates.

## Controls
- 26 checks reproduce Zorora's locked figures from the raw data before anything is built.
- History ties back to 27 paid clients in 2024, 50 in 2025 and BDT 3,160,500 over the window.
- The drivers rebuild the last 12 months' paid clients within 1 client (68.4 against 69).
- A Python copy of the model must match Excel on 99 figures, revenue to the taka.
- Workbook checks: seasonality averages 1, channels add up to totals, no rate above 100%,
  low below base below high, and the backtest bridge adds up.
- AI changes are limited to real levers, channels and months within set ranges, and a
  person approves every AI draft, which is re-checked against the model first.

## Limits
- Low and high move every driver to its extreme at once: outer bounds, not likely outcomes.
- Monthly figures are small (5 to 10 paid clients), so quarterly totals are steadier.
- Leads and calls per operator are assumptions, not measured; the capacity grid shows how
  much they matter.
- The bridge swaps drivers in funnel order; another order would split the steps slightly
  differently.

*Data: a reconstructed operating dataset calibrated to Zorora's real patterns, not a CRM
export. Names are removed, and operators appear only as roles.*
