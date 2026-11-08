# Technical details

Back to the [README](../README.md). One-page summary: [writeup.md](writeup.md).

## Run it
```
pip install -r requirements.txt
python build_drivers.py      # locked-number checks, history, drivers, Session 1 checks
python build_model.py        # writes zorora_forecast.xlsx with live formulas
python check_model.py        # Excel and Python must agree (99 checks)
python ask_scenario.py "What if Facebook leads drop 20% in November and December?"
python draft_notes.py        # AI note for every assumption
python approve.py scenario S01 "Your Name"
python approve.py notes "Your Name"
python privacy_check.py      # run before publishing
```
The AI steps need an Anthropic API key: copy `.env.example` to `.env` and add the key.
`build_model.py` writes formulas only; Excel calculates them when the file opens. After
rebuilding, open the file in Excel and save it once before running `check_model.py`.

## The workbook
| Tab | What it shows |
|---|---|
| Summary | Next 12 months (low, base, high), capacity answer, backtest result, checks |
| Inputs | Every driver and assumption; blue cells can be changed |
| Forecast | Jun 2026 to May 2027 by month for each case, by channel, by quarter |
| Capacity | Operators needed each month, and how the answer moves with the capacity assumption and lead growth |
| Backtest | 2025 forecast from 2024 drivers vs actual, and a bridge explaining the gap |
| Top-down | Last 12 months flat and with last year's growth, next to the bottom-up base |
| Scenarios | Approved what-if runs: the question, how code read it, the result and the notes |
| History | What actually happened, Jan 2024 to May 2026 |
| Notes | Where each assumption comes from, flags for thin or unusual drivers, and an approved AI note for each |

## How the AI is used
1. **Claude reads the question, code checks it.** A what-if question becomes lever changes
   (lead volume, triage pass, call rate, call-to-paid, revenue per client, operators).
   Code rejects anything that is not a real lever, channel or forecast month, or is outside
   a set range, or would push a rate above 100%, and Claude gets up to three tries.
2. **Code calculates.** The model recalculates; Claude never computes a result.
3. **Claude drafts the wording, code checks it.** Explanations and assumption notes use
   placeholders such as `{paid_scenario}` that code fills in. Code rejects typed numbers,
   cause-and-effect wording, advice words and invented placeholders. After three failed
   tries a plain template is used.
4. **A person approves.** Approval re-runs the model and refuses a draft whose figures no
   longer match. Only approved text goes into the workbook.

## Data notes
The same data as the [monthly business review pipeline](https://github.com/muhtasimchaklader/zorora-monthly-business-review).

## Change log
- 2026-11-06: Revenue and prices scaled by undisclosed factors for confidentiality; revenue checks, workbook, backtest, scenario S01 and driver notes regenerated from the scaled data. Counts, rates and the AI wording are unchanged. Repository history restarted.
- 2026-10-29: Session 3. AI scenarios (question to checked lever changes, model recalculates, explanation with code-filled figures), AI driver notes, approval step that re-checks drafts against the model, Scenarios tab, write-up.
- 2026-10-29: Session 2. Excel model with live formulas (985), Python copy of the model and 99 Excel-vs-Python checks.
- 2026-10-29: Session 1. History (event and cohort views), two driver sets (base: Jun 2025 to May 2026; backtest: 2024 only), 26 locked-number checks and Session 1 checks.
- 2026-11-06: README shortened; the detail moved to this page, unchanged.
