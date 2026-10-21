"""
Run steps: what a library runs once its files are in, such as making a key.

It runs on the user's own computer, so it is always asked about first, unless
the user said so beforehand with --run or --yes. A step whose file is already
there is skipped without a question, and one that ran before is not run again
by an update.
"""

import json
import sys

import pytest

from lib_installer.core import cli, download, manifest
from lib_installer.core.manifest import ManifestError

MAKE = (
    "import os, sys\n"
    "with open(sys.argv[1], 'w') as f:\n"
    "    f.write(os.environ['INSTALLER_NAME'] + ' ' + os.environ['INSTALLER'])\n"
)

KEY = {"label": "key", "description": "Make a key", "script": "scripts/make_key.py",
       "args": ["sign_key.pem"], "unless": "sign_key.pem"}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("tried to use the network")

    monkeypatch.setattr(download, "fetch", refuse)


@pytest.fixture
def answers(monkeypatch):
    """What each question is answered: a list, taken in turn, None for nobody."""
    given = []
    asked = []

    def answer(prompt):
        asked.append(prompt)
        return given.pop(0) if given else None

    monkeypatch.setattr(cli, "_answer", answer)

    return given, asked


def _lib(library, steps, **kwargs):
    files = {"scripts/make_key.py": MAKE, "scripts/fail.py": "import sys\nsys.exit(3)\n"}
    files.update(kwargs.pop("extra_files", {}))

    return library(once=[], extra={"run": steps}, extra_files=files, **kwargs)


def _app(tmp_path):
    root = tmp_path / "app"
    root.mkdir(exist_ok=True)

    return root


def _install(source, root, *more):
    return cli.main([str(source), "--project", str(root), "--dir", "demo", *more])


def _ran(root):
    return json.loads((root / ".test-installer.json").read_text())["libraries"]["demo"].get("ran")


def test_a_step_answered_yes_runs_in_the_project_folder(library, tmp_path, answers):
    given, asked = answers
    given += ["y"]
    root = _app(tmp_path)
    source = _lib(library, [KEY])

    assert _install(source, root) == 0

    assert (root / "sign_key.pem").read_text() == "demo test-installer"
    assert any("Run it?" in prompt for prompt in asked)
    assert _ran(root) == {"key": manifest.load(source).run[0].fingerprint()}


def test_the_command_is_shown_before_the_question(library, tmp_path, answers, capsys):
    answers[0].append("n")

    _install(_lib(library, [KEY]), _app(tmp_path))

    out = capsys.readouterr().out
    assert "scripts/make_key.py sign_key.pem" in out
    assert "not run, as answered" in out


def test_its_file_already_there_skips_it_without_a_question(library, tmp_path, answers, capsys):
    root = _app(tmp_path)
    (root / "sign_key.pem").write_text("mine")

    assert _install(_lib(library, [KEY]), root) == 0

    assert (root / "sign_key.pem").read_text() == "mine"
    assert not any("Run it?" in prompt for prompt in answers[1])
    assert "skipped, sign_key.pem is already there" in capsys.readouterr().out


def test_with_nobody_to_ask_it_is_not_run_and_says_how(library, tmp_path, answers, capsys):
    root = _app(tmp_path)

    assert _install(_lib(library, [KEY]), root) == 0

    assert not (root / "sign_key.pem").exists()
    assert "Run it with --run key" in capsys.readouterr().out


def test_run_given_runs_it_without_a_question(library, tmp_path, answers):
    root = _app(tmp_path)

    assert _install(_lib(library, [KEY]), root, "--run", "key") == 0

    assert (root / "sign_key.pem").is_file()
    assert not any("Run it?" in prompt for prompt in answers[1])


def test_yes_runs_every_step(library, tmp_path, monkeypatch):
    root = _app(tmp_path)
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False, raising=False)

    assert _install(_lib(library, [KEY]), root, "--yes") == 0

    assert (root / "sign_key.pem").is_file()


def test_no_run_skips_it(library, tmp_path, answers, capsys):
    root = _app(tmp_path)

    assert _install(_lib(library, [KEY]), root, "--no-run", "key") == 0

    assert not (root / "sign_key.pem").exists()
    assert "skipped, as asked with --no-run key" in capsys.readouterr().out


def test_an_unknown_step_is_refused_before_anything_goes_in(library, tmp_path, answers, capsys):
    root = _app(tmp_path)

    assert _install(_lib(library, [KEY]), root, "--run", "kye") == 2

    assert "No run step called kye" in capsys.readouterr().err
    assert not (root / "demo").exists()


def test_one_step_given_both_ways_is_refused(library, tmp_path, answers, capsys):
    assert _install(_lib(library, [KEY]), _app(tmp_path), "--run", "key", "--no-run", "key") == 2


def test_a_step_that_fails_leaves_the_library_in_and_says_so(library, tmp_path, answers, capsys):
    root = _app(tmp_path)
    step = {"label": "bad", "script": "scripts/fail.py"}

    assert _install(_lib(library, [step]), root, "--run", "bad") == 1

    assert (root / "demo" / "demo.h").is_file()
    out = capsys.readouterr().out
    assert "failed, it ended with code 3" in out
    assert "bad did not finish" in out
    assert _ran(root) == {}


