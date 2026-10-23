"""
What 4.0.0 puts right on Arduino: a key the arduino section does not have,
such as a misspelt architectures, is refused in a manifest asking for 4.0.0,
and named in a warning in one asking for less, where before it was passed by
with what it said.
"""

import pytest

from lib_installer.core import manifest
from lib_installer.core.manifest import ManifestError

FOUR = {"lib_installer": "4.0.0"}
BEFORE = {"lib_installer": "3.0.0"}


def test_a_key_the_section_does_not_have_is_refused_from_4_0_0(library):
    with pytest.raises(ManifestError, match="arduino has architecture. It holds architectures, category"):
        manifest.load(library(arduino={"architecture": "avr"}, requires=FOUR, extra={"platform": "arduino"}))


def test_a_key_the_section_does_not_have_is_warned_about_before(library):
    loaded = manifest.load(library(arduino={"architecture": "avr"}, requires=BEFORE,
                                   extra={"platform": "arduino"}))

    assert "arduino.architecture is no key lib-installer reads, so it was left out" in loaded.warnings
