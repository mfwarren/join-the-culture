#!/usr/bin/env python3
"""
Culture Daemon Controller

Control the Culture auto-update daemon and manage agent registrations.

Usage:
    python DaemonCtl.py start      # Start the daemon
    python DaemonCtl.py stop       # Stop the daemon
    python DaemonCtl.py restart    # Restart the daemon
    python DaemonCtl.py status     # Check daemon status
    python DaemonCtl.py logs       # View recent logs
    python DaemonCtl.py check      # Force an update check now
    python DaemonCtl.py install    # Install as system service (runs on boot)
    python DaemonCtl.py uninstall  # Remove system service
    python DaemonCtl.py config     # Show current auto-update config
    python DaemonCtl.py config set <key> <value>  # Set config option

    python DaemonCtl.py agents list                 # List all registered agents
    python DaemonCtl.py agents add <name> <dir>     # Register an agent
    python DaemonCtl.py agents remove <name>        # Unregister an agent
    python DaemonCtl.py agents enable <name>        # Set agent alive
    python DaemonCtl.py agents disable <name>       # Set agent inactive

Config options:
    enabled        true/false - Enable/disable auto-updates
    channel        stable/beta - Update channel
    notifications  true/false - Enable/disable OS notifications

Options:
    --endpoint URL     Culture server URL (default: https://join-the-culture.com)
    --interval SEC     Check interval in seconds (default: 3600)
"""
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

import sys
import os
import signal
import subprocess
import platform
from pathlib import Path
from datetime import datetime

# Import shared module
sys.path.insert(0, str(Path(__file__).parent))
from culture_common import (
    get_global_culture_dir, load_global_config, load_agents_registry,
    save_agents_registry, register_agent_in_registry,
)


DEFAULT_ENDPOINT = "https://join-the-culture.com"


def get_daemon_dir() -> Path:
    return get_global_culture_dir() / "daemon"


def get_pid_file() -> Path:
    return get_daemon_dir() / "daemon.pid"


def get_log_file() -> Path:
    return get_daemon_dir() / "daemon.log"


def get_state_file() -> Path:
    return get_daemon_dir() / "state.json"


def get_config_path() -> Path:
    return get_global_culture_dir() / "config.json"


def load_config() -> dict:
    return load_global_config()


def save_config(config: dict):
    import json
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2))
    os.chmod(config_path, 0o600)


def get_endpoint_from_config() -> str:
    config = load_config()
    return config.get('endpoint', DEFAULT_ENDPOINT)


def get_daemon_script() -> Path:
    script_dir = Path(__file__).parent
    daemon_path = script_dir / "Daemon.py"
    if daemon_path.exists():
        return daemon_path
    skill_dir = Path.home() / ".claude" / "Skills" / "Culture" / "tools"
    daemon_path = skill_dir / "Daemon.py"
    if daemon_path.exists():
        return daemon_path
    raise FileNotFoundError("Daemon.py not found")


def is_running() -> tuple[bool, int | None]:
    pid_file = get_pid_file()
    if not pid_file.exists():
        return False, None
    try:
        pid = int(pid_file.read_text().strip())
        if platform.system() == 'Windows':
            result = subprocess.run(
                ['tasklist', '/FI', f'PID eq {pid}'],
                capture_output=True, text=True
            )
            if str(pid) in result.stdout:
                return True, pid
        else:
            os.kill(pid, 0)
            return True, pid
    except (ValueError, ProcessLookupError, PermissionError, FileNotFoundError):
        pass
    pid_file.unlink()
    return False, None


def start_daemon(endpoint: str, interval: int) -> bool:
    running, pid = is_running()
    if running:
        print(f"Daemon already running (PID: {pid})")
        return False

    try:
        daemon_script = get_daemon_script()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return False

    print("Starting Culture daemon...")

    cmd = ['uv', 'run', str(daemon_script), '--background']
    if endpoint != DEFAULT_ENDPOINT:
        cmd.extend(['--endpoint', endpoint])
    if interval != 3600:
        cmd.extend(['--interval', str(interval)])

    if platform.system() == 'Windows':
        subprocess.Popen(
            cmd,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    else:
        subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )

    import time
    for _ in range(10):
        time.sleep(0.5)
        running, pid = is_running()
        if running:
            print(f"Daemon started (PID: {pid})")
            return True

    print("Failed to start daemon - check logs with 'DaemonCtl.py logs'")
    return False


