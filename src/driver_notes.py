"""
AI driver notes for the Notes tab, with the same controls as the scenarios:
code works out every figure and flag, Claude writes one short note per assumption
using {slots}, code checks each note, and a person approves them (approve.py).
"""

import re
from datetime import datetime

from src.claude import ask_json
from src.inputs import DRIVER_LABELS
from src.scenario import BANNED, NUMBER_WORDS, SLOT, repeated_units

MAX_ATTEMPTS = 3
MAX_WORDS = 30
CAUTION = ["thin", "few", "small", "rough", "caution", "careful", "treat", "uncertain",
           "history", "earlier", "past", "assumption", "check", "watch", "differs", "above",
           "below", "higher", "lower"]
STAGES = {"mql_rate": ("mqls", "leads"), "call_rate": ("calls", "mqls"),
          "call_to_paid": ("paid", "calls")}

SYSTEM = """You write one short note for each assumption in Zorora Academy's forecast model,
for a manager reading the Notes tab. Rules:
1. One sentence per note, at most 30 words.
2. Never type a number, percent, currency, year or month. Use only the slots listed for that
   row, written exactly with curly braces. Spelled-out numbers count as numbers.
3. Say what the assumption rests on. If the row has a flag, the note must say plainly why
   to be careful (for example that it rests on few people, or that it differs from history).
4. No cause-and-effect claims (because, due to, caused, leads to, drives, results in), no
   "will", and no advice words (should, must, recommend, need to).
5. Slots already include their units ("BDT 37,515", "+4.9 points", "26.8%"), except
   {behind}, which is a bare count: write "{behind} people" or "{behind} paid clients".
   Do not repeat a unit or currency that a slot already has.
6. Return a note for every key, using the keys exactly as given."""

SCHEMA = {"type": "object", "properties": {"notes": {"type": "array", "items": {
    "type": "object", "properties": {"key": {"type": "string"}, "note": {"type": "string"}},
    "required": ["key", "note"], "additionalProperties": False}}},
    "required": ["notes"], "additionalProperties": False}


def note_rows(inp):
    """Every Notes-tab row with its figures, flag and allowed slots (same order as the tab)."""
    b, full = inp["base"], inp["full_history_rates"]
    rows = []
    for ch in inp["channels"]:
        for d, (num, den) in STAGES.items():
            own = b["source"][ch][d] == "own"
            value = b[d][ch]
            hist = full[ch][num] / full[ch][den] if full[ch][den] else 0.0
            behind = int(b["based_on"][ch][d].split("/")[0]) if own else None
            diff = value - hist
            flag = "Thin" if behind is not None and behind < 10 else \
                ("Far from history" if abs(diff) >= 0.10 else "")
            slots = {"value": f"{value:.1%}", "history": f"{hist:.1%}",
                     "difference": f"{round(diff * 100, 1) + 0.0:+.1f} points"}
            if behind is not None:
                slots["behind"] = f"{behind}"
            rows.append({"key": f"{DRIVER_LABELS[d]}|{ch}", "driver": DRIVER_LABELS[d],
                         "channel": ch, "flag": flag, "pooled": not own, "slots": slots})
    hist = inp["history"]
    rpc_hist = hist["revenue_bdt"].sum() / hist["paid_clients"].sum()
    diff = b["rpc"] / rpc_hist - 1
    rows.append({"key": "Revenue per client|All", "driver": "Revenue per client", "channel": "All",
                 "flag": "Far from history" if abs(diff) >= 0.10 else "", "pooled": False,
                 "slots": {"value": f"BDT {b['rpc']:,.0f}", "history": f"BDT {rpc_hist:,.0f}",
                           "difference": f"{diff:+.1%}",
                           "behind": f"{b['rpc_based_on']}"}})
    for label, k in [("Leads per operator", "leads_per_operator"),
                     ("Calls per operator", "calls_per_operator")]:
        rows.append({"key": f"{label}|All", "driver": label, "channel": "All",
                     "flag": "Assumption, not measured", "pooled": False,
                     "slots": {"value": f"{inp['capacity'][k]} a month"}})
    return rows


