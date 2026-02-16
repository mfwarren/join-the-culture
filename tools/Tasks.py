#!/usr/bin/env python3
"""
Culture Task Scheduler

Manage recurring and one-off tasks for Culture agents. Each task has a custom
prompt that gets sent to Claude when the task is due.

Usage:
    python Tasks.py add --name "daily-review" --schedule "interval:24h" --prompt "Review code changes..."
    python Tasks.py add --name "weekly-report" --schedule "cron:0 9 * * 1" --prompt "Generate weekly report..."
    python Tasks.py add --name "check-tonight" --schedule "once:2026-02-16T00:00:00" --prompt "Check deployment..."
    python Tasks.py list                    # Show all tasks with status
    python Tasks.py remove <id-or-name>     # Remove a task
    python Tasks.py enable <id-or-name>     # Enable a task
    python Tasks.py disable <id-or-name>    # Disable a task
    python Tasks.py run <id-or-name>        # Run a task immediately (for testing)

Schedule formats:
    interval:6h          Every 6 hours
    interval:30m         Every 30 minutes
    cron:0 9 * * 1       Standard 5-field cron (e.g. Monday 9am)
    once:2026-02-16T00:00:00  One-time execution at ISO datetime
"""
# /// script
# requires-python = ">=3.10"
# dependencies = ["croniter>=2.0.0"]
# ///

import sys
import os
import json
import subprocess
import shutil
import secrets
from pathlib import Path
from datetime import datetime
from typing import Optional

# Import shared module
sys.path.insert(0, str(Path(__file__).parent))
from culture_common import load_tasks, save_tasks, load_config


def generate_task_id() -> str:
    """Generate a short random hex ID for a task."""
    return secrets.token_hex(3)


def parse_schedule(schedule_str: str) -> dict:
    """
    Parse a schedule string into a schedule dict.

    Formats:
        "interval:6h"  -> {"type": "interval", "hours": 6}
        "interval:30m" -> {"type": "interval", "minutes": 30}
        "cron:0 9 * * 1" -> {"type": "cron", "expr": "0 9 * * 1"}
        "once:2026-02-16T00:00:00" -> {"type": "once", "run_at": "2026-02-16T00:00:00"}
    """
    if ":" not in schedule_str:
        raise ValueError(
            f"Invalid schedule format: {schedule_str}\n"
            "Expected: interval:<duration>, cron:<expr>, or once:<datetime>"
        )

    stype, _, value = schedule_str.partition(":")

    if stype == "interval":
        value = value.strip()
        if value.endswith("h"):
            hours = float(value[:-1])
            if hours <= 0:
                raise ValueError("Interval hours must be positive")
            return {"type": "interval", "hours": hours}
        elif value.endswith("m"):
            minutes = float(value[:-1])
            if minutes <= 0:
                raise ValueError("Interval minutes must be positive")
            return {"type": "interval", "minutes": minutes}
        else:
            # Assume hours if no suffix
            hours = float(value)
            if hours <= 0:
                raise ValueError("Interval must be positive")
            return {"type": "interval", "hours": hours}

    elif stype == "cron":
        expr = value.strip()
        # Validate the cron expression
        try:
            from croniter import croniter

            croniter(expr)
        except (ValueError, KeyError) as e:
            raise ValueError(f"Invalid cron expression '{expr}': {e}")
        return {"type": "cron", "expr": expr}

    elif stype == "once":
        run_at = value.strip()
        # Validate ISO datetime
        try:
            datetime.fromisoformat(run_at)
        except ValueError:
            raise ValueError(f"Invalid datetime '{run_at}'. Use ISO format: 2026-02-16T00:00:00")
        return {"type": "once", "run_at": run_at}

    else:
        raise ValueError(
            f"Unknown schedule type: {stype}\n"
            "Expected: interval, cron, or once"
        )


def is_task_due(task: dict) -> bool:
    """Check if a task should run now based on its schedule and last_run."""
    if not task.get("enabled", True):
        return False

    schedule = task.get("schedule", {})
    stype = schedule.get("type")
    last_run = task.get("last_run")

    if stype == "interval":
        if not last_run:
            return True
        try:
            last_dt = datetime.fromisoformat(last_run)
            elapsed_seconds = (datetime.now() - last_dt).total_seconds()
            interval_seconds = schedule.get("hours", 0) * 3600 + schedule.get("minutes", 0) * 60
            return elapsed_seconds >= interval_seconds
        except (ValueError, TypeError):
            return True

    elif stype == "cron":
        from croniter import croniter

        expr = schedule.get("expr", "")
        if not last_run:
            # Never run - check if we're past the most recent trigger
            return True
        try:
            last_dt = datetime.fromisoformat(last_run)
            cron = croniter(expr, last_dt)
            next_run = cron.get_next(datetime)
            return datetime.now() >= next_run
        except (ValueError, TypeError, KeyError):
            return True

    elif stype == "once":
        if last_run:
            # Already ran
            return False
        run_at = schedule.get("run_at", "")
        try:
            run_dt = datetime.fromisoformat(run_at)
            return datetime.now() >= run_dt
        except (ValueError, TypeError):
            return False

    return False


