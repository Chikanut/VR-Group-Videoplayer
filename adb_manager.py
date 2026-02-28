"""Wrapper around CLI adb for Meta Quest device management."""

import subprocess
import re
import os
import threading


ADB_PORT = 5555
ADB_TIMEOUT = 5  # seconds


def _run(args: list[str], timeout: int = ADB_TIMEOUT) -> tuple[int, str, str]:
    """Run a subprocess and return (returncode, stdout, stderr)."""
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except FileNotFoundError:
        return -1, "", "adb not found"


def _target(ip: str) -> str:
    """Format ip:port target string."""
    return f"{ip}:{ADB_PORT}"


def connect(ip: str) -> bool:
    """Connect to device via adb. Returns True on success."""
    rc, out, _ = _run(["adb", "connect", _target(ip)])
    return rc == 0 and "connected" in out.lower()


def disconnect(ip: str) -> bool:
    """Disconnect from device. Returns True on success."""
    rc, _, _ = _run(["adb", "disconnect", _target(ip)])
    return rc == 0


def exec_command(ip: str, cmd: str) -> str:
    """Execute shell command on device. Returns stdout."""
    _, out, err = _run(["adb", "-s", _target(ip), "shell", cmd], timeout=10)
    return out if out else err


def exec_shell_args(ip: str, args: list[str], timeout: int = 15) -> str:
    """Execute adb shell command using argv mode to avoid quoting issues."""
    _, out, err = _run(["adb", "-s", _target(ip), "shell", *args], timeout=timeout)
    return out if out else err


def get_battery(ip: str) -> int:
    """Get battery level percentage. Returns -1 on failure."""
    out = exec_command(ip, "dumpsys battery | grep level")
    match = re.search(r"level:\s*(\d+)", out)
    return int(match.group(1)) if match else -1


def get_device_name(ip: str) -> str:
    """Get device model name."""
    out = exec_command(ip, "getprop ro.product.model")
    return out if out else "Unknown"


def get_mac(ip: str) -> str:
    """Get WiFi MAC address of the device."""
    out = exec_command(ip, "cat /sys/class/net/wlan0/address")
    out = out.strip().lower()
    if re.match(r"([0-9a-f]{2}:){5}[0-9a-f]{2}", out):
        return out
    # Fallback: ip link
    out = exec_command(ip, "ip link show wlan0")
    match = re.search(r"link/ether\s+([0-9a-f:]{17})", out.lower())
    return match.group(1) if match else ""


def is_online(ip: str) -> bool:
    """Check if device is reachable via adb."""
    rc, out, _ = _run(["adb", "-s", _target(ip), "get-state"], timeout=3)
    return rc == 0 and "device" in out.lower()


# ---------------------------------------------------------------------------
# Transfer commands with progress support
# ---------------------------------------------------------------------------

def push(ip: str, local_path: str, remote_path: str,
         progress_callback=None, cancel_event: threading.Event = None) -> tuple[bool, str]:
    """Push file to device. progress_callback(percent: int). Returns (success, message)."""
    if not os.path.exists(local_path):
        return False, f"Local file not found: {local_path}"
    args = ["adb", "-s", _target(ip), "push", local_path, remote_path]
    return _run_with_progress(args, progress_callback, cancel_event)


def pull(ip: str, remote_path: str, local_path: str,
         progress_callback=None, cancel_event: threading.Event = None) -> tuple[bool, str]:
    """Pull file from device. progress_callback(percent: int). Returns (success, message)."""
    args = ["adb", "-s", _target(ip), "pull", remote_path, local_path]
    return _run_with_progress(args, progress_callback, cancel_event)


def install(ip: str, apk_path: str,
            progress_callback=None, cancel_event: threading.Event = None) -> tuple[bool, str]:
    """Install APK on device. Returns (success, message)."""
    if not os.path.exists(apk_path):
        return False, f"APK not found: {apk_path}"
    args = ["adb", "-s", _target(ip), "install", "-r", apk_path]
    return _run_with_progress(args, progress_callback, cancel_event)


def uninstall(ip: str, package: str) -> tuple[bool, str]:
    """Uninstall package from device. Returns (success, message)."""
    rc, out, err = _run(["adb", "-s", _target(ip), "uninstall", package], timeout=30)
    msg = out if out else err
    return rc == 0 and "success" in msg.lower(), msg


def forward(ip: str, local_port: str, remote_port: str) -> tuple[bool, str]:
    """Set up port forwarding. Returns (success, message)."""
    rc, out, err = _run(["adb", "-s", _target(ip), "forward", local_port, remote_port])
    return rc == 0, out if out else err


def reverse(ip: str, remote_port: str, local_port: str) -> tuple[bool, str]:
    """Set up reverse port forwarding. Returns (success, message)."""
    rc, out, err = _run(["adb", "-s", _target(ip), "reverse", remote_port, local_port])
    return rc == 0, out if out else err


