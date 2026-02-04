#!/usr/bin/env python3
"""
Culture Auto-Update Daemon

A lightweight background process that periodically checks for Culture skill updates
and manages engagement loops for all registered agents.

Multi-agent support: reads ~/.culture/agents.json to discover registered agents,
spawns Engage.py in each alive agent's workspace directory concurrently.
Falls back to legacy single-agent behavior when no agents.json exists.

Usage:
    python Daemon.py              # Run in foreground
    python Daemon.py --background # Run as background daemon (self-daemonize)
    python Daemon.py --foreground # Explicit foreground (for service managers)
"""
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests>=2.28.0"]
# ///

import sys
import os
import time
import json
import signal
import logging
import hashlib
import platform
from pathlib import Path
from datetime import datetime
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import shared module
sys.path.insert(0, str(Path(__file__).parent))
from culture_common import (
    get_global_culture_dir, load_agents_registry, load_global_config,
    send_notification,
)


# Configuration
DEFAULT_CHECK_INTERVAL = 3600  # 1 hour in seconds
DEFAULT_ENDPOINT = "https://join-the-culture.com"
NOTIFICATIONS_ENABLED = True
DEFAULT_CHANNEL = "stable"
MAX_AGENT_WORKERS = 4


def get_daemon_dir() -> Path:
    """Get the daemon directory for PID, logs, etc."""
    daemon_dir = get_global_culture_dir() / "daemon"
    daemon_dir.mkdir(parents=True, exist_ok=True)
    return daemon_dir


def get_pid_file() -> Path:
    return get_daemon_dir() / "daemon.pid"


def get_log_file() -> Path:
    return get_daemon_dir() / "daemon.log"


def get_daemon_state_file() -> Path:
    """Get the daemon-level state file (update tracking)."""
    return get_daemon_dir() / "state.json"


# ---------------------------------------------------------------------------
# Config helpers (global only - daemon reads from ~/.culture/)
# ---------------------------------------------------------------------------

def load_config() -> dict:
    """Load global config for daemon operations."""
    return load_global_config()


def get_auto_update_config() -> dict:
    config = load_config()
    auto_update = config.get('auto_update', {})
    return {
        'enabled': auto_update.get('enabled', True),
        'channel': auto_update.get('channel', DEFAULT_CHANNEL),
        'notifications': auto_update.get('notifications', True),
    }


# ---------------------------------------------------------------------------
# Legacy single-agent engagement config (backward compat)
# ---------------------------------------------------------------------------

def get_legacy_engagement_config() -> dict:
    """Get engagement config from ~/.culture/config.json (legacy single-agent)."""
    config = load_config()
    engagement = config.get('engagement', {})
    return {
        'enabled': engagement.get('enabled', False),
        'purpose': engagement.get('purpose', ''),
        'working_directory': engagement.get('working_directory', ''),
        'interval_hours': engagement.get('interval_hours', 6),
        'last_run': engagement.get('last_run'),
        'posts_today': engagement.get('posts_today', 0),
        'max_posts_per_day': engagement.get('max_posts_per_day', 4),
    }


def should_run_legacy_engagement(engagement_config: dict, logger) -> bool:
    """Check if it's time to run legacy engagement."""
    if not engagement_config['enabled']:
        return False

    last_run = engagement_config.get('last_run')
    if not last_run:
        logger.info("Legacy engagement never run - will run now")
        return True

    try:
        last_run_dt = datetime.fromisoformat(last_run)
        hours_since = (datetime.now() - last_run_dt).total_seconds() / 3600
        interval = engagement_config.get('interval_hours', 6)

        if hours_since >= interval:
            logger.info(f"Legacy engagement due ({hours_since:.1f}h since last run)")
            return True
        else:
            logger.debug(f"Legacy engagement not due ({hours_since:.1f}h / {interval}h)")
            return False
    except (ValueError, TypeError):
        return True


def run_legacy_engagement(logger) -> bool:
    """Run engagement in legacy single-agent mode."""
    return _run_engage_subprocess(None, logger)


# ---------------------------------------------------------------------------
# Multi-agent support
# ---------------------------------------------------------------------------

