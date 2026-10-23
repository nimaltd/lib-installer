"""
What 4.0.0 brings to an ESP-IDF project: the esp32 section says where each
line it writes goes. Under project, the project's own files: conf, the
library's block in sdkconfig.defaults, where requires.kconfig went before;
and cmake, its blocks in the project's CMakeLists.txt, under before-project
and after-project. Under library, its component: requires, the components its
code uses; and cmake, the lines of the component's CMakeLists.txt. settings
stays where it was.

Every list but requires can be given in groups under their titles, and a
symbol with a note: each file written carries both as comments, a title
between two lines of stars and a note above its symbol. The keys from before
4.0.0 are refused in a manifest asking for it, with where they went, and the
new ones in a manifest asking for less, which keeps the meanings it was
written for.

And what 4.0.0 puts right. A key the esp32 section does not have, such as a
misspelt settings, is refused in a manifest asking for 4.0.0, and named in a
warning in one asking for less, where before it was passed by with what it
said. And a library's block in the project's CMakeLists.txt that sets
SDKCONFIG_DEFAULTS, keeping sdkconfig.defaults in the list as extra's does,
is no longer taken for the project's own line: every later install of a
library with requires.kconfig warned that ESP-IDF might not read
sdkconfig.defaults, which it did.
"""

import re
from pathlib import Path

import pytest
from conftest import read

from lib_installer.core import cli, manifest
from lib_installer.core.manifest import ManifestError
from lib_installer.esp32 import project as prj

E2E = Path(__file__).resolve().parent / "e2e"

FOUR = {"lib_installer": "4.0.0"}
BEFORE = {"lib_installer": "3.0.0"}

STARS = "# " + "*" * 78

OPEN = ("# >>> lib-installer: demo >>>\n"
        "# Added by lib-installer, and written again on every install, so set\n"
        "# demo's symbols below this block rather than in it.\n")

CLOSE = "# <<< lib-installer: demo <<<\n"

FROM = "# From demo's installer.yml, and written again on every install.\n"

GROUPED = {
    "A faster tick": [{"FREERTOS_HZ=1000": "one tick a millisecond"}],
    "Quiet logs": ["LOG_DEFAULT_LEVEL_WARN", {"LOG_COLORS=n": "plain text, for a file"}],
}

BLOCK = ("# >>> lib-installer: extra/defaults >>>\n"
         "# From extra's installer.yml, and written again on every install.\n"
         'if(NOT SDKCONFIG_DEFAULTS AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/sdkconfig.defaults")\n'
         '    set(SDKCONFIG_DEFAULTS "${CMAKE_CURRENT_SOURCE_DIR}/sdkconfig.defaults")\n'
         "endif()\n"
         'list(APPEND SDKCONFIG_DEFAULTS "${CMAKE_CURRENT_SOURCE_DIR}/extra.defaults")\n'
         "# <<< lib-installer: extra/defaults <<<\n")


def _demo(library, project=None, own=None, requires=FOUR, esp32=None, extra=None):
    """demo, asking for 4.0.0: what it writes under project and under library."""
    part = {}

    if project is not None:
        part["project"] = project

    if own is not None:
        part["library"] = own

    part.update(esp32 or {})

    return library(name="demo", requires=requires, esp32=part, extra=dict({"platform": "esp32"}, **(extra or {})))


def _install(source, root, *more):
    return cli.main([str(source), "--project", str(root), *more])


def _component(root):
    """The component's CMakeLists.txt, written into components/demo."""
    return read(root / "components" / "demo" / "CMakeLists.txt")


def _project_cmake(middle):
    return ("cmake_minimum_required(VERSION 3.16)\n\n" + middle
            + "\ninclude($ENV{IDF_PATH}/tools/cmake/project.cmake)\nproject(app)\n")


# ----------------------------------------------------------------------------
# project: the project's own files
# ----------------------------------------------------------------------------


def test_project_conf_goes_into_sdkconfig_defaults(library, project, nobody, no_network):
    root = project()

    assert _install(_demo(library, project={"conf": ["FREERTOS_HZ=1000", "SPI_MASTER_IN_IRAM"]}), root) == 0

    assert read(root / "sdkconfig.defaults") == (
        OPEN + "CONFIG_FREERTOS_HZ=1000\nCONFIG_SPI_MASTER_IN_IRAM=y\n" + CLOSE)


