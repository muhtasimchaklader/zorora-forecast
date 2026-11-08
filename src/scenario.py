"""
What-if scenarios, with the same controls as the monthly business review:
  1. Claude turns the question into lever changes. It never calculates anything.
  2. Code checks every change: a real lever, a real channel and month, a sensible size.
  3. The model (src/model.py) recalculates. Code formats every figure.
  4. Claude explains the result using {slots}; code fills in the figures and rejects any
     bullet that types a number, uses cause-and-effect wording or invents a slot.
  5. A person approves it (approve.py) before it is added to the workbook.
"""

import copy
import re
from datetime import datetime

from src.claude import ask_json
from src.model import capacity, forecast

LEVERS = {
    "lead_volume": {"label": "leads", "min": -100, "max": 200, "by_channel": True, "by_month": True},
    "triage_pass": {"label": "triage pass", "min": -50, "max": 50, "by_channel": True, "by_month": False},
    "call_rate": {"label": "call rate", "min": -50, "max": 50, "by_channel": True, "by_month": False},
    "call_to_paid": {"label": "call-to-paid", "min": -50, "max": 50, "by_channel": True,
                     "by_month": False},
    "revenue_per_client": {"label": "revenue per client", "min": -50, "max": 100,
                           "by_channel": False, "by_month": False},
    "operators": {"label": "operators planned", "min": 1, "max": 5, "by_channel": False,
                  "by_month": True},
}
RATE_ADJ = {"triage_pass": ("mql_adj", "mql_rate"), "call_rate": ("call_adj", "call_rate"),
            "call_to_paid": ("paid_adj", "call_to_paid")}
MAX_ATTEMPTS = 3

TRANSLATE_SYSTEM = """You turn a manager's what-if question about Zorora Academy's 12-month
forecast into changes to the model's levers. You never calculate results.

Levers:
- lead_volume: percent change to the number of leads. One channel or all; specific months or all.
- triage_pass: percent change to the share of leads that pass triage. One channel or all; all months.
- call_rate: percent change to the share of triaged leads that take a diagnostic call. One channel or all; all months.
- call_to_paid: percent change to the share of calls that become paid clients. One channel or all; all months.
- revenue_per_client: percent change to average revenue per paid client. Channel "all"; months "all".
- operators: set the number of operators planned (a whole number from 1 to 5) in the given months. Channel "all".

Value: for percent levers, the percent as a number (a 20% drop is -20, a 10% rise is 10).
For operators, the number of operators.
Use "all" for channel or months when the question does not narrow them. Use the exact
channel names and month codes given. If part of the question cannot be expressed with these
levers, leave it out and say what was left out in not_supported (in words). If nothing can be
expressed, return an empty list of changes."""

EXPLAIN_SYSTEM = """You explain the result of a what-if run on Zorora Academy's forecast
model to a manager. Rules:
1. Write 2 to 4 bullets, one sentence each.
2. Never type a number, percent, currency, year or month. Use the {slots} given, written
   exactly with curly braces. Spelled-out numbers (one, two, twenty, hundred...) count as numbers.
3. Use only the slots listed. Do not invent slots.
4. Describe what the model calculates, not what will happen: write "in the model" or "the
   forecast shows". Never use "will", and no cause-and-effect words (because, due to, caused,
   leads to, drives, results in, as a result).
5. No advice words (should, must, recommend, need to). A person decides.
6. At most three slots in one bullet.
7. One bullet must give paid clients with both {paid_base} and {paid_scenario}.
8. If the months short of operators differ, one bullet must give {months_short_scenario}.
9. Slots already include their units ("69.4 paid clients", "BDT 2,601,882", "2 of 12
   months"). Do not repeat the unit or the currency next to a slot."""

BANNED = ["will", "because", "due to", "caused", "causes", "leads to", "lead to", "drives",
          "driven", "results in", "as a result", "should", "must", "recommend", "need to",
          "guarantee", "definitely", "bdt", "taka", "cad", "tk"]
NUMBER_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
                "ten", "eleven", "twelve", "twenty", "thirty", "forty", "fifty", "hundred",
                "thousand", "million", "lakh", "crore", "percent", "half", "dozen"]


def translate_schema(channels, months):
    return {
        "type": "object",
        "properties": {
            "changes": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "lever": {"type": "string", "enum": list(LEVERS)},
                    "channel": {"type": "string", "enum": channels + ["all"]},
                    "months": {"type": "array", "items": {"type": "string",
                                                          "enum": months + ["all"]}},
                    "value": {"type": "number"},
                },
                "required": ["lever", "channel", "months", "value"],
                "additionalProperties": False}},
            "not_supported": {"type": "string"},
        },
        "required": ["changes", "not_supported"],
        "additionalProperties": False,
    }


