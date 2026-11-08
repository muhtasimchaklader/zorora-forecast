"""
One way to ask Claude for JSON, shared by the scenario tool and the driver notes.

Newer models think before answering, which uses output tokens, so effort is kept low
and there is room for the thinking. If the model refuses an option, the next, simpler
request is tried. The key comes from the private .env file (src/apikey.py).
"""

import json

MAX_TOKENS = 8000


def make_client():
    import anthropic

    from src.apikey import get_api_key
    return anthropic.Anthropic(api_key=get_api_key())


def ask_json(client, model, system, user_text, schema):
    """Return (parsed JSON or None, info about the reply)."""
    import anthropic

    shape = json.dumps(schema)
    messages = [{"role": "user", "content": user_text +
                 f"\n\nReply with JSON only, matching this schema and nothing else: {shape}"}]
    options_list = [
        {"output_config": {"format": {"type": "json_schema", "schema": schema}, "effort": "low"}},
        {"output_config": {"format": {"type": "json_schema", "schema": schema}}},
        {},
    ]
    last_error = None
    for options in options_list:
        try:
            reply = client.messages.create(model=model, max_tokens=MAX_TOKENS, system=system,
                                           messages=messages, **options)
        except anthropic.BadRequestError as e:
            last_error = e
            continue
        text = "".join(getattr(b, "text", "") or "" for b in reply.content
                       if getattr(b, "type", None) == "text")
        info = {"stop_reason": getattr(reply, "stop_reason", None), "text_start": text[:300]}
        return parse_json(text), info
    raise last_error


def parse_json(text):
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None
