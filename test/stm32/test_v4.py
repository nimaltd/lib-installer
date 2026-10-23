"""
What 4.0.0 puts right on STM32: a peripheral given as a word alone, "- spi",
as every other platform takes it, is read rather than stopping the installer
with a Python error, and a count that is no whole number is refused with what
to write.
"""

import pytest

from lib_installer.core import manifest
from lib_installer.core.manifest import ManifestError


def test_a_peripheral_given_as_a_word_is_taken(library):
    loaded = manifest.load(library(requires={"peripherals": [
        "spi", {"type": "i2c", "count": 2, "note": "400 kHz"}]}))

    assert [p.describe() for p in loaded.requires.peripherals] == ["SPI", "I2C x2, 400 kHz"]


@pytest.mark.parametrize("count", ["two", 0, -1, True, "1.5"])
def test_a_count_that_is_no_whole_number_is_refused(library, count):
    with pytest.raises(ManifestError, match="requires.peripherals spi has a count of"):
        manifest.load(library(requires={"peripherals": [{"type": "spi", "count": count}]}))