EXPLAIN_SCHEMA = {"type": "object", "properties": {"bullets": {"type": "array",
                  "items": {"type": "string"}}}, "required": ["bullets"],
                  "additionalProperties": False}


def month_codes(inp):
    return [str(m) for m in inp["months"]]


# ---------- step 2: check the changes ----------
def check_changes(changes, inp):
    problems = []
    codes = month_codes(inp)
    if not changes:
        problems.append("No changes were given.")
    for i, c in enumerate(changes, 1):
        lever, ch, months, value = (c.get("lever"), c.get("channel"), c.get("months"),
                                    c.get("value"))
        spec = LEVERS.get(lever)
        if spec is None:
            problems.append(f"Change {i}: '{lever}' is not a lever.")
            continue
        if ch != "all" and ch not in inp["channels"]:
            problems.append(f"Change {i}: '{ch}' is not a channel.")
        if not spec["by_channel"] and ch != "all":
            problems.append(f"Change {i}: {spec['label']} can only be changed for all channels.")
        if not isinstance(months, list) or not months:
            problems.append(f"Change {i}: months must be a list.")
        else:
            bad = [m for m in months if m != "all" and m not in codes]
            if bad:
                problems.append(f"Change {i}: {bad} are not forecast months ({codes[0]} to {codes[-1]}).")
            if not spec["by_month"] and months != ["all"]:
                problems.append(f"Change {i}: {spec['label']} applies to all months; use [\"all\"].")
        if not isinstance(value, (int, float)):
            problems.append(f"Change {i}: value must be a number.")
        elif not spec["min"] <= value <= spec["max"]:
            problems.append(f"Change {i}: {value} is outside the allowed range "
                            f"{spec['min']} to {spec['max']} for {spec['label']}.")
        elif lever == "operators" and value != int(value):
            problems.append(f"Change {i}: operators must be a whole number.")
    if not problems:
        scen = apply_changes(inp, changes)
        for lever, (adj, rate) in RATE_ADJ.items():
            for ch in inp["channels"]:
                if inp["base"][rate][ch] * scen["levers"][adj][ch] > 1:
                    problems.append(f"{LEVERS[lever]['label']} for {ch} would go above 100%.")
    return problems


# ---------- step 3: apply and recalculate ----------
def _targets(change, inp):
    chans = inp["channels"] if change["channel"] == "all" else [change["channel"]]
    codes = month_codes(inp)
    idx = range(len(codes)) if change["months"] == ["all"] or "all" in change["months"] \
        else [codes.index(m) for m in change["months"]]
    return chans, list(idx)


def apply_changes(inp, changes):
    scen = copy.deepcopy(inp)
    lv = scen["levers"]
    for c in changes:
        chans, idx = _targets(c, inp)
        f = 1 + c["value"] / 100
        if c["lever"] == "lead_volume":
            for ch in chans:
                for j in idx:
                    lv["lead_adj"][ch][j] *= f
        elif c["lever"] in RATE_ADJ:
            for ch in chans:
                lv[RATE_ADJ[c["lever"]][0]][ch] *= f
        elif c["lever"] == "revenue_per_client":
            lv["rpc_adj"] *= f
        elif c["lever"] == "operators":
            for j in idx:
                scen["capacity"]["planned"][j] = int(c["value"])
    return scen


def describe_changes(changes, inp):
    """The changes in plain words, written by code (the person checks this reading)."""
    labels = {str(m): m.strftime("%b %Y") for m in inp["months"]}
    parts = []
    for c in changes:
        spec = LEVERS[c["lever"]]
        who = "all channels" if c["channel"] == "all" else c["channel"]
        when = "every month" if "all" in c["months"] else ", ".join(labels[m] for m in c["months"])
        if c["lever"] == "operators":
            parts.append(f"operators planned set to {int(c['value'])} in {when}")
        elif c["lever"] == "revenue_per_client":
            parts.append(f"revenue per client {c['value']:+g}%")
        elif c["lever"] == "lead_volume":
            parts.append(f"{who} leads {c['value']:+g}% in {when}")
        else:
            parts.append(f"{spec['label']} {c['value']:+g}% for {who}")
    return "; ".join(parts)


