"""
A manifest written for 2.1.0: every path naming a place in the project starts
at the project's folder, and {library} names the folder the library is in.

In a list of files a to is another place where the list puts its files, the
library's folder or, for once, the project's, and an extra's root is a place
in the project's. An extra with a root lands in the project's folder as the
library's own, such as its tools, written again on every install and taken out
by an uninstall. A run step's script is found from the project's folder, where
such an extra put it, or in the library's folder with {library}. A manifest
from before keeps the meaning it was written for.
"""

import json
from pathlib import Path

import pytest
import yaml

from lib_installer.core import cli, download, installer, manifest, steps
from lib_installer.core.manifest import ManifestError

ROOTED = {"installer": "2.1.0"}

# Writes where it ran from and where it is, so a test can tell both.
SCRIPT = (
    "import os, sys\n"
    "from pathlib import Path\n"
    "Path('ran.txt').write_text(os.getcwd() + '\\n' + str(Path(__file__).resolve()) + '\\n' + ' '.join(sys.argv[1:]))\n"
)


@pytest.fixture
def nobody(monkeypatch):
    monkeypatch.setattr(cli, "_answer", lambda prompt: None)


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("tried to use the network")

    monkeypatch.setattr(download, "fetch", refuse)


def _lib(library, extras=None, run=None, requires=ROOTED, files=None):
    extra = {}

    if extras is not None:
        extra["extras"] = extras

    if run is not None:
        extra["run"] = run

    written = {
        "tools/keygen.py": SCRIPT,
        "tools/keygen.md": "# keygen\n",
        "LICENSE.md": "licence\n",
    }
    written.update(files or {})

    return library(once=[], requires=requires, extra_files=written, extra=extra)


def _install(*args):
    return cli.main([str(arg) for arg in args])


def _record(root):
    return json.loads((root / ".test-installer.json").read_text(encoding="utf-8"))["libraries"]


@pytest.fixture
def app(tmp_path):
    root = tmp_path / "app"
    root.mkdir()

    return root


TOOLS = [{"from": "tools", "root": "tools"}]


# ----------------------------------------------------------------------------
# Extras with a root
# ----------------------------------------------------------------------------


def test_a_folder_lands_in_the_project_folder(library, app, nobody, no_network, capsys):
    assert _install(_lib(library, TOOLS), "--project", app, "--dir", "modules/demo") == 0

    assert (app / "tools" / "keygen.py").read_text() == SCRIPT
    assert (app / "tools" / "keygen.md").is_file()
    assert not (app / "modules" / "demo" / "tools").exists()
    assert _record(app)["demo"]["placed"] == ["tools/keygen.md", "tools/keygen.py"]
    assert "written tools/keygen.py" in capsys.readouterr().out


def test_a_file_lands_at_root_and_a_wildcard_keeps_the_names(library, app, nobody, no_network):
    extras = [{"from": "tools/keygen.md", "root": "doc/keys.md"}, {"from": "tools/*.py", "root": "scripts"}]

    assert _install(_lib(library, extras), "--project", app, "--dir", "demo") == 0

    assert (app / "doc" / "keys.md").read_text() == "# keygen\n"
    assert (app / "scripts" / "keygen.py").is_file()


def test_an_update_writes_them_again(library, app, nobody, no_network):
    _install(_lib(library, TOOLS), "--project", app, "--dir", "demo")
    (app / "tools" / "keygen.md").write_text("changed by hand\n")

    _install(_lib(library, TOOLS, files={"tools/keygen.md": "# keygen, new\n"}), "--project", app, "--dir", "demo")

    assert (app / "tools" / "keygen.md").read_text() == "# keygen, new\n"


def test_one_the_new_version_drops_is_removed(library, app, nobody, no_network, capsys):
    lib = _lib(library, TOOLS, files={"tools/old.py": "# old\n"})
    _install(lib, "--project", app, "--dir", "demo")
    assert (app / "tools" / "old.py").is_file()

    (lib / "tools" / "old.py").unlink()
    capsys.readouterr()
    _install(lib, "--project", app, "--dir", "demo")

    assert not (app / "tools" / "old.py").exists()
    assert (app / "tools" / "keygen.py").is_file()
    assert "removed" in capsys.readouterr().out
    assert "tools/old.py" not in _record(app)["demo"]["placed"]