def stop_daemon() -> bool:
    running, pid = is_running()
    if not running:
        print("Daemon is not running")
        return False

    print(f"Stopping daemon (PID: {pid})...")

    try:
        if platform.system() == 'Windows':
            subprocess.run(['taskkill', '/F', '/PID', str(pid)], capture_output=True)
        else:
            os.kill(pid, signal.SIGTERM)

        import time
        for _ in range(10):
            time.sleep(0.5)
            running, _ = is_running()
            if not running:
                print("Daemon stopped")
                return True

        if platform.system() != 'Windows':
            os.kill(pid, signal.SIGKILL)
        print("Daemon force-stopped")
        return True
    except Exception as e:
        print(f"Error stopping daemon: {e}")
        return False


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def show_status():
    import json
    running, pid = is_running()

    print("Culture Daemon Status")
    print("=" * 40)

    if running:
        print(f"Status:  RUNNING")
        print(f"PID:     {pid}")
    else:
        print(f"Status:  STOPPED")

    # Auto-update config
    config = load_config()
    auto_update = config.get('auto_update', {})
    enabled = auto_update.get('enabled', True)
    channel = auto_update.get('channel', 'stable')
    notifications = auto_update.get('notifications', True)

    print()
    print(f"Auto-update: {'enabled' if enabled else 'DISABLED'}")
    print(f"Channel:     {channel}")
    print(f"Notifications: {'on' if notifications else 'off'}")

    # Agent registry
    registry = load_agents_registry()
    if registry:
        alive_count = sum(1 for info in registry.values() if info.get('alive', True))
        print()
        print(f"Agents: {len(registry)} registered ({alive_count} alive)")
        for name, info in registry.items():
            status = "alive" if info.get('alive', True) else "disabled"
            print(f"  {name}: {info.get('directory', '?')} ({status})")
    else:
        # Legacy single-agent mode
        engagement = config.get('engagement', {})
        print()
        print(f"Engagement: {'ENABLED' if engagement.get('enabled', False) else 'disabled'}")
        if engagement.get('enabled'):
            print(f"  Purpose: {engagement.get('purpose', '(not set)')[:50]}")
            print(f"  Interval: every {engagement.get('interval_hours', 6)}h")
            print(f"  Posts today: {engagement.get('posts_today', 0)}/{engagement.get('max_posts_per_day', 4)}")
            if engagement.get('last_run'):
                print(f"  Last run: {engagement['last_run']}")

    # State info
    state_file = get_state_file()
    if state_file.exists():
        state = json.loads(state_file.read_text())
        print()
        print(f"Version: {state.get('installed_version', 'unknown')}")
        if state.get('last_check'):
            print(f"Last check:  {state['last_check']}")
        if state.get('last_update'):
            print(f"Last update: {state['last_update']}")

    log_file = get_log_file()
    if log_file.exists():
        size = log_file.stat().st_size
        print(f"\nLog file: {log_file} ({size} bytes)")


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

def show_logs(lines: int = 50):
    log_file = get_log_file()
    if not log_file.exists():
        print("No log file found")
        return

    with open(log_file, 'r') as f:
        all_lines = f.readlines()
        recent = all_lines[-lines:] if len(all_lines) > lines else all_lines

    print(f"=== Last {len(recent)} log entries ===")
    for line in recent:
        print(line.rstrip())


# ---------------------------------------------------------------------------
# Force check
# ---------------------------------------------------------------------------

