"""
What 4.0.0 brings to a PlatformIO project: the pio section says where each
thing it gives goes. Under project, the project's platformio.ini: build_flags,
the flags every file of the build is given, written after the library's
defines in its block of build_flags. Under library, its library.json:
frameworks, platforms and dependencies, where the pio section had them before.

build_flags can be given in groups under their titles, and a flag with a
note: the block carries both as comments of platformio.ini, ; like its
markers, a title between two lines of stars and a note above its flag, with
no blank line. library.json is JSON, which has no comments, so its lists have
neither. The keys from before 4.0.0 are refused in a manifest asking for it,
with where they went, and the new ones in a manifest asking for less.

And what 4.0.0 puts right: a dependency given twice is refused, where the
second quietly took the first one's place, and a key the pio section does not
have, such as a misspelt frameworks, is refused in a manifest asking for
4.0.0, and named in a warning in one asking for less.
"""

import json
import re
from pathlib import Path

import pytest
from conftest import read

from lib_installer.core import cli, manifest
from lib_installer.core.manifest import ManifestError
from lib_installer.core.target import MANUAL
from lib_installer.pio import ini

E2E = Path(__file__).resolve().parent / "e2e"

FOUR = {"lib_installer": "4.0.0"}
BEFORE = {"lib_installer": "3.0.0"}

STARS = "; " + "*" * 78

# Two environments: one with build_flags of its own, one that takes them from
# [env], which the install makes.
TWO = "[env:native]\nplatform = native\nbuild_flags = -DFROM_YOU=1\n\n[env:plain]\nplatform = native\n"

GROUPED = {
    "Printing": [{"-Wl,-u,_printf_float": 'printf("%f") prints nothing without it'}],
    "Speed": ["-O2", "-I include"],
}


def _demo(library, project=None, own=None, requires=FOUR, pio=None, defines=None):
    """demo, asking for 4.0.0: what it gives under project and under library."""
    part = {}

    if project is not None:
        part["project"] = project

    if own is not None:
        part["library"] = own

    part.update(pio or {})

    return library(name="demo", requires=requires, pio=part, defines=defines, extra={"platform": "pio"})


def _install(source, root, *more):
    return cli.main([str(source), "--project", str(root), *more])


def _both(*lines):
    """platformio.ini of TWO with the block of these lines in [env] and in [env:native]."""
    block = ("    ; >>> lib-installer: demo >>>\n"
             + "".join(f"    {line}\n" if line else "\n" for line in lines)
             + "    ; <<< lib-installer: demo <<<\n")

    return ("[env]\nbuild_flags =\n" + block + "\n"
            "[env:native]\nplatform = native\nbuild_flags = -DFROM_YOU=1\n" + block + "\n"
            "[env:plain]\nplatform = native\n")


# ----------------------------------------------------------------------------
# project: platformio.ini
# ----------------------------------------------------------------------------


def test_build_flags_go_after_the_defines_wherever_build_flags_reach(library, project, nobody, no_network):
    root = project(ini=TWO)

    assert _install(_demo(library, project={"build_flags": ["-O2", "-Wl,-u,_printf_float"]},
                          defines=["DEMO_FAST"]), root) == 0

    assert read(root / "platformio.ini") == _both("-DDEMO_FAST", "-O2", "-Wl,-u,_printf_float")


def test_titles_and_notes_are_comments_of_platformio_ini_with_no_blank_line(library, project, nobody, no_network):
    root = project(ini=TWO)

    assert _install(_demo(library, project={"build_flags": GROUPED}), root) == 0

    text = read(root / "platformio.ini")
    assert text == _both(STARS, "; Printing", STARS, '; printf("%f") prints nothing without it',
                         "-Wl,-u,_printf_float", STARS, "; Speed", STARS, "-O2", "-I include")
    assert "\n\n    ;" not in text


def test_what_a_run_says_names_the_flags(library, project, nobody, no_network, capsys):
    root = project()

    _install(_demo(library, project={"build_flags": ["-O2", "-Wl,-u,_printf_float"]}), root)

    assert "-O2, -Wl,-u,_printf_float go into build_flags in platformio.ini" in capsys.readouterr().out


