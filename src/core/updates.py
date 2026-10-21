"""
Telling the user a newer installer is out.

At most once a day the version on PyPI is asked for, in the background while
the install runs, and kept in the user's cache folder. When it is newer than
the one running, the last line of the run says so, with the command to update.

It must never be in the way: no answer within a second or two, no internet, a
proxy, a cache folder that cannot be written, all mean saying nothing. It is
off with --no-update-check, with INSTALLER_NO_UPDATE_CHECK set, and on a build
server, where CI is set.
"""

import json
import os
import threading
import time
import urllib.request
from pathlib import Path

PYPI_URL = "https://pypi.org/pypi/{name}/json"

# How long an answer is good for, and how long to wait for a new one.
DAY_SECONDS = 24 * 60 * 60
TIMEOUT_SECONDS = 2

# Turns the check off, whatever installer is running.
OFF_VARIABLES = ("INSTALLER_NO_UPDATE_CHECK", "CI")


def _version(text):
    """(2, 0, 1) from "2.0.1", or None for anything else, a pre-release included."""
    parts = str(text).strip().split(".")

    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None

    return tuple(int(part) for part in parts)


def cache_file(name):
    """Where the last answer is kept: the user's cache folder, one per installer."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")

    return Path(base) / name / "latest.json"


def _cached(path):
    """The version kept from a check less than a day old, or None."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

    if not isinstance(data, dict) or time.time() - float(data.get("checked", 0)) > DAY_SECONDS:
        return None

    return data.get("latest")


def _ask(name):
    """The newest version on PyPI, or None."""
    with urllib.request.urlopen(PYPI_URL.format(name=name), timeout=TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))["info"]["version"]


def latest(name):
    """The newest version, from the cache or PyPI, or None. Never raises."""
    path = cache_file(name)
    found = _cached(path)

    if found is not None:
        return found

    try:
        found = _ask(name)
    except Exception:
        return None

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"checked": time.time(), "latest": found}) + "\n", encoding="utf-8")
    except OSError:
        pass

    return found


class Check:
    """A check started in the background, asked for its answer at the end of the run."""

    def __init__(self, name, version, enabled=True):
        self.name = name
        self.version = version
        self.found = None
        self.thread = None

        if enabled and not any(os.environ.get(v) for v in OFF_VARIABLES):
            self.thread = threading.Thread(target=self._work, daemon=True)
            self.thread.start()

    def _work(self):
        self.found = latest(self.name)

    def message(self, wait=TIMEOUT_SECONDS):
        """The line to print when a newer version is out, or None."""
        if self.thread is None:
            return None

        self.thread.join(wait)
        have, newer = _version(self.version), _version(self.found or "")

        if have is None or newer is None or newer <= have:
            return None

        return (f"{self.name} {self.found} is out, and this is {self.version}. "
                f"Update with: pip install --upgrade {self.name}")
