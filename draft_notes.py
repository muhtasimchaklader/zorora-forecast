"""
Session 3 command: draft a short note for every assumption on the Notes tab.
Run from the project folder:

    python draft_notes.py

Code works out every figure and flag; Claude writes the wording with {slots}; code
checks each note and uses a plain template note for any that still fail after three
tries. Read notes/driver_notes_draft.md, then approve:

    python approve.py notes "Your Name"

Cost: about 3 to 8 US cents.
"""

import json

from src.claude import make_client
from src.driver_notes import draft
from src.inputs import load_inputs
from src.load import PROJECT_ROOT

FOLDER = PROJECT_ROOT / "notes"


def main():
    inp = load_inputs()
    print("Asking Claude (costs about 3 to 8 cents)...")
    record = draft(inp, make_client(), inp["settings"]["model"])
    FOLDER.mkdir(exist_ok=True)
    (FOLDER / "driver_notes_draft.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = ["# Driver notes (draft)", ""]
    for n in record["notes"]:
        flag = f" [{n['flag']}]" if n["flag"] else ""
        lines.append(f"- **{n['key'].replace('|', ', ')}**{flag}: {n['note']}"
                     f"{'' if n['source'] == 'ai' else ' _(template)_'}")
    (FOLDER / "driver_notes_draft.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    ai = sum(n["source"] == "ai" for n in record["notes"])
    for i, a in enumerate(record["attempts"], 1):
        print(f"  Attempt {i}: {a['accepted']} notes passed so far, {len(a['problems'])} to fix")
    print(f"\n{ai} of {len(record['notes'])} notes written by Claude and passed every check; "
          f"{len(record['notes']) - ai} use the plain template.\n")
    for n in record["notes"]:
        print(f"- {n['key'].replace('|', ', ')}: {n['note']}")
    print("\nSaved notes/driver_notes_draft.md. If they read well, run:")
    print('  python approve.py notes "Your Name"')


if __name__ == "__main__":
    main()