def note_problems(row, note):
    problems = []
    used = SLOT.findall(note)
    unknown = [u for u in used if u not in row["slots"]]
    if unknown:
        problems.append(f"unknown slots {unknown} (allowed: {list(row['slots'])})")
    doubled = repeated_units(note, row["slots"])
    if doubled:
        problems.append(f"repeats a unit the slot already has: {doubled}")
    text = SLOT.sub(" ", note).lower()
    if re.search(r"\d", text) or "%" in text:
        problems.append("types a number")
    words = re.findall(r"[a-z]+", text)
    if any(w in NUMBER_WORDS for w in words):
        problems.append("spelled-out number")
    banned = [w for w in BANNED if re.search(rf"\b{re.escape(w)}\b", text)]
    if banned:
        problems.append(f"banned wording {banned}")
    if len(note.split()) > MAX_WORDS:
        problems.append(f"longer than {MAX_WORDS} words")
    if row["flag"] and not any(c in words for c in CAUTION):
        problems.append(f"flagged '{row['flag']}' but does not say why to be careful")
    return problems


def template_note(row):
    if row["driver"] in ("Leads per operator", "Calls per operator"):
        return ("An assumption, not measured: {value} per operator. The Capacity tab shows "
                "how much the answer depends on it.")
    if row["flag"] == "Thin":
        return "Rests on only {behind} people, so treat {value} as rough."
    if row["pooled"]:
        return ("Too few for this channel alone, so the all-channel rate of {value} is used; "
                "its own history was {history}.")
    if row["flag"] == "Far from history":
        return "{value} now, against {history} over the full history ({difference})."
    return "Measured on {behind} people over the last year; close to its history of {history}."


def draft(inp, client, model):
    rows = note_rows(inp)
    by_key = {r["key"]: r for r in rows}
    listing = "\n".join(
        f"- key: {r['key']} | flag: {r['flag'] or 'none'}"
        f"{' | all-channel rate used (too few for this channel)' if r['pooled'] else ''} | slots: "
        + ", ".join(f"{{{k}}} = {v}" for k, v in r["slots"].items())
        + (f" ({{behind}} is the number of {'paid clients' if r['driver'] == 'Revenue per client' else 'people who passed this stage'}"
           ", a bare count: write the noun after it)" if "behind" in r["slots"] else "")
        for r in rows)
    prompt = f"ROWS\n{listing}\n\nWrite the notes now."
    record = {"model": model, "created": datetime.now().isoformat(timespec="seconds"), "attempts": []}
    accepted = {}
    for _ in range(MAX_ATTEMPTS):
        data, info = ask_json(client, model, SYSTEM, prompt, SCHEMA)
        got = {n.get("key"): str(n.get("note", "")).strip() for n in (data or {}).get("notes", [])}
        problems = {}
        for key, row in by_key.items():
            if key in accepted:
                continue
            if key not in got or not got[key]:
                problems[key] = ["missing"]
                continue
            p = note_problems(row, got[key])
            if p:
                problems[key] = p
            else:
                accepted[key] = got[key]
        record["attempts"].append({"accepted": len(accepted), "problems": problems,
                                   "stop_reason": info.get("stop_reason")})
        if not problems:
            break
        prompt += ("\n\nThese notes had problems. Rewrite only these keys:\n" +
                   "\n".join(f"- {k}: {'; '.join(v)}" for k, v in problems.items()))
    notes = []
    for r in rows:
        source = "ai" if r["key"] in accepted else "template"
        text = accepted.get(r["key"], template_note(r))
        notes.append({"key": r["key"], "flag": r["flag"], "source": source,
                      "with_slots": text,
                      "note": SLOT.sub(lambda m: r["slots"][m.group(1)], text)})
    record["notes"] = notes
    return record
