"""
Session 3 command: ask a what-if question in plain English. Run from the project folder:

    python ask_scenario.py "What if Facebook leads drop 20% in November and December?"

Claude turns the question into lever changes, code checks them, the model recalculates,
Claude explains the result with figures that code fills in. Nothing goes into the
workbook until you approve it:

    python approve.py scenario S01 "Your Name"

Cost: about 2 to 5 US cents per question.
"""

import json
import sys

from src.claude import make_client
from src.inputs import load_inputs
from src.load import PROJECT_ROOT
from src.scenario import run

DRAFTS = PROJECT_ROOT / "scenarios" / "drafts"


def next_id():
    DRAFTS.mkdir(parents=True, exist_ok=True)
    n = len(list(DRAFTS.glob("S*.json"))) + 1
    return f"S{n:02d}"


def save_draft(record):
    sid = next_id()
    record["id"] = sid
    (DRAFTS / f"{sid}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False),
                                        encoding="utf-8")
    lines = [f"# Scenario {sid} (draft)", "", f"**Question:** {record['question']}", "",
             f"**Read as:** {record['changes_text']}"]
    if record.get("not_supported"):
        lines += ["", f"**Left out:** {record['not_supported']}"]
    lines += ["", "**Notes:**"] + [f"- {b}" for b in record["bullets"]]
    lines += ["", f"Draft source: {'AI' if record['source'] == 'ai' else 'template'}."]
    (DRAFTS / f"{sid}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return sid


def show(record, sid):
    r = record["raw"]
    print(f"\nI read your question as: {record['changes_text']}")
    if record.get("not_supported"):
        print(f"Left out: {record['not_supported']}")
    print("\nNext 12 months           Base          Scenario")
    print(f"  Leads             {r['leads_base']:>10,.0f}      {r['leads_scenario']:>10,.0f}")
    print(f"  Paid clients      {r['paid_base']:>10.1f}      {r['paid_scenario']:>10.1f}")
    print(f"  Revenue (BDT)     {r['revenue_base']:>10,.0f}      {r['revenue_scenario']:>10,.0f}")
    print(f"  Months short      {r['months_short_base']:>10}      {r['months_short_scenario']:>10}")
    attempts = len(record["explain_attempts"])
    print(f"\nNotes ({'written by Claude, passed all checks' if record['source'] == 'ai' else 'plain template: Claude did not pass the checks'}"
          f", {attempts} attempt(s)):")
    for b in record["bullets"]:
        print(f"  - {b}")
    print(f"\nSaved as {sid}. If the reading above is right and the notes are fine, run:")
    print(f'  python approve.py scenario {sid} "Your Name"')


def main():
    if len(sys.argv) < 2:
        sys.exit('Type your question in quotes, e.g.\n  python ask_scenario.py "What if Facebook '
                 'leads drop 20% in November and December?"')
    question = " ".join(sys.argv[1:])
    inp = load_inputs()
    print("Asking Claude (costs about 2 to 5 cents)...")
    record = run(question, inp, make_client(), inp["settings"]["model"])
    if record["status"] == "not_understood":
        tries = record["translate_attempts"]
        print("\nThe question could not be turned into model changes.")
        if record.get("not_supported"):
            print(f"Claude says: {record['not_supported']}")
        for t in tries[-1:]:
            for p in t["problems"]:
                print(f"  - {p}")
        sys.exit("Try rephrasing it with a channel, a month, and a percent or number of operators.")
    show(record, save_draft(record))


if __name__ == "__main__":
    main()
