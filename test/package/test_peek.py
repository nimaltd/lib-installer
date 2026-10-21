"""
The library's installer.yml, read for its platform before anything else: from
GitHub, with nothing asked twice, and from a zip, without unpacking it.
"""

import io
import json
import urllib.error
import zipfile

from conftest import run
from lib_installer.core import download

SHA = "a" * 40

MANIFEST = b"""name: demo
platform: zephyr
files:
  headers:
    - src/demo.h
  sources:
    - src/demo.c
"""


def _github(monkeypatch, files, repo="demo"):
    """A GitHub of one repository of someone's, holding files, that counts what it is asked."""
    asked = []
    served = {download.COMMIT_URL.format(owner="someone", repo=repo, ref="HEAD"): SHA.encode()}
    served.update({download.RAW_URL.format(owner="someone", repo=repo, ref=SHA, path=path): data
                   for path, data in files.items()})

    def answer(url, token=None, accept=None, timeout=None):
        asked.append(url)

        if url not in served:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

        return io.BytesIO(served[url])

    monkeypatch.setattr(download, "_open", answer)

    return asked


def test_the_manifest_on_github_is_asked_for_once(project, monkeypatch):
    root = project("zephyr")
    asked = _github(monkeypatch, {"installer.yml": MANIFEST, "src/demo.h": b"int demo(void);\n",
                                  "src/demo.c": b"int demo(void) { return 1; }\n"})

    assert run("someone/demo", "--project", root) == 0

    assert json.loads((root / ".lib-installer.json").read_text(encoding="utf-8"))["platform"] == "zephyr"
    assert len(asked) == len(set(asked))
    assert sum(url.endswith("/installer.yml") for url in asked) == 1
    assert sum("/commits/" in url for url in asked) == 1
    # Kept for the one run, and no longer.
    assert download._RUN is None


def test_a_manifest_on_github_naming_no_platform_stops_before_any_file(project, monkeypatch, capsys):
    root = project("zephyr")
    asked = _github(monkeypatch, {"installer.yml": MANIFEST.replace(b"platform: zephyr\n", b""),
                                  "src/demo.h": b"int demo(void);\n", "src/demo.c": b"int demo(void);\n"})

    assert run("someone/demo", "--project", root) == 2

    assert "names no platform" in capsys.readouterr().err
    assert not any(url.endswith(("/demo.h", "/demo.c")) for url in asked)


def test_a_library_needed_that_is_for_another_platform_is_refused(library, project, monkeypatch, capsys):
    root = project("zephyr")
    dep = MANIFEST.replace(b"name: demo", b"name: dep").replace(b"platform: zephyr", b"platform: stm32")
    _github(monkeypatch, {"installer.yml": dep, "src/demo.h": b"int demo(void);\n",
                          "src/demo.c": b"int demo(void);\n"}, repo="dep")
    needer = library(name="needer", platform="zephyr", requires={"libraries": ["someone/dep"]})

    assert run(needer, "--project", root) == 2

    assert "dep works on stm32, as platform in its installer.yml says, not on zephyr" in capsys.readouterr().err
    assert not (root / ".lib-installer.json").exists()


def _zip(path, top, manifest):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{top}installer.yml", manifest)
        archive.writestr(f"{top}src/demo.h", "int demo(void);\n")
        archive.writestr(f"{top}src/demo.c", "int demo(void) { return 1; }\n")

    return path


def test_the_platform_is_read_from_a_zip_as_github_gives_it(project, tmp_path):
    root = project("zephyr")
    archive = _zip(tmp_path / "demo-main.zip", "demo-main/", MANIFEST)

    assert run(archive, "--project", root) == 0

    assert json.loads((root / ".lib-installer.json").read_text(encoding="utf-8"))["platform"] == "zephyr"


def test_the_platform_is_read_from_a_zip_with_no_top_folder(project, tmp_path):
    root = project("zephyr")
    archive = _zip(tmp_path / "demo.zip", "", MANIFEST)

    assert run(archive, "--project", root) == 0

    assert json.loads((root / ".lib-installer.json").read_text(encoding="utf-8"))["platform"] == "zephyr"


def test_a_zip_with_no_manifest_is_said(project, tmp_path, capsys):
    root = project("zephyr")
    archive = tmp_path / "empty.zip"

    with zipfile.ZipFile(archive, "w") as made:
        made.writestr("demo-main/README.md", "nothing\n")

    assert run(archive, "--project", root) == 2

    assert "holds no installer.yml" in capsys.readouterr().err


def test_a_file_that_is_no_zip_is_said(project, tmp_path, capsys):
    root = project("zephyr")
    (tmp_path / "demo.tar").write_text("not a zip", encoding="utf-8")

    assert run(tmp_path / "demo.tar", "--project", root) == 2

    assert "is not a .zip" in capsys.readouterr().err