def test_titles_and_notes_in_the_block_of_sdkconfig_defaults(library, project, nobody, no_network):
    root = project()

    assert _install(_demo(library, project={"conf": GROUPED}), root) == 0

    assert read(root / "sdkconfig.defaults") == OPEN + (
        "\n"
        f"{STARS}\n"
        "# A faster tick\n"
        f"{STARS}\n"
        "# one tick a millisecond\n"
        "CONFIG_FREERTOS_HZ=1000\n"
        "\n"
        f"{STARS}\n"
        "# Quiet logs\n"
        f"{STARS}\n"
        "CONFIG_LOG_DEFAULT_LEVEL_WARN=y\n"
        "# plain text, for a file\n"
        "CONFIG_LOG_COLORS=n\n") + CLOSE


def test_a_line_the_user_sets_keeps_its_note_and_its_place_in_its_group(library, project, nobody, no_network):
    root = project(defaults="CONFIG_FREERTOS_HZ=100\n")
    conf = {"A faster tick": [{"FREERTOS_HZ=1000": "one tick a millisecond"}, "FREERTOS_USE_TRACE_FACILITY"]}

    assert _install(_demo(library, project={"conf": conf}), root) == 0

    assert ("# A faster tick\n"
            f"{STARS}\n"
            "# one tick a millisecond\n"
            "# CONFIG_FREERTOS_HZ=1000  (left out: sdkconfig.defaults sets CONFIG_FREERTOS_HZ=100)\n"
            "CONFIG_FREERTOS_USE_TRACE_FACILITY=y\n"
            + CLOSE) in read(root / "sdkconfig.defaults")


def test_project_cmake_goes_into_the_projects_cmakelists_by_its_place(library, project, nobody, no_network):
    root = project()
    cmake = {"before-project": {"Its own defaults": ['list(APPEND SDKCONFIG_DEFAULTS "{library}/demo.defaults")']},
             "after-project": ['message(STATUS "after")']}

    assert _install(_demo(library, project={"cmake": cmake}), root) == 0

    assert read(root / "CMakeLists.txt") == (
        "cmake_minimum_required(VERSION 3.16)\n"
        "\n"
        "# >>> lib-installer: demo/before-project >>>\n" + FROM +
        f"{STARS}\n"
        "# Its own defaults\n"
        f"{STARS}\n"
        'list(APPEND SDKCONFIG_DEFAULTS "${CMAKE_CURRENT_SOURCE_DIR}/components/demo/demo.defaults")\n'
        "# <<< lib-installer: demo/before-project <<<\n"
        "\n"
        "include($ENV{IDF_PATH}/tools/cmake/project.cmake)\n"
        "project(app)\n"
        "\n"
        "# >>> lib-installer: demo/after-project >>>\n" + FROM +
        'message(STATUS "after")\n'
        "# <<< lib-installer: demo/after-project <<<\n")


# ----------------------------------------------------------------------------
# library: its component
# ----------------------------------------------------------------------------


def test_library_requires_goes_into_the_components_requires(library, project, nobody, no_network):
    root = project()

    assert _install(_demo(library, own={"requires": ["esp_timer", "esp_driver_i2c", "esp_timer"]}), root) == 0

    assert "    REQUIRES\n        esp_timer\n        esp_driver_i2c\n)\n" in _component(root)


def test_library_cmake_goes_into_the_components_cmakelists(library, project, nobody, no_network):
    root = project()
    cmake = {"Math": ["target_link_libraries(${COMPONENT_LIB} PRIVATE m)"],
             "Its private headers": ['target_include_directories(${COMPONENT_LIB} PRIVATE "{library}/private")']}

    assert _install(_demo(library, own={"cmake": cmake}), root) == 0

    assert ("# >>> lib-installer: demo/component >>>\n" + FROM +
            f"{STARS}\n"
            "# Math\n"
            f"{STARS}\n"
            "target_link_libraries(${COMPONENT_LIB} PRIVATE m)\n"
            "\n"
            f"{STARS}\n"
            "# Its private headers\n"
            f"{STARS}\n"
            'target_include_directories(${COMPONENT_LIB} PRIVATE "${COMPONENT_DIR}/private")\n'
            "# <<< lib-installer: demo/component <<<\n") in _component(root)


# ----------------------------------------------------------------------------
# Every file written
# ----------------------------------------------------------------------------


def test_a_plain_list_has_no_titles(library, project, nobody, no_network):
    root = project()

    _install(_demo(library, project={"conf": ["FREERTOS_HZ=1000"], "cmake": {"after-project": ["a()"]}},
                   own={"cmake": ["b()"]}), root)

    for path in (root / "sdkconfig.defaults", root / "CMakeLists.txt", root / "components" / "demo" / "CMakeLists.txt"):
        assert "*****" not in read(path)


