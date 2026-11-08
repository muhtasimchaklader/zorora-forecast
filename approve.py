"""
Session 3 command: a person signs off the AI drafts before they go into the workbook.
Run from the project folder:

    python approve.py notes "Your Name"
    python approve.py scenario S01 "Your Name"

Approval re-checks every draft against a fresh run of the model, so nothing goes in if
the numbers no longer match. Then the workbook is rebuilt with the approved text.
Open zorora_forecast.xlsx in Excel and save it once afterwards.
"""

import json
import sys
from datetime import date

import build_model
from src.driver_notes import note_rows
from src.inputs import load_inputs
from src.load import PROJECT_ROOT
from src.scenario import apply_changes, check_changes, results

NOTES = PROJECT_ROOT / "notes"
SCENARIOS = PROJECT_ROOT / "scenarios"


def approve_notes(name):
    path = NOTES / "driver_notes_draft.json"
    if not path.exists():
        sys.exit("No draft yet. Run python draft_notes.py first.")
    record = json.loads(path.read_text(encoding="utf-8"))
    inp = load_inputs()
    rows = {r["key"]: r for r in note_rows(inp)}
    for n in record["notes"]:
        row = rows.get(n["key"])
        if row is None:
            sys.exit(f"NOT APPROVED: '{n['key']}' is no longer in the model. Draft again.")
        rendered = build_model.render_slots(n["with_slots"], row["slots"])
        if rendered != n["note"]:
            sys.exit(f"NOT APPROVED: the note or its figures for '{n['key']}' have changed since the draft. "
                     "Run python draft_notes.py again.")
    out = {"approved_by": name, "approved_on": date.today().isoformat(),
           "notes": {n["key"]: n["note"] for n in record["notes"]},
           "sources": {n["key"]: n["source"] for n in record["notes"]}}
    (NOTES / "driver_notes_approved.json").write_text(json.dumps(out, indent=2, ensure_ascii=False),
                                                      encoding="utf-8")
    print(f"APPROVED by {name}: {len(out['notes'])} notes.")


def approve_scenario(sid, name):
    path = SCENARIOS / "drafts" / f"{sid}.json"
    if not path.exists():
        sys.exit(f"No draft called {sid}. Check the scenarios/drafts folder.")
    record = json.loads(path.read_text(encoding="utf-8"))
    inp = load_inputs()
    problems = check_changes(record["changes"], inp)
    if problems:
        sys.exit("NOT APPROVED: the changes no longer pass the checks:\n- " + "\n- ".join(problems))
    _, slots, _ = results(inp, apply_changes(inp, record["changes"]))
    if slots != record["slots"]:
        sys.exit("NOT APPROVED: the model gives different figures now. Ask the question again.")
    record.update({"approved_by": name, "approved_on": date.today().isoformat()})
    (SCENARIOS / "approved").mkdir(parents=True, exist_ok=True)
    (SCENARIOS / "approved" / f"{sid}.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"APPROVED by {name}: scenario {sid} ({record['changes_text']}).")


def main():
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "notes":
        approve_notes(args[1])
    elif len(args) == 3 and args[0] == "scenario":
        approve_scenario(args[1].upper(), args[2])
    else:
        sys.exit('Use:  python approve.py notes "Your Name"\n'
                 '  or: python approve.py scenario S01 "Your Name"')
    build_model.main()
    print("Open zorora_forecast.xlsx in Excel, press Ctrl+S, close it. "
          "Then python check_model.py should pass again.")


if __name__ == "__main__":
    main()
