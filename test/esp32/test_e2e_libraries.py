"""
The libraries of test/esp32/e2e, which CI installs into its app and builds with
a real ESP-IDF, installed here into the same project with no ESP-IDF at all,
so what the build is given is checked on every run of the tests: places' lines
under their places, {library} in them, and its files at their own paths; and
parts' lines under project and library, with their titles and its note.
"""

from pathlib import Path

from conftest import read

from lib_installer.core import cli

E2E = Path(__file__).resolve().parent / "e2e"


def _app(project):
    return project(cmakelists=read(E2E / "app" / "CMakeLists.txt"),
                   main=read(E2E / "app" / "main" / "CMakeLists.txt"),
                   defaults=read(E2E / "app" / "sdkconfig.defaults"))


def test_the_three_install_as_ci_builds_them(project, nobody, no_network):
    root = _app(project)

    assert cli.main([str(E2E / "demo"), str(E2E / "extra"), str(E2E / "places"), "--project", str(root)]) == 0

    places = root / "components" / "places"
    assert (places / "src" / "places.h").is_file()
    assert (places / "private" / "places_private.h").is_file()
    assert (places / "places.defaults").is_file()
    assert (root / "config" / "places.cfg").is_file()
    assert (root / "tools" / "places.txt").is_file()

    component = read(places / "CMakeLists.txt")
    assert '"src/places.c"' in component
    assert 'target_include_directories(${COMPONENT_LIB} PRIVATE "${COMPONENT_DIR}/private")' in component

    text = read(root / "CMakeLists.txt")
    assert 'list(APPEND SDKCONFIG_DEFAULTS "${CMAKE_CURRENT_SOURCE_DIR}/components/places/places.defaults")' in text
    # Both before include(project.cmake), extra's first, so its own guard has
    # set SDKCONFIG_DEFAULTS by the time places adds to it.
    assert (text.index("extra/defaults >>>") < text.index("places/before-project >>>")
            < text.index("include($ENV{IDF_PATH}") < text.index("places/after-project >>>"))
    assert "places" in read(root / "main" / "CMakeLists.txt")


def test_places_goes_with_its_blocks_and_tools_and_leaves_its_once_file(project, nobody, no_network):
    root = _app(project)
    cli.main([str(E2E / "demo"), str(E2E / "extra"), str(E2E / "places"), "--project", str(root)])

    assert cli.main(["--uninstall", "places", "--project", str(root)]) == 0

    assert "lib-installer: places" not in read(root / "CMakeLists.txt")
    assert "places" not in read(root / "main" / "CMakeLists.txt")
    assert not (root / "components" / "places").exists()
    assert not (root / "tools").exists()
    assert (root / "config" / "places.cfg").is_file()


def test_parts_writes_each_line_where_4_0_0_says_with_its_titles(project, nobody, no_network):
    root = _app(project)
    libraries = [str(E2E / name) for name in ("demo", "extra", "places", "parts")]

    assert cli.main(libraries + ["--project", str(root)]) == 0

    # The app's files are checked out with CRLF on Windows, and keep them.
    defaults = read(root / "sdkconfig.defaults").replace("\r\n", "\n")
    assert ("# Its answer\n"
            f"# {'*' * 78}\n"
            "# set here, where the project sees it\n"
            "CONFIG_PARTS_BASE=20\n"
            "# <<< lib-installer: parts <<<\n") in defaults
    # The user's own line, and demo's block, are where they were.
    assert defaults.startswith("CONFIG_DEMO_BASE=50\n")

    text = read(root / "CMakeLists.txt").replace("\r\n", "\n")
    assert text.index("include($ENV{IDF_PATH}") < text.index("parts/after-project >>>")
    assert "# Checked by main.c\n" in text

    component = read(root / "components" / "parts" / "CMakeLists.txt").replace("\r\n", "\n")
    assert "    REQUIRES\n        esp_timer\n)" in component
    assert "# Checked by parts.c\n" in component
    assert "target_compile_definitions(${COMPONENT_LIB} PRIVATE PARTS_OWN)" in component
    assert "parts" in read(root / "main" / "CMakeLists.txt")


def test_parts_goes_with_every_block_of_its_own(project, nobody, no_network):
    root = _app(project)
    cli.main([str(E2E / name) for name in ("demo", "extra", "places", "parts")] + ["--project", str(root)])

    assert cli.main(["--uninstall", "parts", "--project", str(root)]) == 0

    for name in ("CMakeLists.txt", "sdkconfig.defaults", "main/CMakeLists.txt"):
        assert "parts" not in read(root / name)

    assert not (root / "components" / "parts").exists()