def results(inp, scen):
    base, new = forecast(inp, "base"), forecast(scen, "base")
    cb, cn = capacity(inp, base), capacity(scen, new)
    c_inp, c_scen = inp["capacity"], scen["capacity"]

    def load(fc, cap):
        loads = [l / (p * cap["leads_per_operator"]) for l, p in zip(fc["leads"], cap["planned"])]
        k = max(range(len(loads)), key=loads.__getitem__)
        return loads[k], fc.index[k].strftime("%b %Y")

    lb, _ = load(base, c_inp)
    ln, mn = load(new, c_scen)
    raw = {
        "leads_base": base["leads"].sum(), "leads_scenario": new["leads"].sum(),
        "paid_base": base["paid_clients"].sum(), "paid_scenario": new["paid_clients"].sum(),
        "revenue_base": base["revenue_bdt"].sum(), "revenue_scenario": new["revenue_bdt"].sum(),
        "months_short_base": cb["months_short"], "months_short_scenario": cn["months_short"],
        "busiest_load_base": lb, "busiest_load_scenario": ln,
    }
    slots = {
        "leads_base": f"{raw['leads_base']:,.0f} leads",
        "leads_scenario": f"{raw['leads_scenario']:,.0f} leads",
        "leads_change": f"{raw['leads_scenario'] - raw['leads_base']:+,.0f} leads",
        "paid_base": f"{raw['paid_base']:.1f} paid clients",
        "paid_scenario": f"{raw['paid_scenario']:.1f} paid clients",
        "paid_change": f"{raw['paid_scenario'] - raw['paid_base']:+.1f} paid clients",
        "paid_change_pct": f"{raw['paid_scenario'] / raw['paid_base'] - 1:+.1%}",
        "revenue_base": f"BDT {raw['revenue_base']:,.0f}",
        "revenue_scenario": f"BDT {raw['revenue_scenario']:,.0f}",
        "revenue_change": f"{'+' if raw['revenue_scenario'] >= raw['revenue_base'] else '-'}BDT "
                          f"{abs(raw['revenue_scenario'] - raw['revenue_base']):,.0f}",
        "months_short_base": f"{raw['months_short_base']} of 12 months",
        "months_short_scenario": f"{raw['months_short_scenario']} of 12 months",
        "busiest_month_scenario": mn,
        "busiest_load_base": f"{raw['busiest_load_base']:.0%} of one operator's lead capacity",
        "busiest_load_scenario": f"{raw['busiest_load_scenario']:.0%} of the planned lead capacity",
        "period": f"{inp['months'][0].strftime('%b %Y')} to {inp['months'][-1].strftime('%b %Y')}",
    }
    meaning = {
        "leads_base": "leads over the next 12 months, base case",
        "leads_scenario": "leads over the next 12 months, this scenario",
        "leads_change": "difference in leads",
        "paid_base": "paid clients over the next 12 months, base case",
        "paid_scenario": "paid clients over the next 12 months, this scenario",
        "paid_change": "difference in paid clients",
        "paid_change_pct": "difference in paid clients, as a percent",
        "revenue_base": "revenue over the next 12 months, base case",
        "revenue_scenario": "revenue over the next 12 months, this scenario",
        "revenue_change": "difference in revenue",
        "months_short_base": "months short of operators, base case",
        "months_short_scenario": "months short of operators, this scenario",
        "busiest_month_scenario": "busiest month for leads in this scenario",
        "busiest_load_base": "busiest month's lead load, base case",
        "busiest_load_scenario": "busiest month's lead load vs planned capacity, this scenario",
        "period": "the forecast period",
    }
    return raw, slots, meaning


# ---------- step 4: explanation checks ----------
SLOT = re.compile(r"\{([a-z_]+)\}")


def repeated_units(text, slots):
    """Slots already carry their unit ('11 people', 'BDT 37,515'). Catch '{behind} people'
    or 'BDT {revenue_base}': the unit written again right next to the slot."""
    found = []
    for m in SLOT.finditer(text):
        value = slots.get(m.group(1), "")
        digits = [i for i, ch in enumerate(value) if ch.isdigit()]
        if not digits:
            continue
        unit = re.findall(r"[A-Za-z]+", value[digits[-1] + 1:])
        prefix = re.findall(r"[A-Za-z]+", value[:digits[0]])
        nxt = re.match(r"\s*([A-Za-z]+)", text[m.end():])
        prev = re.search(r"([A-Za-z]+)\s*$", text[:m.start()])
        if unit and nxt and nxt.group(1).lower() == unit[0].lower():
            found.append(f"{{{m.group(1)}}} {nxt.group(1)}")
        if prefix and prev and prev.group(1).lower() == prefix[-1].lower():
            found.append(f"{prev.group(1)} {{{m.group(1)}}}")
    rendered = SLOT.sub(lambda m: slots.get(m.group(1), ""), text)
    found += [f"{w} {w}" for w in re.findall(r"\b([A-Za-z]+)\s+\1\b", rendered, flags=re.I)]
    return found