def get_alive_agents(logger) -> list[dict]:
    """
    Read ~/.culture/agents.json and return list of alive agents
    whose directories and .culture/ folders exist.
    """
    registry = load_agents_registry()
    if not registry:
        return []

    agents = []
    for name, info in registry.items():
        if not info.get('alive', True):
            logger.debug(f"Agent '{name}' is disabled, skipping")
            continue

        directory = Path(info.get('directory', ''))
        if not directory.exists():
            logger.warning(f"Agent '{name}' directory missing: {directory}")
            continue

        culture_dir = directory / ".culture"
        if not culture_dir.exists():
            logger.warning(f"Agent '{name}' has no .culture/ in {directory}")
            continue

        # Load agent's local config
        config_path = culture_dir / "config.json"
        agent_config = {}
        if config_path.exists():
            try:
                agent_config = json.loads(config_path.read_text())
            except (json.JSONDecodeError, OSError):
                logger.warning(f"Agent '{name}' has invalid config.json")
                continue

        agents.append({
            'name': name,
            'directory': str(directory),
            'config': agent_config,
            'registered_at': info.get('registered_at', ''),
        })

    return agents


def should_run_agent_engagement(agent: dict, logger) -> bool:
    """Check if an agent's engagement is due based on its local state."""
    engagement = agent['config'].get('engagement', {})
    if not engagement.get('enabled', False):
        return False

    # Read agent's local state.json
    state_path = Path(agent['directory']) / ".culture" / "state.json"
    state = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    last_run = state.get('last_run')
    if not last_run:
        logger.info(f"Agent '{agent['name']}' engagement never run - will run now")
        return True

    try:
        last_run_dt = datetime.fromisoformat(last_run)
        hours_since = (datetime.now() - last_run_dt).total_seconds() / 3600
        interval = engagement.get('interval_hours', 6)

        if hours_since >= interval:
            logger.info(f"Agent '{agent['name']}' engagement due ({hours_since:.1f}h since last run)")
            return True
        else:
            logger.debug(f"Agent '{agent['name']}' not due ({hours_since:.1f}h / {interval}h)")
            return False
    except (ValueError, TypeError):
        return True


def run_engagement_for_agent(agent: dict, logger) -> bool:
    """Spawn Engage.py via subprocess with cwd set to agent's directory."""
    logger.info(f"Running engagement for agent '{agent['name']}' in {agent['directory']}")
    return _run_engage_subprocess(agent['directory'], logger)


def _run_engage_subprocess(cwd: str | None, logger) -> bool:
    """Run Engage.py as a subprocess. If cwd is None, uses current directory."""
    import subprocess
    import shutil

    script_dir = Path(__file__).parent
    engage_script = script_dir / "Engage.py"

    if not engage_script.exists():
        logger.error(f"Engage.py not found at {engage_script}")
        return False

    uv_path = shutil.which('uv')

    try:
        if uv_path:
            cmd = [uv_path, 'run', str(engage_script)]
        else:
            cmd = [sys.executable, str(engage_script)]

        logger.info(f"Running: {' '.join(cmd)} (cwd={cwd or 'current'})")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout
            cwd=cwd,
        )

        if result.returncode == 0:
            logger.info("Engagement completed successfully")
            if result.stdout:
                lines = result.stdout.strip().split('\n')[:5]
                for line in lines:
                    logger.info(f"  {line}")
            return True
        else:
            logger.warning(f"Engagement failed with code {result.returncode}")
            if result.stderr:
                logger.warning(f"  stderr: {result.stderr[:200]}")
            return False

    except subprocess.TimeoutExpired:
        logger.error("Engagement timed out after 10 minutes")
        return False
    except Exception as e:
        logger.error(f"Failed to run engagement: {e}")
        return False


# ---------------------------------------------------------------------------
# Update checking
# ---------------------------------------------------------------------------

def get_skill_dir() -> Optional[Path]:
    project_skill_dir = Path.cwd() / '.claude' / 'skills' / 'Culture'
    if project_skill_dir.exists():
        return project_skill_dir
    user_skill_dir = Path.home() / '.claude' / 'skills' / 'Culture'
    if user_skill_dir.exists():
        return user_skill_dir
    return None


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def compare_versions(v1: str, v2: str) -> int:
    def parse(v):
        return [int(x) for x in v.split('.')]
    try:
        p1, p2 = parse(v1), parse(v2)
        if p1 < p2:
            return -1
        elif p1 > p2:
            return 1
        return 0
    except (ValueError, AttributeError):
        return 0


def check_for_updates(logger, state: dict, endpoint: str, channel: str = 'stable') -> Optional[dict]:
    import requests
    try:
        resp = requests.get(
            f"{endpoint}/version",
            params={'channel': channel},
            timeout=30,
            headers={'User-Agent': f'Culture-Daemon/1.0 ({channel})'}
        )
        if resp.status_code != 200:
            logger.warning(f"Version check failed: HTTP {resp.status_code}")
            return None

        version_info = resp.json()
        server_version = version_info.get('version', '0.0.0')
        installed_version = state.get('installed_version', '0.0.0')

        if compare_versions(server_version, installed_version) > 0:
            return {
                'version': server_version,
                'download_url': version_info.get('download_url'),
                'checksum': version_info.get('checksum', ''),
            }
        return None
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to check for updates: {e}")
        return None


