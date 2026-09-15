import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import config

LEASES_PATH = os.path.join(config.CONFIG_DIR, "leases.json")

_DURATION_RE = re.compile(r"^(\d+)([smhd])$")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_duration(text):
    """Parse '90m', '2h', '1d', '30s' into a number of seconds."""
    match = _DURATION_RE.match(text.strip().lower())
    if not match:
        raise ValueError(f"Invalid duration '{text}'. Use a number followed by s, m, h, or d (e.g. 90m, 2h, 1d).")
    value, unit = match.groups()
    return int(value) * _UNIT_SECONDS[unit]


def _load_leases():
    try:
        with open(LEASES_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_leases(leases):
    os.makedirs(config.CONFIG_DIR, exist_ok=True)
    with open(LEASES_PATH, "w") as f:
        json.dump(leases, f, indent=2)


def _pid_alive(pid):
    """POSIX-only liveness probe. On Windows, os.kill(pid, 0) calls TerminateProcess
    instead of just checking existence, so we can't safely probe there - assume alive."""
    if pid is None:
        return False
    if os.name == "nt":
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def schedule_destroy(token, droplet_id, droplet_name, ttl_seconds):
    """Spawn a detached watcher process that destroys the droplet once its TTL expires."""
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat()

    env = dict(os.environ)
    env["DOCONSOLE_TTL_TOKEN"] = token

    ttl_script = os.path.abspath(__file__)
    cmd = [sys.executable, ttl_script, "--watch", str(droplet_id), expires_at]

    popen_kwargs = {
        "env": env,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        popen_kwargs["start_new_session"] = True

    process = subprocess.Popen(cmd, **popen_kwargs)

    leases = _load_leases()
    leases[str(droplet_id)] = {
        "name": droplet_name,
        "expires_at": expires_at,
        "pid": process.pid,
    }
    _save_leases(leases)
    return expires_at


def list_leases():
    leases = _load_leases()
    now = datetime.now(timezone.utc)
    result = []
    for droplet_id, lease in leases.items():
        expires_at = datetime.fromisoformat(lease["expires_at"])
        seconds_remaining = (expires_at - now).total_seconds()
        result.append({
            "droplet_id": droplet_id,
            "name": lease["name"],
            "expires_at": lease["expires_at"],
            "seconds_remaining": seconds_remaining,
            "stale": seconds_remaining > 0 and not _pid_alive(lease.get("pid")),
        })
    return result


def cancel_lease(droplet_id_or_name):
    leases = _load_leases()
    match_id = None
    for droplet_id, lease in leases.items():
        if droplet_id == str(droplet_id_or_name) or lease["name"] == droplet_id_or_name:
            match_id = droplet_id
            break

    if match_id is None:
        return False

    pid = leases[match_id].get("pid")
    if _pid_alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass

    del leases[match_id]
    _save_leases(leases)
    return True


def _remove_lease(droplet_id):
    leases = _load_leases()
    leases.pop(str(droplet_id), None)
    _save_leases(leases)


def _watch(droplet_id, expires_at_iso):
    from do_api import DOAPIClient, DOAPIError

    expires_at = datetime.fromisoformat(expires_at_iso)
    while datetime.now(timezone.utc) < expires_at:
        time.sleep(min(30, max(1, (expires_at - datetime.now(timezone.utc)).total_seconds())))

    token = os.environ.get("DOCONSOLE_TTL_TOKEN")
    if not token:
        return

    client = DOAPIClient(token)
    try:
        client.destroy_droplet(droplet_id)
    except DOAPIError:
        pass
    _remove_lease(droplet_id)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--watch":
        _watch(sys.argv[2], sys.argv[3])