def test_a_second_install_with_titles_changes_nothing(library, project, nobody, no_network):
    root = project()
    lib = _demo(library, project={"conf": GROUPED, "cmake": {"before-project": {"First": ["a()"]}}},
                own={"requires": ["esp_timer"], "cmake": {"Second": ["b()"]}})
    _install(lib, root)
    files = [root / "sdkconfig.defaults", root / "CMakeLists.txt", root / "components" / "demo" / "CMakeLists.txt"]
    before = {path: read(path) for path in files}
    backups = sorted(path.name for path in root.rglob("*.bak"))

    assert _install(lib, root) == 0

    assert {path: read(path) for path in files} == before
    assert sorted(path.name for path in root.rglob("*.bak")) == backups


def test_an_uninstall_gives_the_project_back_as_it_was(library, project, nobody, no_network):
    root = project(defaults="CONFIG_FREERTOS_HZ=100\n")
    files = [root / "sdkconfig.defaults", root / "CMakeLists.txt"]
    before = {path: read(path) for path in files}
    _install(_demo(library, project={"conf": GROUPED, "cmake": {"before-project": {"First": ["a()"]},
                                                                "after-project": ["b()"]}}), root)

    assert cli.main(["--uninstall", "demo", "--project", str(root)]) == 0

    assert {path: read(path) for path in files} == before
    assert not (root / "components" / "demo").exists()


def test_moving_from_before_changes_nothing_in_the_project(library, project, nobody, no_network):
    """The same lines, moved to where 4.0.0 has them, write the same files."""
    root = project()
    old = _demo(library, requires=dict(BEFORE, kconfig=["FREERTOS_HZ=1000"]),
                esp32={"requires": ["esp_timer"], "cmake": {"component": ["a()"], "before-project": ["b()"],
                                                            "after-project": ["c()"]}})
    _install(old, root)
    files = [root / "sdkconfig.defaults", root / "CMakeLists.txt", root / "components" / "demo" / "CMakeLists.txt"]
    before = {path: read(path) for path in files}

    new = _demo(library, project={"conf": ["FREERTOS_HZ=1000"],
                                  "cmake": {"before-project": ["b()"], "after-project": ["c()"]}},
                own={"requires": ["esp_timer"], "cmake": ["a()"]})

    assert _install(new, root) == 0

    assert {path: read(path) for path in files} == before


# ----------------------------------------------------------------------------
# Options
# ----------------------------------------------------------------------------


def test_an_options_cmake_is_under_project_and_library(library, project, nobody, no_network):
    root = project()
    options = {"fast": {"description": "Built for speed", "esp32": {
        "project": {"cmake": {"after-project": ['message(STATUS "fast")']}},
        "library": {"cmake": {"Speed": ["target_compile_options(${COMPONENT_LIB} PRIVATE -O2)"]}}}}}
    source = _demo(library, extra={"options": options})

    _install(source, root, "--with", "fast")
    assert "demo/fast-after-project >>>" in read(root / "CMakeLists.txt")
    assert f"demo/fast-component >>>\n{FROM}{STARS}\n# Speed\n" in _component(root)

    _install(source, root, "--without", "fast")
    assert "demo/fast" not in read(root / "CMakeLists.txt")
    assert "demo/fast" not in _component(root)


@pytest.mark.parametrize("esp32, requires, says", [
    ({"cmake": {"component": ["a()"]}}, FOUR,
     "options.fast.esp32.cmake is options.fast.esp32.project.cmake and options.fast.esp32.library.cmake"),
    ({"library": {"cmake": ["a()"]}}, BEFORE, "options.fast.esp32.project and options.fast.esp32.library "
                                              "are new in 4.0.0"),
    ({"project": {"conf": ["LOG_COLORS=n"]}}, FOUR, "options.fast.esp32.project has conf. It holds cmake."),
])
def test_an_options_cmake_in_the_other_releases_place_is_refused(library, esp32, requires, says):
    options = {"fast": {"description": "x", "esp32": esp32}}

    with pytest.raises(ManifestError, match=re.escape(says)):
        manifest.load(_demo(library, requires=requires, extra={"options": options}))


# ----------------------------------------------------------------------------
# What is refused
# ----------------------------------------------------------------------------


@pytest.mark.parametrize("esp32, says", [
    ({"requires": ["esp_timer"]}, "esp32.requires is esp32.library.requires from 4.0.0"),
    ({"cmake": {"component": ["a()"]}}, "esp32.cmake is esp32.project.cmake and esp32.library.cmake from 4.0.0"),
    ({"setings": []}, "esp32 has setings. It holds settings, project, library."),
])
def test_the_keys_from_before_are_refused_with_where_they_went(library, esp32, says):
    with pytest.raises(ManifestError, match=re.escape(says)):
        manifest.load(_demo(library, esp32=esp32))


def test_requires_kconfig_is_refused_from_4_0_0(library):
    with pytest.raises(ManifestError, match="requires.kconfig is esp32.project.conf from 4.0.0"):
        manifest.load(_demo(library, requires=dict(FOUR, kconfig=["FREERTOS_HZ=1000"])))