def mark_task_run(task: dict) -> dict:
    """Update a task after it runs. Auto-disables 'once' tasks."""
    task["last_run"] = datetime.now().isoformat()
    if task.get("schedule", {}).get("type") == "once":
        task["enabled"] = False
    return task


def find_task(tasks: list[dict], identifier: str) -> Optional[dict]:
    """Find a task by ID or name."""
    for task in tasks:
        if task.get("id") == identifier or task.get("name") == identifier:
            return task
    return None


def find_claude_cli() -> Optional[str]:
    """Find the claude CLI executable."""
    candidates = [
        shutil.which("claude"),
        Path.home() / ".claude" / "local" / "claude",
        Path("/usr/local/bin/claude"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    return None


def run_task(task: dict, cwd: Optional[str] = None) -> bool:
    """Run a task immediately by spawning Claude with the task's prompt."""
    claude_path = find_claude_cli()
    if not claude_path:
        print("ERROR: Claude CLI not found. Install Claude Code first.")
        return False

    prompt = task.get("prompt", "")
    if not prompt:
        print(f"ERROR: Task '{task.get('name', '?')}' has no prompt.")
        return False

    working_dir = cwd or str(Path.cwd())

    print(f"Running task '{task.get('name', '?')}'...")
    print(f"Working directory: {working_dir}")
    print()

    try:
        result = subprocess.run(
            [claude_path, "--print", prompt],
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=600,
        )

        if result.returncode == 0:
            print("Task completed successfully.")
            if result.stdout:
                output = result.stdout[:1000]
                print(output)
                if len(result.stdout) > 1000:
                    print("... (truncated)")
        else:
            print(f"Task finished with code {result.returncode}")
            if result.stderr:
                print(f"stderr: {result.stderr[:500]}")

        return result.returncode == 0

    except subprocess.TimeoutExpired:
        print("ERROR: Task timed out after 10 minutes")
        return False
    except Exception as e:
        print(f"ERROR: Failed to run task: {e}")
        return False


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


def cmd_add(args: list[str]) -> None:
    """Add a new task."""
    name = None
    schedule_str = None
    prompt = None

    i = 0
    while i < len(args):
        if args[i] == "--name" and i + 1 < len(args):
            name = args[i + 1]
            i += 2
        elif args[i] == "--schedule" and i + 1 < len(args):
            schedule_str = args[i + 1]
            i += 2
        elif args[i] == "--prompt" and i + 1 < len(args):
            prompt = args[i + 1]
            i += 2
        else:
            i += 1

    if not name:
        print("ERROR: --name is required")
        sys.exit(1)
    if not schedule_str:
        print("ERROR: --schedule is required")
        sys.exit(1)
    if not prompt:
        print("ERROR: --prompt is required")
        sys.exit(1)

    try:
        schedule = parse_schedule(schedule_str)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    tasks = load_tasks()

    # Check for duplicate name
    if find_task(tasks, name):
        print(f"ERROR: Task '{name}' already exists. Remove it first or use a different name.")
        sys.exit(1)

    task = {
        "id": generate_task_id(),
        "name": name,
        "prompt": prompt,
        "schedule": schedule,
        "enabled": True,
        "last_run": None,
        "created_at": datetime.now().isoformat(),
    }

    tasks.append(task)
    save_tasks(tasks)

    print(f"Task '{name}' added (id: {task['id']})")
    _print_schedule(schedule)


def cmd_list() -> None:
    """List all tasks."""
    tasks = load_tasks()

    if not tasks:
        print("No tasks configured.")
        print()
        print("Add one with:")
        print('  python Tasks.py add --name "my-task" --schedule "interval:6h" --prompt "Do something..."')
        return

    print()
    print(f"{'Name':<25} {'Schedule':<25} {'Status':<10} {'Last Run':<20}")
    print("-" * 80)

    for task in tasks:
        name = task.get("name", "?")
        schedule = _format_schedule(task.get("schedule", {}))
        status = "enabled" if task.get("enabled", True) else "disabled"
        last_run = task.get("last_run") or "never"
        if last_run and last_run != "never":
            try:
                dt = datetime.fromisoformat(last_run)
                last_run = dt.strftime("%Y-%m-%d %H:%M")
            except ValueError:
                pass

        # Check if due
        if task.get("enabled", True) and is_task_due(task):
            status = "DUE"

        print(f"{name:<25} {schedule:<25} {status:<10} {last_run:<20}")

    print()
    print(f"{len(tasks)} task(s)")


def cmd_remove(identifier: str) -> None:
    """Remove a task by ID or name."""
    tasks = load_tasks()
    task = find_task(tasks, identifier)

    if not task:
        print(f"ERROR: Task '{identifier}' not found")
        sys.exit(1)

    tasks = [t for t in tasks if t.get("id") != task.get("id")]
    save_tasks(tasks)
    print(f"Task '{task.get('name', '?')}' removed.")


def cmd_enable(identifier: str) -> None:
    """Enable a task."""
    tasks = load_tasks()
    task = find_task(tasks, identifier)

    if not task:
        print(f"ERROR: Task '{identifier}' not found")
        sys.exit(1)

    task["enabled"] = True
    save_tasks(tasks)
    print(f"Task '{task.get('name', '?')}' enabled.")


def cmd_disable(identifier: str) -> None:
    """Disable a task."""
    tasks = load_tasks()
    task = find_task(tasks, identifier)

    if not task:
        print(f"ERROR: Task '{identifier}' not found")
        sys.exit(1)

    task["enabled"] = False
    save_tasks(tasks)
    print(f"Task '{task.get('name', '?')}' disabled.")


def cmd_run(identifier: str) -> None:
    """Run a task immediately."""
    tasks = load_tasks()
    task = find_task(tasks, identifier)

    if not task:
        print(f"ERROR: Task '{identifier}' not found")
        sys.exit(1)

    success = run_task(task)

    if success:
        mark_task_run(task)
        save_tasks(tasks)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _format_schedule(schedule: dict) -> str:
    """Format a schedule dict for display."""
    stype = schedule.get("type", "?")
    if stype == "interval":
        hours = schedule.get("hours", 0)
        minutes = schedule.get("minutes", 0)
        if hours:
            return f"every {hours}h"
        elif minutes:
            return f"every {minutes}m"
        return "interval (unknown)"
    elif stype == "cron":
        return f"cron: {schedule.get('expr', '?')}"
    elif stype == "once":
        run_at = schedule.get("run_at", "?")
        try:
            dt = datetime.fromisoformat(run_at)
            return f"once: {dt.strftime('%Y-%m-%d %H:%M')}"
        except ValueError:
            return f"once: {run_at}"
    return str(schedule)


def _print_schedule(schedule: dict) -> None:
    """Print schedule info after adding a task."""
    stype = schedule.get("type")
    if stype == "interval":
        hours = schedule.get("hours", 0)
        minutes = schedule.get("minutes", 0)
        if hours:
            print(f"  Schedule: every {hours} hour(s)")
        elif minutes:
            print(f"  Schedule: every {minutes} minute(s)")
    elif stype == "cron":
        print(f"  Schedule: cron {schedule.get('expr')}")
    elif stype == "once":
        print(f"  Schedule: once at {schedule.get('run_at')}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    args = sys.argv[1:]

    if not args or args[0] in ("--help", "-h"):
        print(__doc__)
        return

    command = args[0]
    rest = args[1:]

    if command == "add":
        cmd_add(rest)
    elif command == "list":
        cmd_list()
    elif command == "remove":
        if not rest:
            print("ERROR: Specify task ID or name")
            sys.exit(1)
        cmd_remove(rest[0])
    elif command == "enable":
        if not rest:
            print("ERROR: Specify task ID or name")
            sys.exit(1)
        cmd_enable(rest[0])
    elif command == "disable":
        if not rest:
            print("ERROR: Specify task ID or name")
            sys.exit(1)
        cmd_disable(rest[0])
    elif command == "run":
        if not rest:
            print("ERROR: Specify task ID or name")
            sys.exit(1)
        cmd_run(rest[0])
    else:
        print(f"Unknown command: {command}")
        print("Commands: add, list, remove, enable, disable, run")
        sys.exit(1)


if __name__ == "__main__":
    main()
