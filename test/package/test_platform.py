"""Which platform a run is: from the library's installer.yml, --platform, or the project's record."""

import json

import pytest

import lib_installer
from conftest import run
from lib_installer import cli
from lib_installer.core import manifest, target


def _record(root):
    return json.loads((root / ".lib-installer.json").read_text(encoding="utf-8"))


def _answering(monkeypatch, platform):
    """Someone who answers the platform question with platform, and nothing else."""
    asked = []

    def answer(prompt):
        if "Platform" in prompt:
            asked.append(prompt)
            return platform

        return None

    monkeypatch.setattr(cli.cli, "_answer", answer)

    return asked


def test_every_platform_is_one_of_lib_installers():
    assert tuple(cli.PLATFORMS) == manifest.PLATFORMS

    for name, make in cli.PLATFORMS.items():
        made = make()

        assert isinstance(made, target.Platform)
        assert (made.platform, made.legacy) == (name, f"{name}-installer")
        assert (made.name, made.record_name, made.requires_key) == (
            "lib-installer", ".lib-installer.json", "lib_installer")
        assert made.version == lib_installer.__version__
        assert made.label


def test_the_platform_comes_from_installer_yml(library, project):
    root = project("zephyr")

    assert run(library(platform="zephyr"), "--project", root) == 0

    assert _record(root)["platform"] == "zephyr"
    assert "demo" in _record(root)["libraries"]
    assert "# >>> lib-installer: demo >>>" in (root / "CMakeLists.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize("platform", ["stm32", "zephyr", "esp32", "pio"])
def test_each_platform_installs_what_names_it(library, project, platform):
    root = project(platform)

    assert run(library(platform=platform), "--project", root) == 0

    assert _record(root)["platform"] == platform


def test_a_library_for_arduino_goes_into_the_libraries_folder(library, project, sketchbook):
    root = project("arduino")

    assert run(library(platform="arduino"), "--project", root, "--into", "libraries") == 0

    assert _record(sketchbook / "libraries")["platform"] == "arduino"
    assert (sketchbook / "libraries" / "demo" / "library.properties").is_file()


def test_a_library_naming_no_platform_needs_platform(library, project, capsys):
    root = project("zephyr")

    assert run(library(), "--project", root) == 2

    assert "names no platform" in capsys.readouterr().err
    assert not (root / ".lib-installer.json").exists()


def test_platform_is_taken_for_a_library_naming_none(library, project):
    root = project("zephyr")

    assert run(library(), "--project", root, "--platform", "zephyr") == 0

    assert _record(root)["platform"] == "zephyr"


def test_a_platform_the_library_does_not_name_is_refused(library, project, capsys):
    root = project("zephyr")

    assert run(library(platform="stm32"), "--project", root, "--platform", "zephyr") == 2

    assert "demo is for stm32, and --platform gives zephyr" in capsys.readouterr().err
    assert not (root / ".lib-installer.json").exists()


def test_a_library_for_several_platforms_with_nobody_to_ask_needs_platform(library, project, capsys):
    root = project("zephyr")

    assert run(library(platform=["stm32", "zephyr"]), "--project", root) == 2

    assert "--platform" in capsys.readouterr().err


def test_a_library_for_several_platforms_takes_the_answer(library, project, monkeypatch):
    root = project("zephyr")
    asked = _answering(monkeypatch, "2")

    assert run(library(platform=["stm32", "zephyr"]), "--project", root) == 0

    assert len(asked) == 1
    assert _record(root)["platform"] == "zephyr"


def test_a_library_for_several_platforms_takes_the_records(library, project, monkeypatch):
    root = project("zephyr")
    assert run(library(name="first", platform="zephyr"), "--project", root) == 0
    asked = _answering(monkeypatch, "1")

    assert run(library(platform=["stm32", "zephyr"]), "--project", root) == 0

    assert asked == []
    assert set(_record(root)["libraries"]) == {"first", "demo"}


def test_the_record_and_the_library_must_agree(library, project, capsys):
    root = project("zephyr")
    assert run(library(name="first", platform="zephyr"), "--project", root) == 0
    capsys.readouterr()

    assert run(library(platform="stm32"), "--project", root) == 2

    assert "This project's record says zephyr, and demo is for stm32." in capsys.readouterr().err


def test_the_record_and_platform_must_agree(library, project, capsys):
    root = project("zephyr")
    assert run(library(name="first", platform="zephyr"), "--project", root) == 0
    capsys.readouterr()

    assert run(library(), "--project", root, "--platform", "pio") == 2

    assert "This project's record says zephyr, and --platform gives pio." in capsys.readouterr().err


def test_two_libraries_take_the_platform_they_share(library, project, monkeypatch):
    root = project("zephyr")
    asked = _answering(monkeypatch, "1")

    assert run(library(name="one", platform=["stm32", "zephyr"]), library(name="two", platform="zephyr"),
               "--project", root) == 0

    assert asked == []
    assert set(_record(root)["libraries"]) == {"one", "two"}


def test_libraries_of_different_platforms_are_refused_together(library, project, capsys):
    root = project("zephyr")

    assert run(library(name="one", platform="stm32"), library(name="two", platform="zephyr"),
               "--project", root) == 2

    assert "different platforms: one for stm32; two for zephyr" in capsys.readouterr().err


def test_an_option_of_another_platform_is_refused(library, project, capsys):
    root = project("zephyr")

    assert run(library(platform="zephyr"), "--project", root, "--ide", "cmake") == 2

    assert "--ide is for STM32 projects, and this one is for Zephyr." in capsys.readouterr().err
    assert not (root / ".lib-installer.json").exists()


def test_an_option_of_this_platform_is_taken(library, project):
    root = project("zephyr", files={"debug.conf": "CONFIG_DEBUG=y\n"})

    assert run(library(platform="zephyr"), "--project", root, "--conf", "debug.conf") == 0

    assert "lib-installer: demo" in (root / "debug.conf").read_text(encoding="utf-8")
    assert "lib-installer" not in (root / "prj.conf").read_text(encoding="utf-8")


def test_uninstall_takes_the_platform_from_the_record(library, project):
    root = project("zephyr")
    assert run(library(platform="zephyr"), "--project", root) == 0

    assert run("--uninstall", "demo", "--project", root) == 0

    assert "lib-installer" not in (root / "CMakeLists.txt").read_text(encoding="utf-8")
    assert _record(root)["libraries"] == {}


def test_uninstall_with_no_record_needs_platform(project, capsys):
    root = project("zephyr")

    assert run("--uninstall", "demo", "--project", root) == 2

    assert "Say it with --platform" in capsys.readouterr().err


def test_a_manifest_asking_for_3_0_0_names_its_platform(library, project, capsys):
    root = project("zephyr")

    assert run(library(requires={"lib_installer": "3.0.0"}), "--project", root, "--platform", "zephyr") == 2

    assert "asks for lib-installer 3.0.0 and names no platform" in capsys.readouterr().err


def test_a_manifest_naming_a_platform_that_is_none_is_refused(library, project, capsys):
    root = project("zephyr")

    assert run(library(platform="avr"), "--project", root) == 2

    assert "platform has 'avr'" in capsys.readouterr().err


def test_a_platform_named_in_capitals_is_read(library, project):
    root = project("zephyr")

    assert run(library(platform="Zephyr"), "--project", root) == 0

    assert _record(root)["platform"] == "zephyr"


def test_a_library_given_as_a_missing_path_is_said(project, capsys):
    root = project("zephyr")

    assert run("./nowhere", "--project", root) == 2

    assert "./nowhere does not exist." in capsys.readouterr().err


def test_a_folder_with_no_manifest_is_said(project, tmp_path, capsys):
    root = project("zephyr")
    (tmp_path / "empty").mkdir()

    assert run(tmp_path / "empty", "--project", root) == 2

    assert "holds no installer.yml" in capsys.readouterr().err


def test_a_message_naming_the_command_names_platform_when_it_was_given(project, capsys):
    root = project("zephyr")

    assert run("--project", root) == 2
    assert "for example: lib-installer owner/example" in capsys.readouterr().err

    assert run("--project", root, "--platform", "zephyr") == 2
    assert "for example: lib-installer --platform zephyr owner/example" in capsys.readouterr().err


def test_a_library_for_another_platform_is_refused_on_load(library):
    lib_installer.use("zephyr")

    with pytest.raises(manifest.ManifestError, match="demo works on stm32, .* not on zephyr"):
        manifest.load(library(platform="stm32"))

    assert manifest.load(library(name="any")).platforms is None


def test_use_chooses_a_platform_and_refuses_one_that_is_none():
    lib_installer.use("pio")
    assert target.current.platform == "pio"

    with pytest.raises(ValueError, match="avr"):
        lib_installer.use("avr")


def test_help_lists_each_platforms_options(capsys):
    with pytest.raises(SystemExit) as stopped:
        run("--help")

    shown = capsys.readouterr().out

    assert stopped.value.code == 0
    assert "--platform {stm32,zephyr,esp32,arduino,pio}" in shown

    for heading, option in (("STM32 only", "--ide"), ("Zephyr only", "--conf"), ("Arduino only", "--into")):
        assert shown.index(heading) < shown.index(option, shown.index(heading))
