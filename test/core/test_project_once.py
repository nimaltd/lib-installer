"""
once in a manifest written for 2.0.0: files that land in the project's own folder.

A product needs files next to its own build files that no library can ship as
its code: a VERSION, a CHANGELOG, an overlay its build system reads from the
application's folder. Each is copied when it is missing and never touched
again: not by an update, and not by an uninstall. A manifest from before 2.0.0
keeps the meaning it was written for, in the library's own folder.
"""

import json

import pytest

from lib_installer.core import cli, download, installer, manifest, target
from lib_installer.core.manifest import ManifestError

MODERN = {"installer": "2.0.0"}


@pytest.fixture
def nobody(monkeypatch):
    monkeypatch.setattr(cli, "_answer", lambda prompt: None)


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("tried to use the network")

    monkeypatch.setattr(download, "fetch", refuse)


def _lib(library, once, **kwargs):
    files = {
        "project/VERSION": "VERSION_MAJOR = 1\n",
        "project/CHANGELOG.md": "# Changelog\n",
        "boards/nrf54l15.overlay": "/ { };\n",
        "port/port.c": "/* port */\n",
    }
    files.update(kwargs.pop("extra_files", {}))

    return library(once=once, requires=kwargs.pop("requires", MODERN), extra_files=files, **kwargs)


def _install(*args):
    return cli.main([str(arg) for arg in args])


def _record(root):
    return json.loads((root / ".test-installer.json").read_text(encoding="utf-8"))["libraries"]


ONCE = [
    {"from": "project/VERSION"},
    {"from": "project/CHANGELOG.md"},
    {"from": "boards/nrf54l15.overlay", "to": "socs/nrf54l15_cpuapp.overlay"},
]


# ----------------------------------------------------------------------------
# Install, update, uninstall
# ----------------------------------------------------------------------------


def test_they_land_in_the_project_folder_a_folder_inside_it_included(library, tmp_path, nobody, no_network, capsys):
    root = tmp_path / "app"
    root.mkdir()

    assert _install(_lib(library, ONCE), "--project", root, "--dir", "modules/demo") == 0

    assert (root / "VERSION").read_text() == "VERSION_MAJOR = 1\n"
    assert (root / "CHANGELOG.md").is_file()
    assert (root / "socs" / "nrf54l15_cpuapp.overlay").is_file()
    assert not (root / "modules" / "demo" / "VERSION").exists()

    out = capsys.readouterr().out
    assert "created VERSION  yours from now on" in out
    assert "created socs/nrf54l15_cpuapp.overlay  yours from now on" in out
    assert _record(root)["demo"]["project_files"] == ["CHANGELOG.md", "VERSION", "socs/nrf54l15_cpuapp.overlay"]
    assert _record(root)["demo"]["once"] == []


def test_one_already_there_is_kept_as_it_is(library, tmp_path, nobody, no_network, capsys):
    root = tmp_path / "app"
    root.mkdir()
    (root / "VERSION").write_text("VERSION_MAJOR = 7\n")

    assert _install(_lib(library, ONCE), "--project", root, "--dir", "demo") == 0

    assert (root / "VERSION").read_text() == "VERSION_MAJOR = 7\n"
    assert "kept    VERSION  yours" in capsys.readouterr().out


def test_an_update_never_replaces_one_the_user_edited(library, tmp_path, nobody, no_network):
    root = tmp_path / "app"
    root.mkdir()
    source = _lib(library, ONCE)
    _install(source, "--project", root, "--dir", "demo")
    (root / "socs" / "nrf54l15_cpuapp.overlay").write_text("/* mine */\n")

    assert _install(source, "--project", root, "--dir", "demo") == 0

    assert (root / "socs" / "nrf54l15_cpuapp.overlay").read_text() == "/* mine */\n"


def test_one_the_new_version_drops_stays_and_leaves_the_record(library, tmp_path, nobody, no_network):
    root = tmp_path / "app"
    root.mkdir()
    _install(_lib(library, ONCE, root=tmp_path / "v1"), "--project", root, "--dir", "demo")

    _install(_lib(library, ONCE[:1], root=tmp_path / "v2"), "--project", root, "--dir", "demo")

    assert (root / "CHANGELOG.md").is_file()
    assert _record(root)["demo"]["project_files"] == ["VERSION"]


def test_an_uninstall_keeps_them_and_says_so(library, tmp_path, nobody, no_network, capsys):
    root = tmp_path / "app"
    root.mkdir()
    _install(_lib(library, ONCE), "--project", root, "--dir", "demo")
    capsys.readouterr()

    assert cli.main(["--uninstall", "demo", "--project", str(root)]) == 0

    assert (root / "VERSION").is_file()
    assert (root / "socs" / "nrf54l15_cpuapp.overlay").is_file()
    assert not (root / "demo").exists()
    assert "VERSION  yours, not removed" in capsys.readouterr().out


