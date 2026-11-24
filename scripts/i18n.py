"""Run gettext commands inside Docker, so Windows hosts don't need GNU gettext.

Usage:
    uv run python scripts/i18n.py make      # extract strings into locale/ka/LC_MESSAGES/*.po
    uv run python scripts/i18n.py compile   # build the .mo files Django loads

Uses the `tools` service from compose.yml (built on first use, cached afterwards).
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ["docker", "compose", "--profile", "tools", "run", "--rm", "--build", "tools"]

# Directories makemessages must never scan.
IGNORE = [".venv/*", "staticfiles/*", "static/vendor/*", "static/dist/*", "bin/*", "media/*"]

COMMANDS = {
    "make": [
        "makemessages",
        "--locale=ka",
        "--add-location=file",
        "--no-obsolete",
        *(f"--ignore={pattern}" for pattern in IGNORE),
    ],
    "compile": ["compilemessages", "--locale=ka", "--ignore=.venv"],
}


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        return 2
    command = [*COMPOSE, *COMMANDS[sys.argv[1]]]
    print("$", " ".join(command), flush=True)
    return subprocess.run(command, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
