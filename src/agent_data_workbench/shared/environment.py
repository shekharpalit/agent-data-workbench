"""Runtime identity recorded with experiment artifacts."""

from __future__ import annotations

import os


def environment_identity() -> dict:
    import platform
    import sys

    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "package": "0.1.0",
        "pid": os.getpid(),
    }