def bullet_problems(bullets, slots, raw):
    problems = []
    if not 2 <= len(bullets) <= 4:
        problems.append(f"Write 2 to 4 bullets (got {len(bullets)}).")
    used_all = set()
    for i, b in enumerate(bullets, 1):
        used = SLOT.findall(b)
        used_all.update(used)
        doubled = repeated_units(b, slots)
        if doubled:
            problems.append(f"Bullet {i}: repeats a unit the slot already has: {doubled}.")
        unknown = [u for u in used if u not in slots]
        if unknown:
            problems.append(f"Bullet {i}: unknown slots {unknown}.")
        text = SLOT.sub(" ", b).lower()
        if re.search(r"\d", text):
            problems.append(f"Bullet {i}: types a number. Use the slots.")
        words = set(re.findall(r"[a-z]+", text))
        nums = [w for w in NUMBER_WORDS if w in words]
        if nums:
            problems.append(f"Bullet {i}: spelled-out number {nums}. Use the slots.")
        banned = [w for w in BANNED if re.search(rf"\b{re.escape(w)}\b", text)]
        if banned:
            problems.append(f"Bullet {i}: banned wording {banned}.")
        if "%" in text or "$" in text:
            problems.append(f"Bullet {i}: types a percent or currency sign.")
        if len(used) > 3:
            problems.append(f"Bullet {i}: more than three slots.")
    if not any("{paid_base}" in b and "{paid_scenario}" in b for b in bullets):
        problems.append("No bullet gives paid clients with both {paid_base} and {paid_scenario}.")
    if raw["months_short_base"] != raw["months_short_scenario"] and \
            "months_short_scenario" not in used_all:
        problems.append("Months short of operators changed, but no bullet gives "
                        "{months_short_scenario}.")
    return problems


def template_bullets(raw):
    bullets = ["In the model, paid clients over {period} move from {paid_base} to "
               "{paid_scenario} ({paid_change}).",
               "Revenue moves from {revenue_base} to {revenue_scenario}."]
    if raw["months_short_base"] != raw["months_short_scenario"]:
        bullets.append("Months short of operators: {months_short_base} in the base case, "
                       "{months_short_scenario} in this scenario.")
    else:
        bullets.append("The busiest month, {busiest_month_scenario}, runs at "
                       "{busiest_load_scenario}.")
    return bullets


def render(bullets, slots):
    return [SLOT.sub(lambda m: slots[m.group(1)], b) for b in bullets]


# ---------- the whole run ----------
def run(question, inp, client, model):
    codes = month_codes(inp)
    record = {"question": question, "model": model, "created": datetime.now().isoformat(timespec="seconds"),
              "translate_attempts": [], "explain_attempts": []}

    # 1-2. Translate and check
    prompt = (f"Question: {question}\n\nChannels: {', '.join(inp['channels'])}\n"
              f"Forecast months (codes): {', '.join(codes)}\n"
              f"(The forecast runs {codes[0]} to {codes[-1]}; peak season is Oct to Dec.)")
    changes = None
    for _ in range(MAX_ATTEMPTS):
        data, info = ask_json(client, model, TRANSLATE_SYSTEM, prompt,
                              translate_schema(inp["channels"], codes))
        if data is None:
            problems = [f"Could not read JSON from the reply (stop reason: {info['stop_reason']})."]
        else:
            problems = check_changes(data.get("changes", []), inp)
        record["translate_attempts"].append({"reply": data, "problems": problems})
        if not problems:
            changes = data["changes"]
            record["not_supported"] = data.get("not_supported", "").strip()
            break
        if data is not None and not data.get("changes"):
            record["not_supported"] = data.get("not_supported", "").strip()
            break
        prompt += "\n\nYour last answer had these problems. Fix them:\n- " + "\n- ".join(problems)
    if changes is None:
        record["status"] = "not_understood"
        return record

    # 3. Recalculate
    scen = apply_changes(inp, changes)
    raw, slots, meaning = results(inp, scen)
    record.update({"status": "drafted", "changes": changes,
                   "changes_text": describe_changes(changes, inp), "raw": raw, "slots": slots})

    # 4. Explain and check
    facts = "\n".join(f"{{{k}}} = {slots[k]}  ({meaning[k]})" for k in slots)
    prompt = (f"Question: {question}\nChanges tested (by code): {record['changes_text']}\n\n"
              f"SLOTS\n{facts}\n\nWrite the bullets now.")
    bullets = None
    for _ in range(MAX_ATTEMPTS):
        data, info = ask_json(client, model, EXPLAIN_SYSTEM, prompt, EXPLAIN_SCHEMA)
        draft = [str(b).strip() for b in (data or {}).get("bullets", []) if str(b).strip()]
        problems = bullet_problems(draft, slots, raw) if draft else \
            [f"Could not read bullets from the reply (stop reason: {info['stop_reason']})."]
        record["explain_attempts"].append({"bullets": draft, "problems": problems})
        if not problems:
            bullets = draft
            record["source"] = "ai"
            break
        prompt += "\n\nYour last bullets had these problems. Fix them:\n- " + "\n- ".join(problems)
    if bullets is None:
        bullets = template_bullets(raw)
        record["source"] = "template"
    record["bullets_with_slots"] = bullets
    record["bullets"] = render(bullets, slots)
    return record