def test_a_command_that_is_not_installed_says_so(library, tmp_path, answers, capsys):
    step = {"label": "tool", "command": ["surely-no-such-program-here", "--x"]}

    assert _install(_lib(library, [step]), _app(tmp_path), "--run", "tool") == 1

    assert "surely-no-such-program-here is not installed, or not on the PATH" in capsys.readouterr().out


def test_a_command_runs_as_it_is_with_no_shell(library, tmp_path, answers):
    root = _app(tmp_path)
    step = {"label": "py", "command": [sys.executable, "-c", "open('made.txt', 'w').write('x; echo no')"]}

    assert _install(_lib(library, [step]), root, "--run", "py") == 0

    assert (root / "made.txt").read_text() == "x; echo no"


def test_an_update_does_not_run_a_step_that_ran_before(library, tmp_path, answers, capsys):
    root = _app(tmp_path)
    step = {"label": "once", "command": [sys.executable, "-c", "open('count.txt', 'a').write('1')"]}
    source = _lib(library, [step])

    _install(source, root, "--run", "once")
    capsys.readouterr()
    _install(source, root)

    assert (root / "count.txt").read_text() == "1"
    assert "ran before. Run it again with --run once" in capsys.readouterr().out

    _install(source, root, "--run", "once")

    assert (root / "count.txt").read_text() == "11"


def test_a_changed_step_is_asked_about_again(library, tmp_path, answers):
    root = _app(tmp_path)
    first = {"label": "s", "command": [sys.executable, "-c", "open('a.txt', 'w').write('1')"]}
    second = {"label": "s", "command": [sys.executable, "-c", "open('b.txt', 'w').write('2')"]}

    _install(_lib(library, [first], root=tmp_path / "v1"), root, "--run", "s")
    _install(_lib(library, [second], root=tmp_path / "v2"), root, "--run", "s")

    assert (root / "b.txt").is_file()


def test_a_project_with_no_folder_of_its_own_leaves_steps_unrun(library, tmp_path, answers, monkeypatch, capsys):
    from lib_installer.core import target

    monkeypatch.setattr(target.current, "once_root", lambda project_root: None)
    monkeypatch.setattr(target.current, "no_once_root", "Install it into a sketch to run them.")
    root = _app(tmp_path)

    assert _install(_lib(library, [KEY]), root, "--yes") == 0

    out = capsys.readouterr().out
    assert "key          not run, there is no project folder here to run it in" in out
    assert "Install it into a sketch to run them." in out
    assert (root / "demo").is_dir()
    assert not list(root.rglob("sign_key.pem"))
    assert not json.loads((root / ".test-installer.json").read_text())["libraries"]["demo"].get("ran")


# ----------------------------------------------------------------------------
# What a manifest may say about a step
# ----------------------------------------------------------------------------


@pytest.mark.parametrize("step, says", [
    ({"label": "Key", "script": "scripts/make_key.py"}, "Label a step"),
    ({"label": "k"}, "a script or a command"),
    ({"label": "k", "script": "scripts/make_key.py", "command": ["x"]}, "only one of them"),
    ({"label": "k", "script": "scripts/make_key.sh"}, "A script is Python"),
    ({"label": "k", "command": "imgtool keygen"}, "should be a list"),
    ({"label": "k", "command": []}, "should be a list"),
    ({"label": "k", "script": "../evil.py"}, "a file outside the library"),
    ({"label": "k", "script": "scripts/make_key.py", "unless": "../x.pem"}, "outside the project"),
    ({"label": "k", "script": "scripts/make_key.py", "args": "x"}, "list of words"),
    ("make it", "Each step is a mapping"),
])
def test_a_step_that_cannot_be_run_safely_is_refused(library, step, says):
    with pytest.raises(ManifestError, match=says):
        manifest.load(_lib(library, [step]))


def test_two_steps_with_one_label_are_refused(library):
    with pytest.raises(ManifestError, match="two steps labelled key"):
        manifest.load(_lib(library, [KEY, dict(KEY)]))


def test_a_script_that_is_not_in_the_library_is_refused(library):
    with pytest.raises(ManifestError, match="do not exist"):
        manifest.load(_lib(library, [{"label": "k", "script": "scripts/missing.py"}]))


def test_the_script_is_fetched_with_the_library():
    data = {"files": {}, "run": [{"label": "k", "script": "scripts/make_key.py"}]}

    assert "scripts/make_key.py" in download._listed_entries(data)


def test_yes_takes_the_folder_offered_and_says_so(library, tmp_path, monkeypatch, capsys):
    root = _app(tmp_path)

    assert cli.main([str(_lib(library, [KEY])), "--project", str(root), "--yes"]) == 0

    assert (root / "demo" / "demo.h").is_file()
    assert "Folder to install demo into [demo]: (--yes)" in capsys.readouterr().out
