"""
lib-installer is now libNIMA.

This last release only says so. libNIMA is the same installer, rewritten, with a
window beside the command line and no Python: https://github.com/nimaltd/libNIMA
"""

__version__ = "5.0.0"

__all__ = ["main"]


def main(argv=None):
    """Say where lib-installer went. Returns a process exit code."""
    from .cli import main as _main

    return _main(argv=argv)
