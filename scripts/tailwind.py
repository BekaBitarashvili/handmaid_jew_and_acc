"""Tailwind CSS standalone CLI: download (pinned + checksum-verified), watch, build.

Usage:
    uv run python scripts/tailwind.py install   # one-time download into bin/
    uv run python scripts/tailwind.py watch     # dev: rebuild on template changes
    uv run python scripts/tailwind.py build     # prod/CI: minified build

No Node.js involved. Input: assets/css/main.css -> output: static/dist/css/main.css.
"""

import hashlib
import platform
import subprocess
import sys
import urllib.request
from pathlib import Path

TAILWIND_VERSION = "4.3.5"

# From the release's sha256sums.txt.
SHA256 = {
    "windows-x64.exe": "2803583268c53f4713e89943e211081fddb186c0a4a7d07b5c342c6ae853ec95",
    "linux-x64": "e47695cee3f0d90623a91f3939b08bdee610eb5ad99340adff9d4145b284d6cc",
    "linux-arm64": "ffcd0d21dbd7c605dc12743ff0c0b47debc963c86b399674084c1c8f2c96ecad",
    "macos-arm64": "f3f4f5d1727e2b693b8f1c9a1492b5dd87008c86ea286bee1589cb458e6235fc",
    "macos-x64": "a63702686a3ed048b3135d84a73be49ea9d47f880c9b20e54b3ef60934ad8cdf",
}

ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = ROOT / "bin"
INPUT = ROOT / "assets" / "css" / "main.css"
OUTPUT = ROOT / "static" / "dist" / "css" / "main.css"


def platform_key() -> str:
    system = platform.system()
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "x64"
    if system == "Windows":
        return "windows-x64.exe"
    if system == "Darwin":
        return f"macos-{arch}"
    if system == "Linux":
        return f"linux-{arch}"
    raise SystemExit(f"Unsupported platform: {system} {machine}")


def binary_path() -> Path:
    suffix = ".exe" if platform.system() == "Windows" else ""
    return BIN_DIR / f"tailwindcss-{TAILWIND_VERSION}{suffix}"


def install() -> Path:
    target = binary_path()
    if target.exists():
        return target
    key = platform_key()
    url = (
        "https://github.com/tailwindlabs/tailwindcss/releases/download/"
        f"v{TAILWIND_VERSION}/tailwindcss-{key}"
    )
    print(f"Downloading Tailwind CSS v{TAILWIND_VERSION} ({key})...", flush=True)
    with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310 (pinned https URL)
        data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != SHA256[key]:
        raise SystemExit(f"Checksum mismatch for {key}: got {digest}, expected {SHA256[key]}")
    BIN_DIR.mkdir(exist_ok=True)
    target.write_bytes(data)
    target.chmod(0o755)
    print(f"Installed {target.relative_to(ROOT)}")
    return target


def run(*extra: str) -> int:
    binary = install()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    command = [str(binary), "--input", str(INPUT), "--output", str(OUTPUT), *extra]
    try:
        return subprocess.run(command, cwd=ROOT, check=False).returncode
    except KeyboardInterrupt:
        return 0


def main() -> int:
    action = sys.argv[1] if len(sys.argv) == 2 else ""
    if action == "install":
        install()
        return 0
    if action == "watch":
        return run("--watch")
    if action == "build":
        return run("--minify")
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
