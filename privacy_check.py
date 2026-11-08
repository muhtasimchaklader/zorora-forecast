"""
Run before making the repository public:

    python privacy_check.py

Scans every file in the project folder (except the private ones Git already
ignores) for things that must never be published:
  - an Anthropic API key
  - name, email or phone columns in any data file
  - staff names (operators appear only as roles in the public data)
and checks that the private files are listed in .gitignore.
"""

import hashlib
import re
import sys

from src.load import PROJECT_ROOT

KEY = re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")
PERSONAL_HEADERS = {"first_name", "last_name", "name", "email", "phone", "company"}
# Staff first names are stored only as SHA-256 codes, so this public file never shows them.
# Every word in every file is turned into the same kind of code and compared.
STAFF_NAME_CODES = {
    "31265150e9fe8affe98292a10cf57260e619549e4385c65c88806e56051574bd",
    "1dd74f64c96722627b37e8160f882070aae61f5a6a0bc779ec1f5126687f2468",
}
WORD = re.compile(r"[a-z]+")
SKIP_DIRS = {".git", "__pycache__", ".vscode", "live"}
SKIP_FILES = {".env", "zorora_contacts_v3.csv"}  # ignored by Git
TEXT_TYPES = {".py", ".csv", ".json", ".md", ".txt", ".sql", ".gitignore", ".example", ""}


def has_staff_name(text):
    words = set(WORD.findall(text.lower()))
    return any(hashlib.sha256(w.encode()).hexdigest() in STAFF_NAME_CODES for w in words)


def main():
    problems, scanned = [], 0
    ignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    for needed in [".env", "data/live/", "data/reconstructed/zorora_contacts_v3.csv"]:
        if needed not in ignore:
            problems.append(f".gitignore does not list {needed}")
    for copy in PROJECT_ROOT.rglob("privacy_check.py"):
        if copy.parent != PROJECT_ROOT:
            problems.append(f"{copy.parent.relative_to(PROJECT_ROOT)}: a second copy of the "
                            "project is inside this folder. Delete it.")

    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file() or path.name in SKIP_FILES:
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(PROJECT_ROOT).parts):
            continue
        if path.suffix.lower() not in TEXT_TYPES and path.name != ".gitignore":
            continue  # binary files such as .docx, .pdf, .pbix
        scanned += 1
        rel = path.relative_to(PROJECT_ROOT)
        text = path.read_text(encoding="utf-8", errors="ignore")
        if KEY.search(text):
            problems.append(f"{rel}: contains an API key")
        if has_staff_name(text):
            problems.append(f"{rel}: contains a staff name")
        if path.suffix.lower() == ".csv":
            header = {h.strip().lower() for h in text.splitlines()[0].split(",")} if text else set()
            found = header & PERSONAL_HEADERS
            if found:
                problems.append(f"{rel}: has personal columns {sorted(found)}")

    print(f"Scanned {scanned} files.")
    if problems:
        print("NOT SAFE TO PUBLISH:")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)
    print("SAFE TO PUBLISH: no keys, no personal columns, no staff names, "
          "private files are ignored.")
    if (PROJECT_ROOT / "data" / "reconstructed" / "zorora_contacts_v3.csv").exists():
        print("Note: the old zorora_contacts_v3.csv is still in the folder. It is ignored by "
              "Git, but you can delete it.")


if __name__ == "__main__":
    main()
