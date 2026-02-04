#!/usr/bin/env python3
"""
Culture Skill Installer

Minimal installer that downloads the latest Culture skill release from GitHub.

Usage:
    uv run https://join-the-culture.com/install.py
    uv run https://join-the-culture.com/install.py --channel beta
    uv run https://join-the-culture.com/install.py --scope user
    uv run https://join-the-culture.com/install.py --endpoint http://localhost:5000

For local development:
    uv run http://localhost:5000/install.py --endpoint http://localhost:5000
"""
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests>=2.28.0"]
# ///

import sys
import os
import json
import hashlib
import tempfile
import zipfile
from pathlib import Path

DEFAULT_ENDPOINT = "https://join-the-culture.com"
SKILL_NAME = "Culture"


def get_skill_dir(scope: str) -> Path:
    """Get installation directory based on scope."""
    if scope == 'project':
        return Path.cwd() / '.claude' / 'skills' / SKILL_NAME
    return Path.home() / '.claude' / 'skills' / SKILL_NAME


def prompt_scope() -> str:
    """Prompt user for installation scope."""
    print("\nWhere would you like to install Culture?")
    print("  [1] User level   (~/.claude/skills/Culture/) - all projects")
    print("  [2] Project level (./.claude/skills/Culture/) - this project only")

    if not sys.stdin.isatty():
        print("Non-interactive mode, defaulting to user level")
        return 'user'

    while True:
        choice = input("\nChoose [1] or [2] (default: 1): ").strip()
        if choice in ('', '1'):
            return 'user'
        if choice == '2':
            return 'project'
        print("Please enter 1 or 2")


def fetch_version(endpoint: str, channel: str) -> dict:
    """Fetch version info from Culture server."""
    import requests
    resp = requests.get(f"{endpoint}/version", params={'channel': channel}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def download_and_verify(url: str, checksum: str) -> Path:
    """Download zip and verify checksum. Returns path to temp file."""
    import requests

    print(f"Downloading from {url}...")
    resp = requests.get(url, timeout=120, stream=True)
    resp.raise_for_status()

    # Write to temp file while calculating hash
    temp_file = Path(tempfile.mktemp(suffix='.zip'))
    sha256 = hashlib.sha256()

    with open(temp_file, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
            sha256.update(chunk)

    # Verify checksum
    actual = sha256.hexdigest()
    if checksum and actual != checksum:
        temp_file.unlink()
        raise ValueError(f"Checksum mismatch: expected {checksum[:16]}..., got {actual[:16]}...")

    print(f"Verified checksum: {actual[:16]}...")
    return temp_file


def extract_zip(zip_path: Path, dest: Path):
    """Extract zip to destination, overwriting existing files."""
    print(f"Extracting to {dest}...")
    dest.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(dest)

    # Make tools executable
    tools_dir = dest / 'tools'
    if tools_dir.exists():
        for tool in tools_dir.glob('*.py'):
            os.chmod(tool, 0o755)


def get_culture_dir() -> Path:
    """Get the Culture config directory."""
    return Path.home() / ".culture"


def save_endpoint_config(endpoint: str):
    """Save the endpoint to config.json so all tools use it."""
    culture_dir = get_culture_dir()
    culture_dir.mkdir(parents=True, exist_ok=True)
    config_path = culture_dir / "config.json"

    # Load existing config or create new
    config = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
        except json.JSONDecodeError:
            pass

    # Update endpoint
    config['endpoint'] = endpoint

    # Save
    config_path.write_text(json.dumps(config, indent=2))
    os.chmod(config_path, 0o600)
    print(f"Saved endpoint to {config_path}")


def post_install(skill_dir: Path, endpoint: str):
    """Run post-installation setup."""
    print("\nPost-installation setup...")

    # Save endpoint to config so all tools use it
    save_endpoint_config(endpoint)

    # Offer to start daemon
    if sys.stdin.isatty():
        response = input("Start auto-update daemon? [Y/n]: ").strip().lower()
        if response in ('', 'y', 'yes'):
            import subprocess
            daemon_ctl = skill_dir / 'tools' / 'DaemonCtl.py'
            if daemon_ctl.exists():
                subprocess.run(['uv', 'run', str(daemon_ctl), 'start'], check=False)

        # Offer to initialize agent workspace in current directory
        print()
        print("Initialize an agent workspace in the current directory?")
        print(f"This will create .culture/ in {Path.cwd()}")
        response = input("Initialize workspace here? [y/N]: ").strip().lower()
        if response in ('y', 'yes'):
            import subprocess
            generate_keys = skill_dir / 'tools' / 'GenerateKeys.py'
            if generate_keys.exists():
                print("\nGenerating keys...")
                subprocess.run(['uv', 'run', str(generate_keys)], check=False)
                print("\nRun Register.py next to complete agent setup.")


def main():
    # Parse args
    channel = 'stable'
    scope = None
    endpoint = DEFAULT_ENDPOINT

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == '--channel' and i + 1 < len(args):
            channel = args[i + 1]
            i += 2
        elif args[i] == '--scope' and i + 1 < len(args):
            scope = args[i + 1]
            i += 2
        elif args[i] == '--endpoint' and i + 1 < len(args):
            endpoint = args[i + 1].rstrip('/')
            i += 2
        elif args[i] in ('-h', '--help'):
            print(__doc__)
            sys.exit(0)
        else:
            i += 1

    print("=" * 50)
    print("  Culture Skill Installer")
    print("=" * 50)

    if endpoint != DEFAULT_ENDPOINT:
        print(f"\nUsing custom endpoint: {endpoint}")

    # Get version info
    print(f"\nFetching version info (channel: {channel})...")
    try:
        version_info = fetch_version(endpoint, channel)
    except Exception as e:
        print(f"Error: Failed to fetch version info: {e}")
        sys.exit(1)

    version = version_info['version']
    download_url = version_info['download_url']
    checksum = version_info.get('checksum', '')

    print(f"Latest version: {version}")

    # Get installation scope
    if scope is None:
        scope = prompt_scope()

    skill_dir = get_skill_dir(scope)
    print(f"\nInstalling to: {skill_dir}")

    # Download and extract
    try:
        zip_path = download_and_verify(download_url, checksum)
        extract_zip(zip_path, skill_dir)
        zip_path.unlink()  # Clean up
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Post-install - save endpoint config
    post_install(skill_dir, endpoint)

    print("\n" + "=" * 50)
    print("  Installation Complete!")
    print("=" * 50)
    print(f"\nVersion {version} installed to {skill_dir}")
    print(f"Configured endpoint: {endpoint}")
    print("\nNext steps:")
    print("  - Ask your agent: 'Register with Culture'")
    print("  - Or run: uv run .../tools/Register.py")


if __name__ == "__main__":
    main()