def list_files(ip: str, remote_path: str) -> list[dict]:
    """List files/dirs at remote_path. Returns list of {name, type, size}."""
    out = exec_command(ip, f"ls -la {remote_path}")
    items = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("total"):
            continue
        parts = line.split(None, 7)
        if len(parts) < 7:
            continue
        perms = parts[0]
        name = parts[-1] if len(parts) >= 8 else parts[-1]
        if name in (".", ".."):
            continue
        entry_type = "dir" if perms.startswith("d") else "file"
        try:
            size = int(parts[4])
        except (ValueError, IndexError):
            size = 0
        items.append({"name": name, "type": entry_type, "size": size})
    return items


def mkdir(ip: str, remote_path: str) -> tuple[bool, str]:
    """Create directory on device. Returns (success, message)."""
    out = exec_command(ip, f"mkdir -p {remote_path}")
    return "No such" not in out and "error" not in out.lower(), out


def list_packages(ip: str) -> list[str]:
    """List installed packages on device."""
    out = exec_command(ip, "pm list packages")
    packages = []
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("package:"):
            packages.append(line[8:])
    packages.sort()
    return packages


def _escape_shell_single_quotes(value: str) -> str:
    """Escape a string for safe usage inside single quotes in shell command."""
    return value.replace("'", "'\"'\"'")


def _resolve_media_content_uri(ip: str, normalized_path: str) -> str:
    """Resolve MediaStore content URI for a file path if indexed, else empty string."""
    escaped_path = _escape_shell_single_quotes(normalized_path)
    query_cmd = (
        "content query --uri content://media/external/video/media "
        "--projection _id:_data "
        f"--where \"_data='{escaped_path}'\""
    )
    out = exec_command(ip, query_cmd)
    match = re.search(r"_id=(\d+)", out)
    if not match:
        return ""
    return f"content://media/external/video/media/{match.group(1)}"


def _looks_like_intent_error(output: str) -> bool:
    lowered = output.lower()
    return any(marker in lowered for marker in [
        "error",
        "exception",
        "unable to",
        "securityexception",
        "activity not started",
    ])


def launch_video(ip: str, video_path: str) -> tuple[bool, str]:
    """Launch video player with the given file. Returns (success, message)."""
    normalized_path = video_path.strip()
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path.lstrip('/')}"

    # Ensure MediaStore can index newly copied files so they are visible on-device.
    scan_out = exec_shell_args(ip, [
        "am", "broadcast",
        "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
        "-d", f"file://{normalized_path}",
    ])

    file_uri = f"file://{normalized_path}"
    content_uri = _resolve_media_content_uri(ip, normalized_path)

    attempts: list[tuple[str, list[str]]] = []
    if content_uri:
        attempts.append(("content+horizon", [
            "am", "start",
            "-a", "android.intent.action.VIEW",
            "-d", content_uri,
            "-t", "video/*",
            "--grant-read-uri-permission",
            "-p", "com.oculus.horizonmediaplayer",
        ]))
    attempts.append(("file+horizon", [
        "am", "start",
        "-a", "android.intent.action.VIEW",
        "-d", file_uri,
        "-t", "video/*",
        "--grant-read-uri-permission",
        "-p", "com.oculus.horizonmediaplayer",
    ]))
    if content_uri:
        attempts.append(("content+implicit", [
            "am", "start",
            "-a", "android.intent.action.VIEW",
            "-d", content_uri,
            "-t", "video/*",
            "--grant-read-uri-permission",
        ]))
    attempts.append(("file+implicit", [
        "am", "start",
        "-a", "android.intent.action.VIEW",
        "-d", file_uri,
        "-t", "video/*",
        "--grant-read-uri-permission",
    ]))

    logs = [f"scan: {scan_out}"]
    for name, cmd in attempts:
        out = exec_shell_args(ip, cmd)
        logs.append(f"{name}: {out}")
        if not _looks_like_intent_error(out):
            return True, "\n".join(logs)

    # Final fallback: launch the player app even if direct file open failed.
    fallback = exec_command(
        ip,
        "monkey -p com.oculus.horizonmediaplayer -c android.intent.category.LAUNCHER 1",
    )
    logs.append(f"fallback: {fallback}")
    return False, "\n".join(logs)


def _run_with_progress(args: list[str], progress_callback=None,
                       cancel_event: threading.Event = None) -> tuple[bool, str]:
    """Run adb command that outputs progress (push/pull/install).
    Parses percentage from adb output lines. Returns (success, message)."""
    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError:
        return False, "adb not found"

    output_chunks = []
    pct_buf = ""
    last_pct = -1
    while True:
        if cancel_event and cancel_event.is_set():
            proc.kill()
            return False, "Cancelled"

        ch = proc.stdout.read(1)
        if not ch and proc.poll() is not None:
            break
        if not ch:
            continue

        output_chunks.append(ch)
        pct_buf += ch
        if len(pct_buf) > 256:
            pct_buf = pct_buf[-256:]

        if progress_callback:
            matches = re.findall(r"(\d{1,3})%", pct_buf)
            if matches:
                pct = max(0, min(100, int(matches[-1])))
                if pct != last_pct:
                    progress_callback(pct)
                    last_pct = pct

    rc = proc.wait()
    result_text = "".join(output_chunks).strip()
    if progress_callback and rc == 0 and last_pct < 100:
        progress_callback(100)
    return rc == 0, result_text
