"""
Where a library's files come from: inside the library, and from the ref asked for.

A manifest arrives over the network before any of it is trusted, so no file it
names may be read from outside the library, however it is spelt. And a library
another needs can be pinned to a tag, a branch or a commit, or brought in with
an installer.yml the needing library carries for it.
"""

import json
import os

import pytest

from lib_installer.core import cli, download, installer, manifest
from lib_installer.core.manifest import Dependency, ManifestError


@pytest.fixture
def nobody(monkeypatch):
    monkeypatch.setattr(cli, "_answer", lambda prompt: None)


# ----------------------------------------------------------------------------
# Never a file from outside the library
# ----------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["../secret.h", "..\\secret.h", "/etc/passwd", "\\x.h", "C:/x.h", "inc/../../x.h"])
def test_a_source_outside_the_library_is_refused(library, path):
    root = library(once=[], extra={"files": {"headers": ["inc/demo.h"], "sources": [path]}})

    with pytest.raises(ManifestError, match="a file outside the library"):
        manifest.load(root)


@pytest.mark.parametrize("where", ["once", "extras", "option"])
def test_every_kind_of_source_is_checked(library, where):
    if where == "once":
        root = library(once=[{"from": "../x.h"}])
    elif where == "extras":
        root = library(once=[], extra={"extras": ["../NOTICE"]})
    else:
        root = library(once=[], options={"fs": {"description": "x", "files": {"sources": [{"from": "../fs.c", "to": "fs.c"}]}}})

    with pytest.raises(ManifestError, match="a file outside the library"):
        manifest.load(root)


def test_a_link_out_of_the_library_is_refused(library, tmp_path):
    root = library(once=[])
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "demo.c").write_text("/* not the library's */\n")
    (root / "src" / "demo.c").unlink()
    (root / "src").rmdir()

    # A link to the folder. Windows lets anyone make a junction, where a
    # symbolic link needs rights a user may not have.
    try:
        os.symlink(outside, root / "src", target_is_directory=True)
    except (OSError, NotImplementedError):
        try:
            import _winapi

            _winapi.CreateJunction(str(outside), str(root / "src"))
        except (ImportError, OSError):
            pytest.skip("this system makes no links of any kind for this user")

    with pytest.raises(ManifestError, match="leads outside the library"):
        manifest.load(root)


# ----------------------------------------------------------------------------
# A library another needs, at a ref, or with a carried installer.yml
# ----------------------------------------------------------------------------


def test_a_dependency_reads_its_owner_ref_and_oldest_version():
    found = Dependency("someone/osal@v1.2.0 >= 1.2.0")

    assert (found.source, found.ref, found.name, found.minimum) == ("someone/osal", "v1.2.0", "osal", (1, 2, 0))
    assert found.fetch == "someone/osal@v1.2.0"
    assert str(found) == "osal@v1.2.0 >= 1.2.0"


def test_a_dependency_without_a_ref_is_the_default_branch():
    found = Dependency("osal >= 1.1.0")

    assert found.ref is None
    assert found.fetch == "osal"


def test_a_branch_with_a_slash_is_one_ref():
    assert Dependency("someone/lib@feature/x").ref == "feature/x"


@pytest.mark.parametrize("text", ["osal@", "osal@../x", "osal >= 1.2", "a/b/c", "osal@v1 junk"])
def test_a_dependency_that_says_nothing_usable_is_refused(text):
    with pytest.raises(ManifestError):
        Dependency(text)


def test_the_mapping_form_carries_an_installer_yml():
    found = Dependency({"source": "littlefs-project/littlefs@v2.9.3", "manifest": "manifests/littlefs.yml",
                        "minimum": "2.9.0"})

    assert (found.source, found.ref, found.name) == ("littlefs-project/littlefs", "v2.9.3", "littlefs")
    assert found.manifest.as_posix() == "manifests/littlefs.yml"
    assert found.minimum == (2, 9, 0)


def test_a_carried_installer_yml_from_outside_the_library_is_refused():
    with pytest.raises(ManifestError, match="a file outside the library"):
        Dependency({"source": "x/y", "manifest": "../y.yml"})


def test_a_carried_installer_yml_must_be_in_the_library(library):
    root = library(once=[], requires={"libraries": [{"source": "x/y", "manifest": "manifests/y.yml"}]})

    with pytest.raises(ManifestError, match="do not exist"):
        manifest.load(root)


def test_the_ref_and_the_carried_manifest_reach_the_fetch(library, project, tmp_path, monkeypatch, nobody):
    carried = (
        "name: littlefs\nversion: 2.9.3\nfiles:\n  headers:\n    - lfs.h\n  sources:\n    - lfs.c\n"
    )
    needer = library(
        name="spif", headers=("spif.h",), sources=("spif.c",), once=[],
        requires={"libraries": [{"source": "littlefs-project/littlefs@v2.9.3",
                                 "manifest": "manifests/littlefs.yml"}]},
        extra_files={"manifests/littlefs.yml": carried},
    )
    asked = []

    def fake_fetch(source, ref=None, destination=None, carried=None):
        asked.append((source, carried))
        root = tmp_path / "fetched" / "littlefs"
        root.mkdir(parents=True, exist_ok=True)
        (root / "installer.yml").write_bytes(carried)
        (root / "lfs.h").write_text("/* lfs */\n")
        (root / "lfs.c").write_text("/* lfs */\n")
        download._ORIGINS[download._key(root)] = {
            "kind": "github", "source": "littlefs-project/littlefs", "ref": "v2.9.3",
            "commit": "a" * 40, "manifest": "carried",
        }
        return root

    monkeypatch.setattr(download, "fetch", fake_fetch)
    monkeypatch.setattr(download, "cleanup", lambda path: None)
    root = project(cmake=True)

    assert cli.main([str(needer), "--project", str(root), "--dir", "Libs/spif"]) == 0

    assert asked == [("littlefs-project/littlefs@v2.9.3", (needer / "manifests" / "littlefs.yml").read_bytes())]
    record = json.loads((root / ".test-installer.json").read_text())["libraries"]
    assert record["littlefs"]["origin"]["commit"] == "a" * 40
    assert record["littlefs"]["origin"]["ref"] == "v2.9.3"
    assert record["spif"]["origin"]["kind"] == "folder"
    assert json.loads((root / ".test-installer.json").read_text())["record"] == installer.RECORD_VERSION


def test_a_folder_source_is_recorded_as_a_folder(library, project, nobody, monkeypatch):
    monkeypatch.setattr(download, "fetch", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    root = project(cmake=True)
    source = library(once=[])

    assert cli.main([str(source), "--project", str(root), "--dir", "demo"]) == 0

    origin = json.loads((root / ".test-installer.json").read_text())["libraries"]["demo"]["origin"]
    assert origin == {"kind": "folder", "path": source.resolve().as_posix()}


def test_a_ref_with_a_slash_after_an_at_is_a_name_not_a_path():
    assert not cli._looks_like_path("someone/lib@feature/x")
    assert cli._looks_like_path("D:/Downloads/x")
    assert cli._looks_like_path("a/b/c")
