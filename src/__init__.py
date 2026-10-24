"""
Install embedded C libraries into STM32, Zephyr, ESP-IDF, Arduino and
PlatformIO projects.

Installed with pip, it is the lib-installer command. It takes a library from
GitHub, from a downloaded zip, or from a folder. Which platform the project is
comes from the library's installer.yml, or from --platform when it names none.

The work that is the same on every platform is in core/. What a project of
each platform is, is in stm32/, zephyr/, esp32/, arduino/ and pio/.

See https://github.com/nimaltd/lib-installer
"""

__version__ = "4.0.1"

from .core.installer import InstallError, Result, install_in_place, install_to  # noqa: E402
from .core.manifest import Manifest, ManifestError, load  # noqa: E402

__all__ = [
    "InstallError",
    "Manifest",
    "ManifestError",
    "Result",
    "install_in_place",
    "install_to",
    "load",
    "main",
    "use",
]


def use(platform):
    """
    Choose the platform the functions above work for, such as "zephyr", before
    calling them. The command chooses it by itself.
    """
    from .cli import PLATFORMS
    from .core import target

    if platform not in PLATFORMS:
        raise ValueError(f"{platform!r} is not a platform. It is one of {', '.join(PLATFORMS)}.")

    target.use(PLATFORMS[platform]())


def main(argv=None):
    """Run the command line interface. Imported lazily to keep start-up cheap."""
    from .cli import main as _main

    return _main(argv=argv)
