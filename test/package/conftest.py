"""
Shared fixtures for the tests of the command as a whole: every platform at
once, the way lib-installer runs, rather than one forced on as the tests of
each platform have it.
"""

import importlib.util
import os
import sys
from pathlib import Path

import pytest
import yaml

SRC = Path(__file__).resolve().parents[2] / "src"

# The package is the src folder itself, so it is loaded under its own name
# rather than found on sys.path, and before any test imports it.
if "lib_installer" not in sys.modules:
    _spec = importlib.util.spec_from_file_location(
        "lib_installer", SRC / "__init__.py", submodule_search_locations=[str(SRC)]
    )
    _package = importlib.util.module_from_spec(_spec)
    sys.modules["lib_installer"] = _package
    _spec.loader.exec_module(_package)

from lib_installer import cli  # noqa: E402
from lib_installer.core import cli as core_cli  # noqa: E402

# No test asks PyPI whether a newer installer is out.
os.environ["INSTALLER_NO_UPDATE_CHECK"] = "1"

STM32_CMAKELISTS = """cmake_minimum_required(VERSION 3.22)
project(Proj C ASM)
add_executable(${CMAKE_PROJECT_NAME} Core/Src/main.c)
"""

ZEPHYR_CMAKELISTS = """cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(app)

target_sources(app PRIVATE src/main.c)
"""

ESP32_CMAKELISTS = """cmake_minimum_required(VERSION 3.16)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(app)
"""

ESP32_MAIN = """idf_component_register(SRCS "main.c"
                    INCLUDE_DIRS ".")
"""

PLATFORMIO_INI = """[env:native]
platform = native
"""


def run(*argv):
    """One run of the lib-installer command. Returns its exit code."""
    return cli.main([str(arg) for arg in argv])


@pytest.fixture(autouse=True)
def sketchbook(tmp_path, monkeypatch):
    """
    A sketchbook of the test's own, so no run reads or moves over the
    machine's real one, which every run looks at for an Arduino record.
    """
    book = tmp_path / "Arduino"
    book.mkdir()
    monkeypatch.setenv("ARDUINO_DIRECTORIES_USER", str(book))
    monkeypatch.delenv("IDF_PATH", raising=False)

    return book


@pytest.fixture(autouse=True)
def nobody(monkeypatch):
    """Nobody at the keyboard: every question takes the answer it offers."""
    monkeypatch.setattr(core_cli, "_answer", lambda prompt: None)


@pytest.fixture
def library(tmp_path):
    """
    Build a library on disk and return its folder. platform is what its
    installer.yml says under platform, left out when None.
    """

    def build(name="demo", platform=None, requires=None, extra=None, root=None):
        root = Path(root) if root else tmp_path / "repos" / name
        (root / "src").mkdir(parents=True, exist_ok=True)
        (root / "src" / f"{name}.h").write_text(f"/**\n * @version 1.0.0\n */\nint {name}_answer(void);\n",
                                                encoding="utf-8")
        (root / "src" / f"{name}.c").write_text("int answer(void) { return 42; }\n", encoding="utf-8")
        data = {
            "name": name,
            "description": "A library for the tests",
            "repository": f"https://github.com/someone/{name}",
            "files": {"headers": [f"src/{name}.h"], "sources": [f"src/{name}.c"]},
        }

        if platform is not None:
            data["platform"] = platform

        if requires is not None:
            data["requires"] = requires

        data.update(extra or {})
        (root / "installer.yml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

        return root

    return build


def _write(root, files, crlf=False):
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((text.replace("\n", "\r\n") if crlf else text).encode("utf-8"))

    return root


@pytest.fixture
def project(tmp_path):
    """A project of the platform named, on disk: project("zephyr"), with any more files given."""

    def build(platform, files=None, crlf=False):
        root = tmp_path / f"{platform}-project"
        written = {
            "stm32": {"CMakeLists.txt": STM32_CMAKELISTS, "Core/Src/main.c": "/* main */\n",
                      "Core/Inc/main.h": "/* main */\n"},
            "zephyr": {"CMakeLists.txt": ZEPHYR_CMAKELISTS, "prj.conf": "CONFIG_GPIO=y\n",
                       "src/main.c": "int main(void) { return 0; }\n"},
            "esp32": {"CMakeLists.txt": ESP32_CMAKELISTS, "main/CMakeLists.txt": ESP32_MAIN,
                      "main/main.c": "void app_main(void) {}\n"},
            "pio": {"platformio.ini": PLATFORMIO_INI, "src/main.c": "int main(void) { return 0; }\n"},
            "arduino": {"arduino-project.ino": "void setup() {}\nvoid loop() {}\n"},
        }[platform]
        written.update(files or {})

        return _write(root, written, crlf)

    return build