def test_an_uninstall_takes_them_out(library, app, nobody, no_network):
    _install(_lib(library, TOOLS), "--project", app, "--dir", "demo")

    installer.uninstall(app, "demo")

    assert not (app / "tools").exists()


def test_a_file_of_the_users_is_never_written_over(library, app, nobody, no_network, capsys):
    (app / "tools").mkdir()
    (app / "tools" / "keygen.py").write_text("# the user's own\n")

    assert _install(_lib(library, TOOLS), "--project", app, "--dir", "demo") != 0

    assert (app / "tools" / "keygen.py").read_text() == "# the user's own\n"
    said = capsys.readouterr()
    assert "a file of yours already is" in said.out + said.err
    assert not (app / "demo").exists(), "nothing was installed"


def test_the_same_file_already_there_is_taken_over(library, app, nobody, no_network):
    (app / "tools").mkdir()
    (app / "tools" / "keygen.py").write_text(SCRIPT)

    assert _install(_lib(library, TOOLS), "--project", app, "--dir", "demo") == 0
    assert "tools/keygen.py" in _record(app)["demo"]["placed"]


def test_a_manifest_from_before_cannot_have_one(library):
    with pytest.raises(ManifestError, match="new in 2.1.0"):
        manifest.load(_lib(library, TOOLS, requires={"installer": "2.0.0"}))


@pytest.mark.parametrize("root", ["../tools", "C:/tools", "/tools", "{library}/tools"])
def test_a_root_outside_the_project_or_in_the_library_is_refused(library, root):
    with pytest.raises(ManifestError):
        manifest.load(_lib(library, [{"from": "tools", "root": root}]))


def test_two_landing_in_one_place_are_refused(library):
    extras = [{"from": "tools/keygen.md", "root": "x.md"}, {"from": "LICENSE.md", "root": "x.md"}]

    with pytest.raises(ManifestError, match="both land"):
        manifest.load(_lib(library, extras))


# ----------------------------------------------------------------------------
# Run steps
# ----------------------------------------------------------------------------


def _step(script, **more):
    return [dict({"label": "make", "script": script}, **more)]


def test_a_script_is_found_from_the_project_folder(library, app, nobody, no_network, capsys):
    lib = _lib(library, TOOLS, run=_step("tools/keygen.py"))

    assert _install(lib, "--project", app, "--dir", "modules/demo", "--run", "make") == 0

    cwd, where, _ = (app / "ran.txt").read_text().split("\n")
    assert where == str((app / "tools" / "keygen.py").resolve())
    assert Path(cwd).resolve() == app.resolve()
    assert "python tools/keygen.py" in capsys.readouterr().out


def test_library_names_the_folder_it_was_installed_in(library, app, nobody, no_network, capsys):
    lib = _lib(library, ["tools"], run=_step("{library}/tools/keygen.py", args=["{library}/out"]))

    assert _install(lib, "--project", app, "--dir", "modules/demo", "--run", "make") == 0

    _, where, args = (app / "ran.txt").read_text().split("\n")
    assert where == str((app / "modules" / "demo" / "tools" / "keygen.py").resolve())
    assert args == "modules/demo/out"
    assert "python modules/demo/tools/keygen.py modules/demo/out" in capsys.readouterr().out


def test_unless_may_name_the_library_folder(library, app, nobody, no_network, capsys):
    lib = _lib(library, ["tools"], run=_step("{library}/tools/keygen.py", unless="{library}/tools/keygen.md"))

    assert _install(lib, "--project", app, "--dir", "demo", "--run", "make") == 0

    assert not (app / "ran.txt").exists()
    assert "skipped" in capsys.readouterr().out


def test_a_script_nothing_puts_in_place_is_refused(library):
    with pytest.raises(ManifestError, match="would not be there to run"):
        manifest.load(_lib(library, ["LICENSE.md"], run=_step("tools/keygen.py")))


