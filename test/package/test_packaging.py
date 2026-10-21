"""
The package metadata, which pip reads before any of the code runs.

Read as text rather than with tomllib, which only arrived in Python 3.11, and the
tests still run on 3.8.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_the_command_is_called_lib_installer():
    assert re.search(r'^lib-installer = "lib_installer\.cli:main"$', PYPROJECT, re.M)


def test_nothing_has_to_be_downloaded_to_install_it():
    """
    PyYAML is optional in the code. Listing it here would send pip online to get
    it, and break the one kind of install that has to work without a network.
    """
    found = re.search(r"^dependencies = \[(.*?)\]", PYPROJECT, re.M | re.S)

    assert found is not None
    assert found.group(1).strip() == ""


def test_every_folder_of_the_code_goes_into_the_package():
    """A folder left out of packages is missing from the wheel, and only an install shows it."""
    assert 'package-dir = { "lib_installer" = "src" }' in PYPROJECT

    src = ROOT / "src"
    folders = sorted(
        ".".join(("lib_installer",) + path.parent.relative_to(src).parts)
        for path in src.rglob("__init__.py")
    )
    listed = re.search(r"^packages = \[(.*?)\]", PYPROJECT, re.M | re.S).group(1)

    assert sorted(re.findall(r'"([a-z_.0-9]+)"', listed)) == folders
    assert "lib_installer.stm32.ide" in folders


def test_every_folder_of_the_code_has_an_init():
    """A folder of .py files without __init__.py is no package, and setuptools leaves it out."""
    src = ROOT / "src"
    loose = [path.parent for path in src.rglob("*.py") if not (path.parent / "__init__.py").is_file()]

    assert loose == []