@pytest.mark.parametrize("esp32, says", [
    ({"project": {"conf": ["FREERTOS_HZ=1000"]}}, "esp32.project is new in 4.0.0"),
    ({"library": {"requires": ["esp_timer"]}}, "esp32.library is new in 4.0.0"),
])
def test_the_new_keys_are_refused_in_a_manifest_asking_for_less(library, esp32, says):
    with pytest.raises(ManifestError, match=re.escape(says)):
        manifest.load(_demo(library, requires=BEFORE, esp32=esp32))


@pytest.mark.parametrize("project, own, says", [
    ({"requires": ["esp_timer"]}, None, "esp32.project has requires. It holds conf, cmake."),
    (None, {"conf": ["FREERTOS_HZ=1000"]}, "esp32.library has conf. It holds requires, cmake."),
    ({"cmake": {"component": ["a()"]}}, None, "esp32.project.cmake has component. It holds before-project, "
                                              "after-project."),
    (["FREERTOS_HZ=1000"], None, "esp32.project holds conf, cmake"),
])
def test_what_a_part_does_not_hold_is_refused(library, project, own, says):
    with pytest.raises(ManifestError, match=re.escape(says)):
        manifest.load(_demo(library, project=project, own=own))


@pytest.mark.parametrize("project, own, says", [
    ({"conf": ["freertos_hz"]}, None, "esp32.project.conf has 'freertos_hz'. Write a Kconfig symbol"),
    ({"conf": ["FREERTOS_HZ=fast"]}, None, "esp32.project.conf has 'FREERTOS_HZ=fast'. Give a symbol"),
    ({"conf": {"A": ["FREERTOS_HZ=1000"], "B": ["CONFIG_FREERTOS_HZ=100"]}}, None,
     "esp32.project.conf has FREERTOS_HZ more than once"),
    (None, {"requires": {"Timers": ["esp_timer"]}}, "esp32.library.requires is a list of ESP-IDF components"),
    (None, {"requires": [{"esp_timer": "for the time"}]}, "with no titles or notes"),
    (None, {"requires": ["esp timer"]}, "esp32.library.requires has 'esp timer'"),
])
def test_what_cannot_be_written_is_refused(library, project, own, says):
    with pytest.raises(ManifestError, match=re.escape(says)):
        manifest.load(_demo(library, project=project, own=own))


@pytest.mark.parametrize("project, says", [
    ({"conf": {"Two\nlines": ["FREERTOS_HZ=1000"]}}, "Give it one line of text"),
    ({"conf": {">>> lib-installer: x >>>": ["FREERTOS_HZ=1000"]}}, "what the installer marks its blocks with"),
    ({"conf": [{"FREERTOS_HZ=1000": "CONFIG_FREERTOS_HZ is not set"}]}, "Kconfig would read as a setting"),
    ({"conf": {"Empty": []}}, "has the title 'Empty' with no list under it"),
    ({"cmake": {"after-project": [{'message(STATUS "a': 'b")'}]}}, "which YAML reads as a mapping"),
])
def test_titles_and_notes_that_cannot_be_written_are_refused(library, project, says):
    with pytest.raises(ManifestError, match=re.escape(says)):
        manifest.load(_demo(library, project=project))


# ----------------------------------------------------------------------------
# A key the section does not have, and SDKCONFIG_DEFAULTS
# ----------------------------------------------------------------------------


def test_a_key_the_section_does_not_have_is_warned_about_before(library):
    loaded = manifest.load(library(esp32={"setings": []}, requires=BEFORE, extra={"platform": "esp32"}))

    assert "esp32.setings is no key lib-installer reads, so it was left out" in loaded.warnings


def test_a_librarys_block_setting_sdkconfig_defaults_is_not_the_projects_line(project):
    assert not prj.names_its_defaults(project(cmakelists=_project_cmake(BLOCK)))


def test_the_projects_own_line_setting_sdkconfig_defaults_still_counts(project):
    own = 'set(SDKCONFIG_DEFAULTS "sdkconfig.defaults;sdkconfig.release")\n'

    assert prj.names_its_defaults(project(cmakelists=_project_cmake(own + BLOCK)))


def test_installing_again_after_extra_gives_no_warning_about_sdkconfig_defaults(project, nobody, no_network,
                                                                                capsys):
    root = project()
    libraries = [str(E2E / "demo"), str(E2E / "extra"), str(E2E / "places")]
    cli.main(libraries + ["--project", str(root)])
    capsys.readouterr()

    assert cli.main(libraries + ["--project", str(root)]) == 0

    assert "sets SDKCONFIG_DEFAULTS" not in capsys.readouterr().out