def test_a_script_in_the_library_folder_needs_library(library):
    with pytest.raises(ManifestError, match="would not be there to run"):
        manifest.load(_lib(library, TOOLS, run=_step("{library}/tools/keygen.py")))


def test_before_2_1_0_a_script_is_found_in_the_library_as_fetched(library, app):
    lib = _lib(library, ["LICENSE.md"], run=_step("tools/keygen.py"), requires={"installer": "2.0.0"})
    loaded = manifest.load(lib)
    step = loaded.run[0]

    assert steps.script_path(loaded, step, app, app / "demo") == loaded.root / "tools" / "keygen.py"
    assert not step.rooted


# ----------------------------------------------------------------------------
# What is fetched from GitHub
# ----------------------------------------------------------------------------


def test_a_rooted_script_is_not_fetched_on_its_own():
    data = {
        "name": "demo",
        "requires": ROOTED,
        "files": {"headers": ["demo.h"]},
        "extras": [{"root": "tools"}],
        "run": [{"label": "make", "script": "tools/keygen.py"}],
    }

    assert download._listed_entries(data) == ["demo.h", "tools"]



# ----------------------------------------------------------------------------
# Every file keeps its path, and headers and sources need no files around them
# ----------------------------------------------------------------------------


def _rewrite(root, change):
    """Edit the installer.yml at root: change takes the parsed data and returns it."""
    path = root / "installer.yml"
    path.write_text(yaml.safe_dump(change(yaml.safe_load(path.read_text())), sort_keys=False), encoding="utf-8")

    return root


def test_the_code_keeps_its_path_with_no_layout_given(library, app, nobody, no_network):
    lib = _lib(library)

    assert _install(lib, "--project", app, "--dir", "demo") == 0

    assert (app / "demo" / "inc" / "demo.h").is_file()
    assert (app / "demo" / "src" / "demo.c").is_file()
    assert manifest.load(lib).include_dirs == ["inc"]


def test_layout_flat_is_refused_and_mirror_says_nothing_new(library):
    def layout(name):
        return lambda data: dict(data, install={"layout": name})

    with pytest.raises(ManifestError, match="leave install.layout out"):
        manifest.load(_rewrite(_lib(library), layout("flat")))

    assert manifest.load(_rewrite(_lib(library), layout("mirror"))).layout == "mirror"


def test_before_2_1_0_flat_is_still_the_default(library):
    loaded = manifest.load(_lib(library, requires={"installer": "2.0.0"}))

    assert [entry.destination for entry in loaded.code_files] == ["demo.h", "demo.c"]


def test_a_once_file_with_no_to_lands_at_its_own_path(library, app, nobody, no_network):
    lib = library(once=[{"from": "boards/chip.overlay"}], requires=ROOTED, extra_files={"boards/chip.overlay": "/ { };\n"})

    assert _install(lib, "--project", app, "--dir", "demo") == 0

    assert (app / "boards" / "chip.overlay").is_file()
    assert not (app / "chip.overlay").exists()


def test_headers_and_sources_need_no_files_around_them(library, app, nobody, no_network):
    def loose(data):
        files = data.pop("files")
        data["headers"], data["sources"] = files["headers"], files["sources"]
        return data

    lib = _rewrite(_lib(library), loose)

    assert _install(lib, "--project", app, "--dir", "demo") == 0
    assert (app / "demo" / "src" / "demo.c").is_file()


def test_an_options_headers_and_sources_need_no_files_either(library):
    def option(data):
        data["options"] = {"extra": {"description": "More", "sources": ["src/more.c"]}}
        return data

    lib = _lib(library, files={"src/more.c": "/* more */\n"})
    loaded = manifest.load(_rewrite(lib, option))

    assert [entry.destination for entry in loaded.options["extra"].sources] == ["src/more.c"]


def test_both_files_and_headers_at_once_are_refused(library):
    with pytest.raises(ManifestError, match="both files and headers"):
        manifest.load(_rewrite(_lib(library), lambda data: dict(data, headers=["inc/demo.h"])))


def test_before_2_1_0_headers_on_their_own_are_refused(library):
    def loose(data):
        data.pop("files")
        data["headers"] = ["inc/demo.h"]
        return data

    with pytest.raises(ManifestError, match="new in 2.1.0"):
        manifest.load(_rewrite(_lib(library, requires={"installer": "2.0.0"}), loose))


