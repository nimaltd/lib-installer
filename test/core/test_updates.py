"""Telling the user a newer installer is out: once a day, never in the way."""

import json
import time

import pytest

from lib_installer.core import updates


@pytest.fixture
def cache(monkeypatch, tmp_path):
    """A cache folder of the test's own, and the check switched back on."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    for name in updates.OFF_VARIABLES:
        monkeypatch.delenv(name, raising=False)

    return tmp_path


def _pypi(monkeypatch, answer):
    asked = []

    def ask(name):
        asked.append(name)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(updates, "_ask", ask)

    return asked


def test_a_newer_version_is_said_with_the_command(cache, monkeypatch):
    _pypi(monkeypatch, "2.1.0")

    message = updates.Check("zephyr-installer", "2.0.0").message()

    assert message == ("zephyr-installer 2.1.0 is out, and this is 2.0.0. "
                       "Update with: pip install --upgrade zephyr-installer")


@pytest.mark.parametrize("latest", ["2.0.0", "1.9.9", "2.1.0rc1", "garbage"])
def test_nothing_newer_says_nothing(cache, monkeypatch, latest):
    _pypi(monkeypatch, latest)

    assert updates.Check("zephyr-installer", "2.0.0").message() is None


def test_no_internet_says_nothing(cache, monkeypatch):
    _pypi(monkeypatch, OSError("no route"))

    assert updates.Check("zephyr-installer", "2.0.0").message() is None


def test_pypi_is_asked_at_most_once_a_day(cache, monkeypatch):
    asked = _pypi(monkeypatch, "2.1.0")

    updates.Check("pio-installer", "2.0.0").message()
    second = updates.Check("pio-installer", "2.0.0").message()

    assert asked == ["pio-installer"]
    assert "2.1.0 is out" in second


def test_an_answer_older_than_a_day_is_asked_again(cache, monkeypatch):
    path = updates.cache_file("pio-installer")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"checked": time.time() - 2 * updates.DAY_SECONDS, "latest": "2.0.5"}))
    asked = _pypi(monkeypatch, "2.2.0")

    assert "2.2.0 is out" in updates.Check("pio-installer", "2.0.0").message()
    assert asked == ["pio-installer"]


@pytest.mark.parametrize("variable", updates.OFF_VARIABLES)
def test_it_is_off_on_a_build_server_or_when_asked(cache, monkeypatch, variable):
    asked = _pypi(monkeypatch, "9.0.0")
    monkeypatch.setenv(variable, "1")

    assert updates.Check("pio-installer", "2.0.0").message() is None
    assert asked == []


def test_it_is_off_with_the_option(cache, monkeypatch):
    asked = _pypi(monkeypatch, "9.0.0")

    assert updates.Check("pio-installer", "2.0.0", enabled=False).message() is None
    assert asked == []
