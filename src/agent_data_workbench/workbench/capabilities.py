"""Report the actual server runtime and native CLI availability without credentials."""

import json
import shutil
import subprocess
from pathlib import Path


def _probe(name: str) -> dict:
    executable = shutil.which(name)
    value = {
        "name": name,
        "installed": executable is not None,
        "executable": executable,
        "version": None,
        "authentication": "not_checked",
        "ready": False,
    }
    if not executable:
        return value
    try:
        version = subprocess.run(
            [executable, "--version"], capture_output=True, text=True, timeout=10
        )
        if version.returncode:
            return value
        value["version"] = version.stdout.strip()
        if name in ("codex", "claude"):
            args = ["login", "status"] if name == "codex" else ["auth", "status"]
            status = subprocess.run([executable, *args], capture_output=True, text=True, timeout=10)
            if name == "codex":
                logged_in = status.returncode == 0
            else:
                logged_in = json.loads(status.stdout).get("loggedIn") is True
            value["authentication"] = "authenticated" if logged_in else "login_required"
            value["ready"] = logged_in
        elif name == "docker":
            status = subprocess.run(
                [executable, "info", "--format", "{{.ServerVersion}}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            value["ready"] = status.returncode == 0
        else:
            value["ready"] = True
    except OSError, ValueError, subprocess.TimeoutExpired:
        value["authentication"] = "check_failed"
    return value


def capabilities() -> dict:
    return {
        "environment": "container" if Path("/.dockerenv").exists() else "native",
        "tools": [_probe(name) for name in ("codex", "claude", "harbor", "docker")],
    }