def test_headers_on_their_own_are_fetched_from_github():
    data = {"name": "demo", "requires": ROOTED, "headers": ["inc/demo.h"], "sources": ["src/*.c"]}

    assert download._listed_entries(data)[:2] == ["inc/demo.h", "src/*.c"]


# ----------------------------------------------------------------------------
# A wildcard means the same in a checkout and in GitHub's listing
# ----------------------------------------------------------------------------

TREE = ["top.c", "top.h", "src/a.c", "src/b.h", "src/ble/c.c", "src/ble/deep/d.c", "test/t.c"]


@pytest.mark.parametrize("pattern, wanted", [
    ("*.c", ["top.c"]),
    ("src/*.c", ["src/a.c"]),
    ("src/**/*.c", ["src/a.c", "src/ble/c.c", "src/ble/deep/d.c"]),
    ("**/*.c", ["src/a.c", "src/ble/c.c", "src/ble/deep/d.c", "test/t.c", "top.c"]),
    ("src/**", ["src/a.c", "src/b.h", "src/ble/c.c", "src/ble/deep/d.c"]),
    ("src/?.[ch]", ["src/a.c", "src/b.h"]),
    ("src/[!a].h", ["src/b.h"]),
])
def test_a_wildcard_matches_alike_on_disk_and_in_the_listing(tmp_path, pattern, wanted):
    for relative in TREE:
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relative).write_text("x")

    on_disk = [p.as_posix() for p in manifest.expand(tmp_path, pattern)]
    listed = [p.as_posix() for p in manifest.expand(None, pattern, TREE)]

    assert on_disk == listed == sorted(wanted)


# ----------------------------------------------------------------------------
# Two files of the code that would land in one place
# ----------------------------------------------------------------------------


def test_two_files_of_one_name_flattened_into_one_place_are_refused(library):
    lib = library(sources=("src/ble/util.c", "src/dfu/util.c"), once=[], requires={"installer": "2.0.0"})

    with pytest.raises(ManifestError, match="land at util.c"):
        manifest.load(lib)


def test_kept_paths_keep_them_apart(library):
    lib = library(sources=("src/ble/util.c", "src/dfu/util.c"), once=[], requires=ROOTED)

    assert [e.destination for e in manifest.load(lib).sources] == ["src/ble/util.c", "src/dfu/util.c"]


def test_one_file_listed_twice_is_no_clash(library):
    lib = library(sources=("src/demo.c", "src/*.c"), once=[], requires={"installer": "2.0.0"},
                  extra_files={"src/demo.c": "/* c */\n"})

    assert manifest.load(lib).sources


# ----------------------------------------------------------------------------
# A from that is the same as its to can be left out
# ----------------------------------------------------------------------------


def test_an_extra_needs_no_from_when_it_is_its_root(library, app, nobody, no_network):
    assert _install(_lib(library, [{"root": "tools"}]), "--project", app, "--dir", "demo") == 0

    assert (app / "tools" / "keygen.py").is_file()
    assert _record(app)["demo"]["placed"] == ["tools/keygen.md", "tools/keygen.py"]


def test_a_once_file_needs_no_from_either(library, app, nobody, no_network):
    lib = library(once=[{"to": "boards/chip.overlay"}], requires=ROOTED, extra_files={"boards/chip.overlay": "/ { };\n"})

    assert _install(lib, "--project", app, "--dir", "demo") == 0
    assert (app / "boards" / "chip.overlay").is_file()


def test_a_header_needs_no_from_either(library):
    lib = library(headers=({"to": "inc/demo.h"},), once=[], requires=ROOTED, extra_files={"inc/demo.h": "/* h */\n"})

    assert [(e.source.as_posix(), e.destination) for e in manifest.load(lib).headers] == [("inc/demo.h", "inc/demo.h")]


@pytest.mark.parametrize("key", ["to", "root"])
def test_a_place_that_is_a_wildcard_is_refused(library, key):
    with pytest.raises(ManifestError, match="never a wildcard"):
        manifest.load(_lib(library, [{key: "tools/*.py"}]))