def test_a_second_install_changes_nothing_and_an_uninstall_gives_the_file_back(library, project, nobody,
                                                                               no_network, capsys):
    root = project(ini=TWO)
    lib = _demo(library, project={"build_flags": GROUPED}, defines=["DEMO_FAST"])
    _install(lib, root)
    installed = read(root / "platformio.ini")
    backups = sorted(path.name for path in root.rglob("*.bak"))

    assert _install(lib, root) == 0
    assert read(root / "platformio.ini") == installed
    assert sorted(path.name for path in root.rglob("*.bak")) == backups

    capsys.readouterr()
    assert cli.main(["--uninstall", "demo", "--project", str(root)]) == 0
    assert read(root / "platformio.ini") == TWO
    assert "Removed demo's defines and build flags from platformio.ini." in capsys.readouterr().out


def test_an_update_without_build_flags_takes_its_block_out(library, project, nobody, no_network, capsys):
    root = project(ini=TWO)
    _install(_demo(library, project={"build_flags": ["-O2"]}), root)
    capsys.readouterr()

    assert _install(_demo(library), root) == 0

    assert read(root / "platformio.ini") == TWO
    assert "Took demo's old build flags out of platformio.ini." in capsys.readouterr().out


def test_a_half_written_block_is_left_alone_with_the_flags_to_add(library, project, nobody, no_network):
    text = "[env:native]\nbuild_flags =\n    ; >>> lib-installer: demo >>>\n    -DOLD\n\nlib_deps = mine\n"
    root = project(ini=text)
    loaded = manifest.load(_demo(library, project={"build_flags": GROUPED}, defines=["DEMO_FAST"]))

    outcome = ini.integrate(root, loaded)

    assert outcome.status == MANUAL
    assert outcome.steps[1:] == ["-DDEMO_FAST", "-Wl,-u,_printf_float", "-O2", "-I include"]
    assert read(root / "platformio.ini") == text


def test_the_e2e_flags_go_in_after_demo_as_ci_builds_them_and_back_out(project, nobody, no_network):
    """test/pio/e2e/flags, as CI installs it into its app beside demo and helper, and takes them out."""
    before = read(E2E / "app" / "platformio.ini")
    root = project(ini=before)
    cli.main([str(E2E / "demo"), str(E2E / "helper"), "--project", str(root)])

    assert cli.main([str(E2E / "flags"), "--project", str(root)]) == 0

    # The app is checked out with CRLF on Windows, and keeps it.
    text = read(root / "platformio.ini").replace("\r\n", "\n")
    assert text.count("    ; >>> lib-installer: flags >>>\n"
                      f"    {STARS}\n"
                      "    ; Its level\n"
                      f"    {STARS}\n"
                      "    ; flags.h stops the build without it\n"
                      "    -DFLAGS_LEVEL=7\n") == 2
    assert text.index("lib-installer: demo <<<") < text.index("lib-installer: flags >>>")
    assert json.loads(read(root / "lib" / "flags" / "library.json"))["platforms"] == ["native"]

    for name in ("demo", "flags"):
        assert cli.main(["--uninstall", name, "--project", str(root)]) == 0

    assert read(root / "platformio.ini") == before


# ----------------------------------------------------------------------------
# library: library.json
# ----------------------------------------------------------------------------


def test_library_goes_into_library_json(library, project, nobody, no_network):
    root = project()
    own = {"frameworks": ["arduino", "espidf"], "platforms": ["espressif32"],
           "dependencies": ["bblanchon/ArduinoJson@^7", "someone/plain"]}

    assert _install(_demo(library, own=own), root) == 0

    data = json.loads(read(root / "lib" / "demo" / "library.json"))
    assert (data["frameworks"], data["platforms"]) == (["arduino", "espidf"], ["espressif32"])
    assert data["dependencies"] == {"bblanchon/ArduinoJson": "^7", "someone/plain": "*"}


def test_moving_from_before_changes_nothing_in_the_project(library, project, nobody, no_network):
    """The same lists, moved under library as 4.0.0 has them, write the same files."""
    root = project(ini=TWO)
    lists = {"frameworks": ["arduino"], "platforms": ["native"], "dependencies": ["bblanchon/ArduinoJson@^7"]}
    _install(_demo(library, requires=BEFORE, pio=lists, defines=["DEMO_FAST"]), root)
    files = [root / "platformio.ini", root / "lib" / "demo" / "library.json"]
    before = {path: read(path) for path in files}

    assert _install(_demo(library, own=lists, defines=["DEMO_FAST"]), root) == 0

    assert {path: read(path) for path in files} == before


# ----------------------------------------------------------------------------
# What is refused
# ----------------------------------------------------------------------------


