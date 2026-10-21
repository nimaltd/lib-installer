#!/usr/bin/env python3
"""
Build and run the tests, then print the result.

Usage:
    python test/run_tests.py              run everything
    python test/run_tests.py -k manifest  run the tests whose name matches

Each folder is a pytest run of its own: core, package, and one for each
platform. The tests of a platform make it the platform of every run, and the
folders share the names of their test files, so one run of them all would mix
the two up.

Named to match the runner in the C library repositories, so the same command
works everywhere: python test/run_tests.py
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FOLDERS = ("core", "package", "stm32", "zephyr", "esp32", "arduino", "pio")


def main():
    try:
        import pytest  # noqa: F401
    except ImportError:
        print("pytest is not installed. Installing it now ...", flush=True)
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--quiet", "pytest", "PyYAML"]
            )
        except subprocess.CalledProcessError:
            print(f"\nInstall it yourself:\n\n    {sys.executable} -m pip install pytest\n")
            return 2

    failed = []

    for folder in FOLDERS:
        command = [sys.executable, "-m", "pytest", str(ROOT / "test" / folder), "-q",
                   "-p", "no:cacheprovider"] + sys.argv[1:]

        print(f">>> {' '.join(command)}\n", flush=True)
        code = subprocess.run(command, cwd=ROOT).returncode
        print()

        # 5 is pytest finding no test to run, which -k does to most folders.
        if code not in (0, 5):
            failed.append(folder)

    print("PASS: every test succeeded." if not failed else f"FAIL: see the failures above, in {', '.join(failed)}.")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
