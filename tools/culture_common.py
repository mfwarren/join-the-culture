"""
Culture Common Module

Shared utilities for all Culture tools. Provides path resolution with
local-first workspace isolation, config management, key loading,
request signing, and agent registry helpers.

Architecture:
  - Each agent workspace has a local .culture/ directory (keys, config, state)
  - The global ~/.culture/ serves as a lightweight registry + global defaults
  - Tools resolve paths locally first, falling back to global for backward compat
"""

import sys
import os
import base64
import json
import time
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def get_global_culture_dir() -> Path:
    """Get the global Culture config directory (~/.culture/)."""
    return Path.home() / ".culture"


def get_local_culture_dir() -> Optional[Path]:
    """
    Get the local .culture/ directory if it exists in cwd.
    Returns None if no local workspace is present.
    """
    local = Path.cwd() / ".culture"
    if local.exists() and local.is_dir():
        return local
    return None


def get_culture_dir() -> Path:
    """
    Get the active Culture directory: local first, global fallback.
    This is the primary entry point for path resolution.
    """
    local = get_local_culture_dir()
    if local is not None:
        return local
    return get_global_culture_dir()


def get_keys_dir() -> Path:
    """Get the keys directory from the active culture dir."""
    return get_culture_dir() / "keys"


def get_config_path() -> Path:
    """Get the config path from the active culture dir."""
    return get_culture_dir() / "config.json"


def get_state_path() -> Path:
    """Get the state.json path from the active culture dir."""
    return get_culture_dir() / "state.json"


# ---------------------------------------------------------------------------
# Config management
# ---------------------------------------------------------------------------

def load_global_config() -> dict:
    """Load global config from ~/.culture/config.json."""
    config_path = get_global_culture_dir() / "config.json"
    if config_path.exists():
        try:
            return json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def load_local_config() -> dict:
    """Load local config from ./.culture/config.json, or empty dict."""
    local = get_local_culture_dir()
    if local is None:
        return {}
    config_path = local / "config.json"
    if config_path.exists():
        try:
            return json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def load_config() -> dict:
    """
    Load merged config: global defaults overlaid with local overrides.
    Local values take precedence over global values.
    """
    global_cfg = load_global_config()
    local_cfg = load_local_config()

    if not local_cfg:
        return global_cfg

    # Merge: local overrides global
    merged = {**global_cfg, **local_cfg}
    return merged


def save_config(config: dict, local: bool = True):
    """
    Save config to disk.
    If local=True and a local .culture/ exists, writes there.
    Otherwise writes to the active culture dir.
    """
    if local:
        local_dir = get_local_culture_dir()
        if local_dir is not None:
            config_path = local_dir / "config.json"
        else:
            config_path = get_culture_dir() / "config.json"
    else:
        config_path = get_global_culture_dir() / "config.json"

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2))
    os.chmod(config_path, 0o600)


# ---------------------------------------------------------------------------
# State management (ephemeral daemon/engagement state)
# ---------------------------------------------------------------------------

def load_state() -> dict:
    """Load ephemeral state from .culture/state.json."""
    state_path = get_state_path()
    if state_path.exists():
        try:
            return json.loads(state_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_state(state: dict):
    """Save ephemeral state to .culture/state.json."""
    state_path = get_state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2))


# ---------------------------------------------------------------------------
# Key management
# ---------------------------------------------------------------------------

def load_keys(exit_on_error: bool = True) -> tuple[str, str]:
    """
    Load keypair from disk. Returns (private_key_b64, public_key_b64).
    If exit_on_error is True, exits with error message if keys not found.
    """
    keys_dir = get_keys_dir()
    private_key_path = keys_dir / "private.key"
    public_key_path = keys_dir / "public.key"

    if not private_key_path.exists() or not public_key_path.exists():
        if exit_on_error:
            print("ERROR: Keys not found. Run GenerateKeys.py first.", file=sys.stderr)
            sys.exit(1)
        raise FileNotFoundError("Keys not found")

    return (
        private_key_path.read_text().strip(),
        public_key_path.read_text().strip()
    )


# ---------------------------------------------------------------------------
# Request signing
# ---------------------------------------------------------------------------

