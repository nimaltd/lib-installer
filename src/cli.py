"""
The lib-installer command: the core's command line, with every platform.

The core chooses the platform of each run from the library's installer.yml, or
from --platform, and every platform's own options, such as --ide and --conf,
are on the one command line.
"""

import sys

from . import __version__
from .arduino.arduino import Arduino
from .core import cli
from .esp32.esp32 import Esp32
from .pio.pio import PlatformIO
from .stm32.stm32 import Stm32
from .zephyr.zephyr import Zephyr

# Each platform by the name platform: in installer.yml and --platform give it,
# in the order the help lists them.
PLATFORMS = {
    "stm32": lambda: Stm32(__version__),
    "zephyr": lambda: Zephyr(__version__),
    "esp32": lambda: Esp32(__version__),
    "arduino": lambda: Arduino(__version__),
    "pio": lambda: PlatformIO(__version__),
}

__all__ = ["PLATFORMS", "main"]


def main(argv=None, library_root=None):
    """Run the command. Returns a process exit code."""
    return cli.main(argv=argv, library_root=library_root, platforms=PLATFORMS)


if __name__ == "__main__":
    sys.exit(main())
