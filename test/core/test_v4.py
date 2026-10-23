"""
What 4.0.0 checks that every platform shares: a folder of install.include_dirs
is a path inside the library, which every project file it is written into
reads as a path, and a key given twice in installer.yml is refused, where YAML
would keep the last without a word.
"""

import re

import pytest

from lib_installer.core import manifest
from lib_installer.core.manifest import ManifestError


@pytest.mark.parametrize("folder, says", [
    ('src" onload="x', "it holds a quote, <, >, &, ;"),
    ("src;inc", "it holds a quote, <, >, &, ;"),
    ("src<x>", "it holds a quote, <, >, &, ;"),
    ("../../outside", "it climbs out with .."),
    ("/etc", "it starts at the root of the drive"),
    ("C:/Windows", "it names a drive"),
    ("", "it is empty"),
])
def test_an_include_folder_a_project_file_could_not_hold_is_refused(library, folder, says):
    with pytest.raises(ManifestError, match=re.escape(says)):
        manifest.load(library(install={"include_dirs": ["src", folder]}))


def test_a_plain_include_folder_is_taken_as_it_is(library):
    loaded = manifest.load(library(install={"include_dirs": ["src", "inc\\port", "."]}))

    assert loaded.include_dirs == ["src", "inc/port", "."]


def test_include_dirs_is_a_list(library):
    with pytest.raises(ManifestError, match="install.include_dirs is a list of folders"):
        manifest.load(library(install={"include_dirs": "src"}))


def test_a_key_given_twice_is_refused_when_the_manifest_is_read(library):
    root = library()
    path = root / "installer.yml"
    path.write_text(path.read_text(encoding="utf-8") + "kind: driver\n", encoding="utf-8")

    with pytest.raises(ManifestError, match="'kind' is given twice"):
        manifest.load(root)