def test_before_2_1_0_a_once_file_needs_its_from(library):
    lib = library(once=[{"to": "x.overlay"}], requires={"installer": "2.0.0"}, extra_files={"x.overlay": "/ { };\n"})

    with pytest.raises(ManifestError, match="Each entry is a mapping with a from"):
        manifest.load(lib)


def test_a_to_or_a_root_alone_is_fetched_from_github():
    data = {"name": "demo", "requires": ROOTED, "headers": ["inc/demo.h"], "extras": [{"root": "tools"}, {"to": "doc"}],
            "once": [{"to": "boards/chip.overlay"}, "VERSION"]}

    entries = download._listed_entries(data)

    assert {"tools", "doc", "boards/chip.overlay", "VERSION"} <= set(entries)


# ----------------------------------------------------------------------------
# Where a to and a root put a file
# ----------------------------------------------------------------------------


def test_an_extras_to_is_a_place_in_the_library_folder(library, app, nobody, no_network):
    extras = [{"from": "tools/keygen.md", "to": "doc/keys.md"}, {"to": "tools"}]

    assert _install(_lib(library, extras), "--project", app, "--dir", "demo") == 0

    assert (app / "demo" / "doc" / "keys.md").read_text() == "# keygen\n"
    assert (app / "demo" / "tools" / "keygen.py").is_file()
    assert not (app / "doc").exists() and not (app / "tools").exists()
    assert _record(app)["demo"]["placed"] == []


def test_an_extra_with_both_a_to_and_a_root_is_refused(library):
    with pytest.raises(ManifestError, match="both a to and a root"):
        manifest.load(_lib(library, [{"from": "tools", "to": "tools", "root": "tools"}]))


def test_a_to_is_never_written_with_library(library):
    with pytest.raises(ManifestError, match=r"leave \{library\} out"):
        manifest.load(_lib(library, [{"from": "tools", "to": "{library}/tools"}]))


def test_an_extras_to_cannot_land_on_the_code(library):
    with pytest.raises(ManifestError, match="land at src/demo.c in the library's folder"):
        manifest.load(_lib(library, [{"from": "LICENSE.md", "to": "src/demo.c"}]))


def test_code_has_no_root(library):
    lib = library(headers=({"from": "inc/demo.h", "root": "inc/demo.h"},), once=[], requires=ROOTED)

    with pytest.raises(ManifestError, match="Code is built in the library's folder"):
        manifest.load(lib)


def test_a_once_file_may_be_its_path_alone(library, app, nobody, no_network):
    lib = library(once=["boards/chip.overlay"], requires=ROOTED, extra_files={"boards/chip.overlay": "/ { };\n"})

    assert _install(lib, "--project", app, "--dir", "demo") == 0
    assert (app / "boards" / "chip.overlay").is_file()


def test_a_once_files_to_is_its_place_in_the_project(library, app, nobody, no_network):
    lib = library(once=[{"from": "templates/CHANGELOG.md", "to": "CHANGELOG.md"}], requires=ROOTED,
                  extra_files={"templates/CHANGELOG.md": "# Changelog\n"})

    assert _install(lib, "--project", app, "--dir", "demo") == 0

    assert (app / "CHANGELOG.md").read_text() == "# Changelog\n"
    assert not (app / "templates").exists()
    assert not (app / "demo" / "CHANGELOG.md").exists()


@pytest.mark.parametrize("requires", [ROOTED, {"installer": "2.0.0"}])
def test_a_once_file_has_no_root(library, requires):
    lib = library(once=[{"from": "x.overlay", "root": "boards/x.overlay"}], requires=requires,
                  extra_files={"x.overlay": "/ { };\n"})

    with pytest.raises(ManifestError, match="A root is for an extra"):
        manifest.load(lib)


def test_a_once_files_to_never_names_the_library_folder(library):
    lib = library(once=[{"from": "x.overlay", "to": "{library}/x.overlay"}], requires=ROOTED,
                  extra_files={"x.overlay": "/ { };\n"})

    with pytest.raises(ManifestError, match="never the library's"):
        manifest.load(lib)