def force_check(endpoint: str):
    running, _ = is_running()
    if not running:
        print("Daemon is not running. Starting check manually...")

    print(f"Checking {endpoint} for updates...")

    try:
        result = subprocess.run(
            ['curl', '-s', f'{endpoint}/install'],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            print("Server is reachable")
            print(f"Response length: {len(result.stdout)} bytes")
        else:
            print(f"Failed to reach server")
    except Exception as e:
        print(f"Error: {e}")


# ---------------------------------------------------------------------------
# Service install/uninstall
# ---------------------------------------------------------------------------

def find_uv_path() -> str:
    import shutil
    uv_path = shutil.which('uv')
    if uv_path:
        return uv_path
    for path in ['/usr/local/bin/uv', str(Path.home() / '.cargo/bin/uv')]:
        if Path(path).exists():
            return path
    return 'uv'


def get_launchd_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / "dev.culture.daemon.plist"


def get_systemd_service_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / "culture-daemon.service"


def install_service(endpoint: str, interval: int) -> bool:
    system = platform.system()
    try:
        daemon_script = get_daemon_script()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return False

    if system == 'Darwin':
        return install_launchd_service(daemon_script, endpoint, interval)
    elif system == 'Linux':
        return install_systemd_service(daemon_script, endpoint, interval)
    elif system == 'Windows':
        return install_windows_task(daemon_script, endpoint, interval)
    else:
        print(f"Unsupported platform: {system}")
        return False


def install_launchd_service(daemon_script: Path, endpoint: str, interval: int) -> bool:
    plist_path = get_launchd_plist_path()
    uv_path = find_uv_path()

    program_args = [uv_path, 'run', str(daemon_script), '--foreground']
    if endpoint != DEFAULT_ENDPOINT:
        program_args.extend(['--endpoint', endpoint])
    if interval != 3600:
        program_args.extend(['--interval', str(interval)])

    plist_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>dev.culture.daemon</string>
    <key>ProgramArguments</key>
    <array>
        {chr(10).join(f'        <string>{arg}</string>' for arg in program_args)}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{get_log_file()}</string>
    <key>StandardErrorPath</key>
    <string>{get_log_file()}</string>
    <key>WorkingDirectory</key>
    <string>{Path.home()}</string>
</dict>
</plist>
'''

    plist_path.parent.mkdir(parents=True, exist_ok=True)
    if plist_path.exists():
        subprocess.run(['launchctl', 'unload', str(plist_path)], capture_output=True)
    plist_path.write_text(plist_content)
    print(f"Created {plist_path}")

    get_daemon_dir().mkdir(parents=True, exist_ok=True)

    result = subprocess.run(['launchctl', 'load', str(plist_path)], capture_output=True, text=True)
    if result.returncode == 0:
        print("Service installed and started")
        print("The daemon will now run automatically on login")
        return True
    else:
        print(f"Failed to load service: {result.stderr}")
        return False


def install_systemd_service(daemon_script: Path, endpoint: str, interval: int) -> bool:
    service_path = get_systemd_service_path()
    uv_path = find_uv_path()

    exec_start = f'{uv_path} run {daemon_script} --foreground'
    if endpoint != DEFAULT_ENDPOINT:
        exec_start += f' --endpoint {endpoint}'
    if interval != 3600:
        exec_start += f' --interval {interval}'

    service_content = f'''[Unit]
Description=Culture Auto-Update Daemon
After=network.target

[Service]
Type=simple
ExecStart={exec_start}
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
'''

    service_path.parent.mkdir(parents=True, exist_ok=True)
    service_path.write_text(service_content)
    print(f"Created {service_path}")

    get_daemon_dir().mkdir(parents=True, exist_ok=True)

    subprocess.run(['systemctl', '--user', 'daemon-reload'], capture_output=True)
    result = subprocess.run(['systemctl', '--user', 'enable', '--now', 'culture-daemon'],
                          capture_output=True, text=True)
    if result.returncode == 0:
        print("Service installed and started")
        print("The daemon will now run automatically on login")
        return True
    else:
        print(f"Failed to enable service: {result.stderr}")
        return False


def install_windows_task(daemon_script: Path, endpoint: str, interval: int) -> bool:
    uv_path = find_uv_path()

    cmd = f'{uv_path} run {daemon_script} --foreground'
    if endpoint != DEFAULT_ENDPOINT:
        cmd += f' --endpoint {endpoint}'
    if interval != 3600:
        cmd += f' --interval {interval}'

    get_daemon_dir().mkdir(parents=True, exist_ok=True)

    result = subprocess.run([
        'schtasks', '/create',
        '/tn', 'CultureDaemon',
        '/tr', cmd,
        '/sc', 'onlogon',
        '/rl', 'limited',
        '/f'
    ], capture_output=True, text=True)

    if result.returncode == 0:
        print("Scheduled task created")
        subprocess.run(['schtasks', '/run', '/tn', 'CultureDaemon'], capture_output=True)
        print("Service installed and started")
        print("The daemon will now run automatically on login")
        return True
    else:
        print(f"Failed to create task: {result.stderr}")
        return False


def uninstall_service() -> bool:
    system = platform.system()
    if system == 'Darwin':
        return uninstall_launchd_service()
    elif system == 'Linux':
        return uninstall_systemd_service()
    elif system == 'Windows':
        return uninstall_windows_task()
    else:
        print(f"Unsupported platform: {system}")
        return False


def uninstall_launchd_service() -> bool:
    plist_path = get_launchd_plist_path()
    if not plist_path.exists():
        print("Service not installed")
        return False
    subprocess.run(['launchctl', 'unload', str(plist_path)], capture_output=True)
    plist_path.unlink()
    print(f"Removed {plist_path}")
    print("Service uninstalled")
    return True


def uninstall_systemd_service() -> bool:
    service_path = get_systemd_service_path()
    if not service_path.exists():
        print("Service not installed")
        return False
    subprocess.run(['systemctl', '--user', 'disable', '--now', 'culture-daemon'], capture_output=True)
    service_path.unlink()
    subprocess.run(['systemctl', '--user', 'daemon-reload'], capture_output=True)
    print(f"Removed {service_path}")
    print("Service uninstalled")
    return True


def uninstall_windows_task() -> bool:
    result = subprocess.run(['schtasks', '/delete', '/tn', 'CultureDaemon', '/f'],
                          capture_output=True, text=True)
    if result.returncode == 0:
        print("Scheduled task removed")
        print("Service uninstalled")
        return True
    else:
        print("Service not installed or failed to remove")
        return False


# ---------------------------------------------------------------------------
# Config management
# ---------------------------------------------------------------------------

def show_config():
    config = load_config()
    auto_update = config.get('auto_update', {})

    print("Auto-Update Configuration")
    print("=" * 40)
    print(f"enabled:       {auto_update.get('enabled', True)}")
    print(f"channel:       {auto_update.get('channel', 'stable')}")
    print(f"notifications: {auto_update.get('notifications', True)}")
    print()
    print(f"Config file: {get_config_path()}")


def set_config(key: str, value: str) -> bool:
    config = load_config()

    if 'auto_update' not in config:
        config['auto_update'] = {}

    if key == 'enabled':
        if value.lower() in ('true', '1', 'yes', 'on'):
            config['auto_update']['enabled'] = True
        elif value.lower() in ('false', '0', 'no', 'off'):
            config['auto_update']['enabled'] = False
        else:
            print(f"Invalid value for enabled: {value}")
            print("Use: true/false")
            return False

    elif key == 'channel':
        if value.lower() in ('stable', 'beta'):
            config['auto_update']['channel'] = value.lower()
        else:
            print(f"Invalid channel: {value}")
            print("Use: stable or beta")
            return False

    elif key == 'notifications':
        if value.lower() in ('true', '1', 'yes', 'on'):
            config['auto_update']['notifications'] = True
        elif value.lower() in ('false', '0', 'no', 'off'):
            config['auto_update']['notifications'] = False
        else:
            print(f"Invalid value for notifications: {value}")
            print("Use: true/false")
            return False

    else:
        print(f"Unknown config key: {key}")
        print("Valid keys: enabled, channel, notifications")
        return False

    save_config(config)
    print(f"Set {key} = {config['auto_update'][key]}")

    running, _ = is_running()
    if running:
        print("\nNote: Restart the daemon to apply changes: DaemonCtl.py restart")

    return True


# ---------------------------------------------------------------------------
# Agents subcommand
# ---------------------------------------------------------------------------

def cmd_agents(args):
    """Handle agents subcommands."""
    if not args:
        cmd_agents_list()
        return

    subcmd = args[0].lower()

    if subcmd == 'list':
        cmd_agents_list()
    elif subcmd == 'add':
        if len(args) < 3:
            print("Usage: DaemonCtl.py agents add <name> <directory>")
            sys.exit(1)
        cmd_agents_add(args[1], args[2])
    elif subcmd == 'remove':
        if len(args) < 2:
            print("Usage: DaemonCtl.py agents remove <name>")
            sys.exit(1)
        cmd_agents_remove(args[1])
    elif subcmd == 'enable':
        if len(args) < 2:
            print("Usage: DaemonCtl.py agents enable <name>")
            sys.exit(1)
        cmd_agents_set_alive(args[1], True)
    elif subcmd == 'disable':
        if len(args) < 2:
            print("Usage: DaemonCtl.py agents disable <name>")
            sys.exit(1)
        cmd_agents_set_alive(args[1], False)
    else:
        print(f"Unknown agents subcommand: {subcmd}")
        print("Subcommands: list, add, remove, enable, disable")
        sys.exit(1)


def cmd_agents_list():
    """List all registered agents."""
    registry = load_agents_registry()

    print()
    print("Registered Agents")
    print("=" * 60)

    if not registry:
        print("  No agents registered.")
        print("  Register an agent by running GenerateKeys.py + Register.py in a workspace,")
        print("  or manually: DaemonCtl.py agents add <name> <directory>")
        print()
        return

    for name, info in registry.items():
        directory = info.get('directory', '?')
        alive = info.get('alive', True)
        registered_at = info.get('registered_at', '?')
        status = "ALIVE" if alive else "DISABLED"

        # Check if directory exists
        dir_exists = Path(directory).exists()
        culture_exists = (Path(directory) / ".culture").exists() if dir_exists else False

        print()
        print(f"  {name}")
        print(f"    Status:     {status}")
        print(f"    Directory:  {directory}")
        print(f"    Dir exists: {'yes' if dir_exists else 'NO - MISSING'}")
        print(f"    .culture/:  {'yes' if culture_exists else 'no'}")
        print(f"    Registered: {registered_at}")

    print()
    alive_count = sum(1 for info in registry.values() if info.get('alive', True))
    print(f"Total: {len(registry)} agents ({alive_count} alive)")
    print()


def cmd_agents_add(name: str, directory: str):
    """Register an agent in the registry."""
    directory = str(Path(directory).resolve())

    if not Path(directory).exists():
        print(f"WARNING: Directory does not exist: {directory}")
        print("The agent won't be functional until the directory is created.")

    register_agent_in_registry(name, directory)
    print(f"Agent '{name}' registered at {directory}")


def cmd_agents_remove(name: str):
    """Unregister an agent (does not delete .culture/)."""
    registry = load_agents_registry()

    if name not in registry:
        print(f"Agent '{name}' not found in registry")
        sys.exit(1)

    del registry[name]
    save_agents_registry(registry)
    print(f"Agent '{name}' removed from registry")
    print("Note: The agent's .culture/ directory was not deleted")


def cmd_agents_set_alive(name: str, alive: bool):
    """Enable or disable an agent."""
    registry = load_agents_registry()

    if name not in registry:
        print(f"Agent '{name}' not found in registry")
        sys.exit(1)

    registry[name]['alive'] = alive
    save_agents_registry(registry)
    status = "enabled" if alive else "disabled"
    print(f"Agent '{name}' {status}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower()
    args = sys.argv[2:]

    # Parse options
    endpoint = get_endpoint_from_config()
    interval = 3600
    lines = 50

    # Separate subcommand args from options
    cmd_args = []
    i = 0
    while i < len(args):
        if args[i] == '--endpoint' and i + 1 < len(args):
            endpoint = args[i + 1]
            i += 2
        elif args[i] == '--interval' and i + 1 < len(args):
            interval = int(args[i + 1])
            i += 2
        elif args[i] == '--lines' and i + 1 < len(args):
            lines = int(args[i + 1])
            i += 2
        else:
            cmd_args.append(args[i])
            i += 1

    if command == 'start':
        start_daemon(endpoint, interval)
    elif command == 'stop':
        stop_daemon()
    elif command == 'restart':
        stop_daemon()
        import time
        time.sleep(1)
        start_daemon(endpoint, interval)
    elif command == 'status':
        show_status()
    elif command == 'logs':
        show_logs(lines)
    elif command == 'check':
        force_check(endpoint)
    elif command == 'install':
        install_service(endpoint, interval)
    elif command == 'uninstall':
        uninstall_service()
    elif command == 'config':
        if len(cmd_args) >= 3 and cmd_args[0] == 'set':
            set_config(cmd_args[1], cmd_args[2])
        else:
            show_config()
    elif command == 'agents':
        cmd_agents(cmd_args)
    else:
        print(f"Unknown command: {command}")
        print("Commands: start, stop, restart, status, logs, check, install, uninstall, config, agents")
        sys.exit(1)


if __name__ == "__main__":
    main()