@pytest.mark.parametrize("pio, says", [
    ({"frameworks": ["arduino"]}, "pio.frameworks is pio.library.frameworks from 4.0.0"),
    ({"platforms": ["native"]}, "pio.platforms is pio.library.platforms from 4.0.0"),
    ({"dependencies": ["bblanchon/ArduinoJson@^7"]}, "pio.dependencies is pio.library.dependencies from 4.0.0"),
    ({"framework": "arduino"}, "pio has framework. It holds project, library."),
])
def test_the_keys_from_before_are_refused_with_where_they_went(library, pio, says):
    with pytest.raises(ManifestError, match=re.escape(says)):
        manifest.load(_demo(library, pio=pio))


@pytest.mark.parametrize("pio, says", [
    ({"project": {"build_flags": ["-O2"]}}, "pio.project is new in 4.0.0"),
    ({"library": {"platforms": ["native"]}}, "pio.library is new in 4.0.0"),
])
def test_the_new_keys_are_refused_in_a_manifest_asking_for_less(library, pio, says):
    with pytest.raises(ManifestError, match=re.escape(says)):
        manifest.load(_demo(library, requires=BEFORE, pio=pio))


@pytest.mark.parametrize("project, own, says", [
    ({"flags": ["-O2"]}, None, "pio.project has flags. It holds build_flags."),
    (None, {"build_flags": ["-O2"]}, "pio.library has build_flags. It holds frameworks, platforms, dependencies."),
    (["-O2"], None, "pio.project holds build_flags"),
])
def test_what_a_part_does_not_hold_is_refused(library, project, own, says):
    with pytest.raises(ManifestError, match=re.escape(says)):
        manifest.load(_demo(library, project=project, own=own))


@pytest.mark.parametrize("own, says", [
    ({"platforms": {"Boards": ["native"]}}, "pio.library.platforms has a title or a note"),
    ({"frameworks": [{"arduino": "the one it is tested with"}]}, "pio.library.frameworks has a title or a note"),
    ({"dependencies": [{"bblanchon/ArduinoJson@^7": "for the settings file"}]},
     "pio.library.dependencies has a title or a note, which library.json, being JSON, has no room for"),
    ({"dependencies": ["bblanchon/ArduinoJson@^6", "bblanchon/ArduinoJson@^7"]},
     "pio.library.dependencies has bblanchon/ArduinoJson more than once"),
])
def test_what_library_json_cannot_hold_is_refused(library, own, says):
    with pytest.raises(ManifestError, match=re.escape(says)):
        manifest.load(_demo(library, own=own))


@pytest.mark.parametrize("flag", [
    "!echo -DX",                 # PlatformIO runs a command for a line starting with !
    "-DX=$(HOME)",               # SCons expands $
    "-DX=${sysenv.HOME}",
    "-DX;rm",                    # ; starts a comment
    "-O2 #fast",                 # and so does #
    '-DMSG="hi"',
    "O2",                        # no option
    "-DA\n-DB",
    "",
    5,
])
def test_a_flag_that_could_be_read_as_more_than_a_flag_is_refused(library, flag):
    with pytest.raises(ManifestError, match="pio.project.build_flags has .* Give a flag as the compiler takes it"):
        manifest.load(_demo(library, project={"build_flags": [flag]}))


@pytest.mark.parametrize("build_flags, says", [
    ({"A": ["-O2"], "B": ["-O2"]}, "pio.project.build_flags has -O2 more than once"),
    ({">>> lib-installer: x >>>": ["-O2"]}, "what the installer marks its blocks with"),
    ([{"-O2": "first\nsecond"}], "Give it one line of text"),
    ({"Empty": []}, "has the title 'Empty' with no list under it"),
])
def test_build_flags_that_cannot_be_written_are_refused(library, build_flags, says):
    with pytest.raises(ManifestError, match=re.escape(says)):
        manifest.load(_demo(library, project={"build_flags": build_flags}))


def test_a_dependency_given_twice_is_refused_before_4_0_0_too(library):
    pio = {"dependencies": ["bblanchon/ArduinoJson@^6", "bblanchon/ArduinoJson@^7"]}

    with pytest.raises(ManifestError, match="pio.dependencies has bblanchon/ArduinoJson more than once"):
        manifest.load(library(pio=pio))


def test_a_key_the_section_does_not_have_is_warned_about_before(library):
    loaded = manifest.load(library(pio={"framework": "arduino"}, requires=BEFORE, extra={"platform": "pio"}))

    assert "pio.framework is no key lib-installer reads, so it was left out" in loaded.warnings