def test_a_c_file_among_them_is_not_built(library):
    loaded = manifest.load(_lib(library, [{"from": "port/port.c"}]))

    assert "port.c" not in loaded.build_sources


def test_a_manifest_from_before_keeps_them_in_the_library_folder(library, tmp_path, nobody, no_network):
    """seq 2.0.0 lists its configuration under once, and its header includes it from there."""
    root = tmp_path / "app"
    root.mkdir()

    assert _install(_lib(library, [{"from": "project/VERSION"}], requires={"installer": "1.1.0"}),
                    "--project", root, "--dir", "demo") == 0

    assert (root / "demo" / "VERSION").is_file()
    assert not (root / "VERSION").exists()


def test_any_installer_asked_for_2_0_0_means_the_new_place():
    """The family shares one version, so one key is enough, whichever installer reads it."""
    assert manifest.asks_for_modern({"requires": {"zephyr_installer": "2.0.0"}})
    assert manifest.asks_for_modern({"requires": {"pio_installer": "2.1.0"}})
    assert not manifest.asks_for_modern({"requires": {"zephyr_installer": "1.2.0"}})
    assert not manifest.asks_for_modern({"requires": {"libraries": ["osal"]}})
    assert not manifest.asks_for_modern({"requires": {"something": "2.0.0"}})
    assert not manifest.asks_for_modern({})


# ----------------------------------------------------------------------------
# What is refused, before anything is written
# ----------------------------------------------------------------------------


@pytest.mark.parametrize("to", ["../x", "C:/x", "/x", "..\\x", "a/../../x"])
def test_a_place_outside_the_project_is_refused(library, to):
    with pytest.raises(ManifestError):
        manifest.load(_lib(library, [{"from": "project/VERSION", "to": to}]))


def test_two_landing_in_one_place_are_refused(library):
    with pytest.raises(ManifestError, match="both land in VERSION"):
        manifest.load(_lib(library, [{"from": "project/VERSION"}, {"from": "project/CHANGELOG.md", "to": "VERSION"}]))


def test_the_record_is_never_one_of_them(library, tmp_path, nobody, no_network, capsys):
    root = tmp_path / "app"
    root.mkdir()

    code = _install(_lib(library, [{"from": "project/VERSION", "to": ".test-installer.json"}]),
                    "--project", root, "--dir", "demo")

    assert code == 2
    assert "edits or reads as the project's own" in capsys.readouterr().err
    assert not (root / "demo").exists()


def test_a_file_the_installer_manages_is_refused(library, tmp_path, nobody, no_network, monkeypatch, capsys):
    monkeypatch.setattr(target.current, "managed_files",
                        lambda project_root, lib: [".test-installer.json", "CMakeLists.txt", "*.ioc"])
    root = tmp_path / "app"
    root.mkdir()

    for to in ("CMakeLists.txt", "board/app.ioc"):
        assert _install(_lib(library, [{"from": "project/VERSION", "to": to}], root=tmp_path / to.replace("/", "_")),
                        "--project", root, "--dir", "demo") == 2

    assert "edits or reads as the project's own" in capsys.readouterr().err
    assert not (root / "CMakeLists.txt").exists()


def test_one_inside_the_library_folder_is_refused(library, tmp_path, nobody, no_network, capsys):
    root = tmp_path / "app"
    root.mkdir()

    code = _install(_lib(library, [{"from": "project/VERSION", "to": "demo/VERSION"}]),
                    "--project", root, "--dir", "demo")

    assert code == 2
    assert "inside its own folder" in capsys.readouterr().err
    assert not (root / "demo").exists()


def test_a_project_with_no_folder_of_its_own_refuses_them(library, tmp_path, nobody, no_network, monkeypatch, capsys):
    """Arduino's sketchbook: the libraries folder is shared by every sketch."""
    monkeypatch.setattr(target.current, "once_root", lambda project_root: None)
    monkeypatch.setattr(target.current, "no_once_root", "Install it into a sketch to get them.")
    root = tmp_path / "app"
    root.mkdir()

    assert _install(_lib(library, ONCE), "--project", root, "--dir", "demo") == 2

    assert "Install it into a sketch to get them." in capsys.readouterr().err
    assert not (root / "demo").exists()


def test_install_to_refuses_before_writing_a_thing(library, tmp_path):
    root = tmp_path / "app"
    root.mkdir()
    loaded = manifest.load(_lib(library, [{"from": "project/VERSION", "to": "demo/VERSION"}]))

    with pytest.raises(installer.InstallError):
        installer.install_to(loaded, root / "demo", project_root=root)

    assert not (root / "demo").exists()
