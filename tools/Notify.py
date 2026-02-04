#!/usr/bin/env python3
"""
Culture Notification Tool

Send OS-level notifications from Culture tools.

Usage:
    python Notify.py "Title" "Message"
    python Notify.py "Title" "Message" --subtitle "Subtitle"

This tool is used by other Culture tools to send notifications.
"""
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

import sys
import platform
import subprocess
import shutil


def send_notification(title: str, message: str, subtitle: str = None) -> bool:
    """
    Send an OS-level notification.

    Works on macOS, Linux, and Windows.
    Returns True if notification was sent successfully.
    """
    system = platform.system()

    try:
        if system == 'Darwin':
            return _notify_macos(title, message, subtitle)
        elif system == 'Linux':
            return _notify_linux(title, message)
        elif system == 'Windows':
            return _notify_windows(title, message)
        else:
            print(f"Unsupported platform: {system}", file=sys.stderr)
            return False
    except Exception as e:
        print(f"Notification failed: {e}", file=sys.stderr)
        return False


def _notify_macos(title: str, message: str, subtitle: str = None) -> bool:
    """Send notification on macOS using osascript."""
    # Escape quotes in strings
    title = title.replace('"', '\\"')
    message = message.replace('"', '\\"')

    # Build AppleScript
    subtitle_part = f'subtitle "{subtitle.replace(chr(34), chr(92)+chr(34))}"' if subtitle else ''
    script = f'''
    display notification "{message}" with title "{title}" {subtitle_part}
    '''

    result = subprocess.run(
        ['osascript', '-e', script],
        capture_output=True,
        timeout=5
    )
    return result.returncode == 0


def _notify_linux(title: str, message: str) -> bool:
    """Send notification on Linux using notify-send."""
    # Check if notify-send is available
    if not shutil.which('notify-send'):
        print("notify-send not found. Install libnotify.", file=sys.stderr)
        return False

    result = subprocess.run(
        ['notify-send', '-a', 'Culture', title, message],
        capture_output=True,
        timeout=5
    )
    return result.returncode == 0


def _notify_windows(title: str, message: str) -> bool:
    """Send notification on Windows using PowerShell."""
    # Escape quotes for PowerShell
    title = title.replace('"', '`"')
    message = message.replace('"', '`"')

    # Use PowerShell to show a toast notification
    ps_script = f'''
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

    $template = @"
    <toast>
        <visual>
            <binding template="ToastText02">
                <text id="1">{title}</text>
                <text id="2">{message}</text>
            </binding>
        </visual>
    </toast>
"@

    $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
    $xml.LoadXml($template)
    $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Culture").Show($toast)
    '''

    result = subprocess.run(
        ['powershell', '-ExecutionPolicy', 'Bypass', '-Command', ps_script],
        capture_output=True,
        timeout=10
    )
    return result.returncode == 0


def main():
    if len(sys.argv) < 3:
        print("Usage: python Notify.py <title> <message> [--subtitle <subtitle>]")
        sys.exit(1)

    title = sys.argv[1]
    message = sys.argv[2]
    subtitle = None

    # Parse optional subtitle
    if '--subtitle' in sys.argv:
        idx = sys.argv.index('--subtitle')
        if idx + 1 < len(sys.argv):
            subtitle = sys.argv[idx + 1]

    if send_notification(title, message, subtitle):
        print("Notification sent")
    else:
        print("Failed to send notification", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
