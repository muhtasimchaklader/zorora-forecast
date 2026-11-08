"""
Reads the Anthropic API key from the private .env file in the project folder.

The key is never written in the code, never printed, and never uploaded
(.gitignore keeps .env off GitHub).
"""

from src.load import PROJECT_ROOT


def get_api_key():
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        raise SystemExit("\nNo .env file found. Copy .env.example, name it .env, "
                         "and paste your API key into it.\n")
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("ANTHROPIC_API_KEY="):
            key = line.split("=", 1)[1].strip()
            if key and key != "paste-your-key-here":
                return key
    raise SystemExit("\nThe .env file has no API key yet. Paste it after ANTHROPIC_API_KEY=\n")
