# 2-minute screen recording: script

Have zorora_forecast.xlsx and the Command Prompt (in the project folder) open.

**0:00 to 0:15. What it is**
"This is a 12-month forecast for Zorora Academy, a study abroad consultancy. It answers
three questions: how many clients will pay, what revenue that brings, and whether one
intake operator can cope at peak."

**0:15 to 0:40. The model** (Inputs tab, then Forecast tab)
"Every number traces back to these blue inputs: leads by channel, triage pass, call rate,
call-to-paid, revenue per client, all measured on the last 12 months. Low and high come
from the weakest and strongest quarter."

**0:40 to 1:00. Capacity** (Capacity tab; change lead growth on Inputs to 10%, then undo)
"In the base case one operator just copes, at 98% in November. Add 10% more leads and
November needs a second person. This grid shows exactly where the answer flips."

**1:00 to 1:25. Backtest** (Backtest tab)
"To test the method, I forecast 2025 using only what we knew at the end of 2024. It said 31
paid clients; we did 50. The bridge shows why: most of the gap came from more calls turning
into paid clients, not from more leads."

**1:25 to 2:00. AI scenarios** (Command Prompt, then Scenarios tab)
Run `python ask_scenario.py "What if educator leads rise 30%?"`
"Claude turns the question into model changes, and code checks them before anything is
calculated. Claude explains the result, but code fills in every number, and nothing goes
into the workbook until a person approves it."