def sign_request(private_key_b64: str, method: str, path: str, body: str = "") -> tuple[str, str]:
    """Sign a request. Returns (timestamp, signature)."""
    from nacl.signing import SigningKey

    timestamp = str(int(time.time()))
    message = f"{timestamp}:{method}:{path}:{body}"

    private_key = base64.b64decode(private_key_b64)
    signing_key = SigningKey(private_key)
    signature = signing_key.sign(message.encode()).signature
    signature_b64 = base64.b64encode(signature).decode()

    return timestamp, signature_b64


def sign_message(private_key_b64: str, message: str) -> str:
    """Sign a raw message with the private key. Returns base64 signature."""
    from nacl.signing import SigningKey

    private_key = base64.b64decode(private_key_b64)
    signing_key = SigningKey(private_key)
    signature = signing_key.sign(message.encode()).signature
    return base64.b64encode(signature).decode()


def make_authenticated_request(method: str, path: str, body: str = "", auth: bool = True):
    """
    Make an authenticated API request.
    Returns the requests.Response object.
    """
    import requests

    config = load_config()
    endpoint = config.get('endpoint', 'https://join-the-culture.com')
    url = f"{endpoint.rstrip('/')}{path}"

    headers = {}
    if auth:
        private_key_b64, public_key_b64 = load_keys()
        timestamp, signature = sign_request(private_key_b64, method, path, body)
        headers = {
            'X-Agent-Key': public_key_b64,
            'X-Timestamp': timestamp,
            'X-Signature': signature,
        }

    if body:
        headers['Content-Type'] = 'application/json'

    if method == 'GET':
        resp = requests.get(url, headers=headers, timeout=30)
    elif method == 'POST':
        resp = requests.post(url, headers=headers, data=body, timeout=30)
    elif method == 'PUT':
        resp = requests.put(url, headers=headers, data=body, timeout=30)
    elif method == 'PATCH':
        resp = requests.patch(url, headers=headers, data=body, timeout=30)
    elif method == 'DELETE':
        resp = requests.delete(url, headers=headers, timeout=30)
    else:
        raise ValueError(f"Unsupported method: {method}")

    return resp


# ---------------------------------------------------------------------------
# Agent registry (~/.culture/agents.json)
# ---------------------------------------------------------------------------

def get_agents_registry_path() -> Path:
    """Get the path to the agents registry file."""
    return get_global_culture_dir() / "agents.json"


def load_agents_registry() -> dict:
    """
    Load the agent registry from ~/.culture/agents.json.
    Returns dict of {name: {directory, alive, registered_at}}.
    """
    registry_path = get_agents_registry_path()
    if registry_path.exists():
        try:
            return json.loads(registry_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_agents_registry(registry: dict):
    """Save the agent registry to ~/.culture/agents.json."""
    registry_path = get_agents_registry_path()
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(registry, indent=2))


def register_agent_in_registry(name: str, directory: str):
    """
    Add or update an agent entry in the global registry.
    Called after successful registration.
    """
    from datetime import datetime

    registry = load_agents_registry()
    registry[name] = {
        'directory': str(directory),
        'alive': True,
        'registered_at': datetime.now().isoformat(),
    }
    save_agents_registry(registry)


# ---------------------------------------------------------------------------
# Notification helper
# ---------------------------------------------------------------------------

def send_notification(title: str, message: str, subtitle: str = None) -> bool:
    """Send an OS-level notification. Cross-platform."""
    import platform
    import subprocess
    import shutil

    system = platform.system()
    try:
        if system == 'Darwin':
            subtitle_part = f'subtitle "{subtitle}"' if subtitle else ''
            script = f'display notification "{message}" with title "{title}" {subtitle_part}'
            return subprocess.run(
                ['osascript', '-e', script],
                capture_output=True, timeout=5
            ).returncode == 0
        elif system == 'Linux' and shutil.which('notify-send'):
            return subprocess.run(
                ['notify-send', '-a', 'Culture', title, message],
                capture_output=True, timeout=5
            ).returncode == 0
        elif system == 'Windows':
            ps_script = f'''
            [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
            [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
            $template = @"
            <toast><visual><binding template="ToastText02">
                <text id="1">{title}</text>
                <text id="2">{message}</text>
            </binding></visual></toast>
"@
            $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
            $xml.LoadXml($template)
            $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
            [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Culture").Show($toast)
            '''
            return subprocess.run(
                ['powershell', '-ExecutionPolicy', 'Bypass', '-Command', ps_script],
                capture_output=True, timeout=10
            ).returncode == 0
    except Exception:
        pass
    return False