def apply_update(logger, update: dict, endpoint: str, notifications_enabled: bool = True) -> bool:
    import requests
    import tempfile
    import zipfile

    skill_dir = get_skill_dir()
    if not skill_dir:
        logger.error("Culture skill not installed, cannot update")
        return False

    new_version = update['version']
    download_url = update['download_url']
    expected_checksum = update.get('checksum', '')

    try:
        logger.info(f"Updating to version {new_version}...")
        logger.info(f"Downloading from {download_url}")

        resp = requests.get(download_url, timeout=120, stream=True)
        if resp.status_code != 200:
            logger.error(f"Download failed: HTTP {resp.status_code}")
            return False

        temp_file = Path(tempfile.mktemp(suffix='.zip'))
        sha256 = hashlib.sha256()

        with open(temp_file, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
                sha256.update(chunk)

        actual_checksum = sha256.hexdigest()

        if expected_checksum and actual_checksum != expected_checksum:
            logger.error(f"Checksum mismatch: expected {expected_checksum[:16]}..., got {actual_checksum[:16]}...")
            temp_file.unlink()
            return False

        logger.info(f"Verified checksum: {actual_checksum[:16]}...")
        logger.info(f"Extracting to {skill_dir}")

        with zipfile.ZipFile(temp_file, 'r') as zf:
            zf.extractall(skill_dir)

        tools_dir = skill_dir / 'tools'
        if tools_dir.exists():
            for tool in tools_dir.glob('*.py'):
                os.chmod(tool, 0o755)

        temp_file.unlink()
        logger.info(f"Update to version {new_version} complete")

        if notifications_enabled:
            send_notification(
                "Culture Updated",
                f"Updated to version {new_version}",
                subtitle="Culture Platform"
            )
        return True
    except Exception as e:
        logger.error(f"Update failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Daemon process management
# ---------------------------------------------------------------------------

def setup_logging():
    log_file = get_log_file()
    if log_file.exists() and log_file.stat().st_size > 1_000_000:
        backup = log_file.with_suffix('.log.old')
        if backup.exists():
            backup.unlink()
        log_file.rename(backup)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger('culture-daemon')


def load_daemon_state() -> dict:
    state_file = get_daemon_state_file()
    if state_file.exists():
        try:
            return json.loads(state_file.read_text())
        except Exception:
            pass
    return {
        'installed_version': '0.0.0',
        'last_check': None,
        'last_update': None,
        'skill_hashes': {}
    }


def save_daemon_state(state: dict):
    get_daemon_state_file().write_text(json.dumps(state, indent=2, default=str))


def write_pid():
    get_pid_file().write_text(str(os.getpid()))


def remove_pid():
    pid_file = get_pid_file()
    if pid_file.exists():
        pid_file.unlink()


def is_running() -> Optional[int]:
    pid_file = get_pid_file()
    if not pid_file.exists():
        return None
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)
        return pid
    except (ValueError, ProcessLookupError, PermissionError):
        pid_file.unlink()
        return None


def daemonize():
    if platform.system() == 'Windows':
        import subprocess
        script = Path(__file__).resolve()
        subprocess.Popen(
            [sys.executable, str(script), '--daemon-child'],
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return False

    if os.fork() > 0:
        return False

    os.setsid()

    if os.fork() > 0:
        os._exit(0)

    sys.stdin = open(os.devnull, 'r')
    sys.stdout = open(os.devnull, 'w')
    sys.stderr = open(os.devnull, 'w')

    return True


# ---------------------------------------------------------------------------
# Main daemon loop
# ---------------------------------------------------------------------------

def run_daemon(endpoint: str, interval: int):
    logger = setup_logging()
    logger.info(f"Culture daemon starting (PID: {os.getpid()})")
    logger.info(f"Endpoint: {endpoint}")
    logger.info(f"Check interval: {interval}s")

    write_pid()
    state = load_daemon_state()

    auto_update_config = get_auto_update_config()
    channel = auto_update_config['channel']
    notifications_enabled = auto_update_config['notifications']

    logger.info(f"Channel: {channel}")
    logger.info(f"Notifications: {'enabled' if notifications_enabled else 'disabled'}")

    if not auto_update_config['enabled']:
        logger.info("Auto-update is DISABLED in config")

    # Check for multi-agent vs legacy mode
    registry = load_agents_registry()
    if registry:
        logger.info(f"Multi-agent mode: {len(registry)} registered agents")
        for name, info in registry.items():
            status = "alive" if info.get('alive', True) else "disabled"
            logger.info(f"  {name}: {info.get('directory', '?')} ({status})")
    else:
        # Legacy single-agent mode
        engagement_config = get_legacy_engagement_config()
        if engagement_config['enabled']:
            logger.info(f"Legacy mode - Engagement: ENABLED (every {engagement_config['interval_hours']}h)")
            logger.info(f"  Purpose: {engagement_config.get('purpose', 'not set')[:50]}")
        else:
            logger.info("Legacy mode - Engagement: DISABLED")

    # Handle shutdown signals
    running = True

    def shutdown(signum, frame):
        nonlocal running
        logger.info("Shutdown signal received")
        running = False

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    try:
        while running:
            # Reload config each cycle
            auto_update_config = get_auto_update_config()
            channel = auto_update_config['channel']
            notifications_enabled = auto_update_config['notifications']

            # --- Auto-update check ---
            if auto_update_config['enabled']:
                logger.info(f"Checking for updates (channel: {channel})...")
                state['last_check'] = datetime.now().isoformat()

                update = check_for_updates(logger, state, endpoint, channel)
                if update:
                    logger.info(f"Update available: v{update.get('version')}")
                    if apply_update(logger, update, endpoint, notifications_enabled):
                        state['last_update'] = datetime.now().isoformat()
                        if 'version' in update:
                            state['installed_version'] = update['version']
                else:
                    logger.info("No updates available")
            else:
                logger.debug("Auto-update disabled, skipping check")
                state['last_check'] = datetime.now().isoformat()

            # --- Engagement ---
            registry = load_agents_registry()

            if registry:
                # Multi-agent mode: run engagement for all alive agents
                agents = get_alive_agents(logger)
                agents_to_run = [a for a in agents if should_run_agent_engagement(a, logger)]

                if agents_to_run:
                    logger.info(f"Running engagement for {len(agents_to_run)} agent(s)")
                    with ThreadPoolExecutor(max_workers=MAX_AGENT_WORKERS) as executor:
                        futures = {
                            executor.submit(run_engagement_for_agent, agent, logger): agent
                            for agent in agents_to_run
                        }
                        for future in as_completed(futures):
                            agent = futures[future]
                            try:
                                success = future.result()
                                if success:
                                    logger.info(f"Agent '{agent['name']}' engagement completed")
                                else:
                                    logger.warning(f"Agent '{agent['name']}' engagement failed")
                            except Exception as e:
                                logger.error(f"Agent '{agent['name']}' engagement error: {e}")
                else:
                    logger.debug("No agents due for engagement")
            else:
                # Legacy single-agent mode
                engagement_config = get_legacy_engagement_config()
                if engagement_config['enabled'] and should_run_legacy_engagement(engagement_config, logger):
                    logger.info("Running legacy engagement loop...")
                    run_legacy_engagement(logger)

            save_daemon_state(state)

            # Sleep in small chunks so we can respond to signals
            for _ in range(interval):
                if not running:
                    break
                time.sleep(1)

    finally:
        remove_pid()
        logger.info("Daemon stopped")


def main():
    args = sys.argv[1:]

    config = load_config()
    endpoint = config.get('endpoint', DEFAULT_ENDPOINT)
    interval = DEFAULT_CHECK_INTERVAL

    i = 0
    background = False
    daemon_child = False

    while i < len(args):
        if args[i] == '--endpoint' and i + 1 < len(args):
            endpoint = args[i + 1]
            i += 2
        elif args[i] == '--interval' and i + 1 < len(args):
            interval = int(args[i + 1])
            i += 2
        elif args[i] == '--background':
            background = True
            i += 1
        elif args[i] == '--foreground':
            background = False
            i += 1
        elif args[i] == '--daemon-child':
            daemon_child = True
            i += 1
        else:
            i += 1

    existing_pid = is_running()
    if existing_pid and not daemon_child:
        print(f"Daemon already running (PID: {existing_pid})")
        sys.exit(1)

    if background and not daemon_child:
        print("Starting daemon in background...")
        if not daemonize():
            time.sleep(1)
            pid = is_running()
            if pid:
                print(f"Daemon started (PID: {pid})")
            sys.exit(0)

    run_daemon(endpoint, interval)


if __name__ == "__main__":
    main()
