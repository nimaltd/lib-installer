"""
The block helper every installer writes its lines into project files with.

Tested with # and with ; as the sign, since CMake and platformio.ini both hold
blocks, and with the rules every installer keeps: a half written block leaves
its file alone, line endings are kept, and an edit inside a block is noticed.
"""

import pytest

from lib_installer.core import blocks, cli, installer, target
from lib_installer.core.blocks import Marker
from lib_installer.core.target import CHANGED, Outcome


@pytest.mark.parametrize("sign", ["#", ";"])
def test_the_markers_name_the_installer_the_library_and_a_label(sign):
    plain = Marker("zephyr-installer", "gcore", sign=sign)
    labelled = Marker("zephyr-installer", "gcore", "conf", sign=sign)

    assert plain.open == f"{sign} >>> zephyr-installer: gcore >>>"
    assert plain.close == f"{sign} <<< zephyr-installer: gcore <<<"
    assert labelled.open == f"{sign} >>> zephyr-installer: gcore/conf >>>"
    assert labelled.name == "gcore/conf"


M = Marker("x-installer", "demo")
BLOCK = blocks.lines(M, ["a()", "b()"])


def test_a_block_is_found_again():
    text = "before\n" + BLOCK + "after\n"
    start, end = blocks.span(text, M)

    assert text[start:end] == BLOCK.rstrip("\n")
    assert blocks.body(text, (start, end)) == "a()\nb()\n"


def test_no_block_is_none():
    assert blocks.span("nothing here\n", M) is None


@pytest.mark.parametrize("text", [
    M.open + "\na()\n",                       # its end missing
    "a()\n" + M.close + "\n",                  # its start missing
    M.close + "\n" + M.open + "\n",            # the wrong way round
    M.open + "\n" + M.open + "\n" + M.close + "\n",  # one started inside another
    M.close + "\n" + M.open + "\nx\n" + M.close + "\n",  # a stray end before a whole block
])
def test_a_half_written_block_is_false(text):
    assert blocks.span(text, M) is False


def test_a_label_keeps_two_blocks_of_one_library_apart():
    conf = Marker("x-installer", "demo", "conf")
    text = BLOCK + blocks.lines(conf, ["c()"])

    assert blocks.body(text, blocks.span(text, conf)) == "c()\n"
    assert blocks.body(text, blocks.span(text, M)) == "a()\nb()\n"


def test_every_block_of_one_marker_is_found_for_a_file_with_several():
    ini = "[env]\nbuild_flags =\n" + blocks.lines(Marker("pio-installer", "demo", sign=";"), ["-DA"], "    ")
    text = ini + "\n[env:x]\nbuild_flags = -DX\n" + blocks.lines(Marker("pio-installer", "demo", sign=";"), ["-DA"], "    ")

    assert len(blocks.spans(text, Marker("pio-installer", "demo", sign=";"))) == 2


def test_taken_out_it_takes_the_blank_line_below_it():
    text = "top\n" + BLOCK + "\nbottom\n"

    assert blocks.cut(text, blocks.span(text, M), "\n") == "top\nbottom\n"


def test_taken_out_at_the_end_it_takes_the_blank_line_above_it():
    text = "top\n\n" + BLOCK

    assert blocks.cut(text, blocks.span(text, M), "\n") == "top\n"


def test_taken_out_indented_it_takes_its_indentation():
    text = "x\n" + blocks.lines(M, ["a()"], "    ") + "y\n"

    assert blocks.cut(text, blocks.span(text, M), "\n") == "x\ny\n"


def test_crlf_is_kept():
    text = "top\r\n" + blocks.lines(M, ["a()"], newline="\r\n") + "\r\nbottom\r\n"

    assert blocks.line_ending(text) == "\r\n"
    assert blocks.cut(text, blocks.span(text, M), "\r\n") == "top\r\nbottom\r\n"


def test_outside_is_the_users_part():
    assert blocks.outside("mine\n" + BLOCK + "also mine\n", M) == "mine\n\nalso mine\n"


def test_the_fingerprint_ignores_line_endings_and_indentation():
    assert blocks.fingerprint("a()\nb()\n") == blocks.fingerprint("    a()\r\n    b()\r\n")
    assert blocks.fingerprint("a()\nb()\n") != blocks.fingerprint("a()\nc()\n")


def test_an_edit_inside_a_block_is_noticed_from_the_record():
    recorded = {"CMakeLists.txt": blocks.fingerprints(BLOCK, [M])}
    edited = BLOCK.replace("b()", "b(1)")

    assert not blocks.edited(recorded, "CMakeLists.txt", M, BLOCK)
    assert blocks.edited(recorded, "CMakeLists.txt", M, edited)
    assert not blocks.edited({}, "CMakeLists.txt", M, edited)


def test_save_backs_up_before_a_change_and_writes_nothing_when_nothing_changed(tmp_path):
    path = tmp_path / "CMakeLists.txt"
    path.write_text("old\n")

    def write(p, text):
        p.write_text(text)

    assert blocks.save(path, "old\n", "old\n", write) == (False, None)
    changed, saved = blocks.save(path, "old\n", "new\n", write)

    assert changed and saved.read_text() == "old\n"
    assert path.read_text() == "new\n"


def test_save_makes_a_missing_file_without_a_backup(tmp_path):
    path = tmp_path / "sub" / "sysbuild.conf"

    assert blocks.save(path, "", "x\n", lambda p, text: p.write_text(text)) == (True, None)


def test_the_record_keeps_what_the_target_says_it_wrote(library, project, monkeypatch):
    root = project(cmake=True)
    written = {"CMakeLists.txt": {"demo": "0123456789abcdef"}}
    monkeypatch.setattr(target.current, "integrate",
                        lambda *args, **kwargs: [Outcome("CMake", CHANGED, "added", blocks=written)])
    monkeypatch.setattr(cli, "_answer", lambda prompt: None)

    assert cli.main([str(library(once=[])), "--project", str(root), "--dir", "demo"]) == 0

    assert installer.installed_libraries(root)["demo"]["blocks"] == written



# ----------------------------------------------------------------------------
# Groups of lines with a label and a place, and putting a block at an anchor
# ----------------------------------------------------------------------------

from lib_installer.core.manifest import ManifestError  # noqa: E402

PLACES = ("module", "before-zephyr", "after-zephyr")


def test_a_plain_list_of_lines_is_one_group_as_it_always_was():
    found = blocks.groups(["  a()  ", "", "b()"], "zephyr.cmake", PLACES, "module")

    assert [(g.label, g.where, g.lines, g.legacy) for g in found] == [("cmake", "module", ["a()", "b()"], True)]


def test_groups_keep_their_order_label_and_place():
    found = blocks.groups([
        {"label": "warnings", "lines": ["w()"]},
        {"label": "conf", "where": "before-zephyr", "lines": ["c()"]},
    ], "zephyr.cmake", PLACES, "module")

    assert [(g.label, g.where, g.lines, g.legacy) for g in found] == [
        ("warnings", "module", ["w()"], False), ("conf", "before-zephyr", ["c()"], False)]


def test_a_groups_lines_keep_their_indentation():
    found = blocks.groups([{"label": "x", "lines": ["if(A)  ", "    b()", "", "endif()"]}],
                          "zephyr.cmake", PLACES, "module")

    assert found[0].lines == ["if(A)", "    b()", "endif()"]


@pytest.mark.parametrize("value, says", [
    (["a()", {"label": "x", "lines": []}], "mixes lines and groups"),
    ([{"label": "Bad", "lines": []}], "Label a group"),
    ([{"label": "x", "where": "nowhere", "lines": []}], "Use one of"),
    ([{"label": "x", "lines": []}, {"label": "x", "lines": []}], "two groups labelled x"),
    ([{"label": "x", "lines": ["a()\nb()"]}], "runs onto another"),
    ("a()", "a list of groups"),
])
def test_a_group_that_cannot_be_written_is_refused(value, says):
    with pytest.raises(ManifestError, match=says):
        blocks.groups(value, "zephyr.cmake", PLACES, "module")


def test_an_option_takes_groups_only():
    with pytest.raises(ManifestError, match="a list of groups"):
        blocks.groups(["a()"], "options.x.zephyr.cmake", PLACES, "module", legacy=False)


def test_the_labels_of_a_librarys_blocks_are_found_in_order():
    text = (blocks.lines(Marker("z", "gcore", "conf"), ["c()"]) + blocks.lines(Marker("z", "gcore"), ["m()"])
            + blocks.lines(Marker("z", "gcore", "report"), ["r()"]) + blocks.lines(Marker("z", "other", "elsewhere"), ["o()"]))

    assert blocks.labels(text, "z", "gcore") == ["conf", "report"]


def _above(text):
    at = text.find("find_package(Zephyr)")

    return at if at >= 0 else None


def test_a_block_goes_above_its_anchor_with_a_blank_line_after_it():
    text = "cmake_minimum_required()\n\nfind_package(Zephyr)\n"

    placed = blocks.place(text, M, ["a()"], "\n", _above)

    assert placed == "cmake_minimum_required()\n\n" + M.open + "\na()\n" + M.close + "\n\nfind_package(Zephyr)\n"


def test_a_block_with_no_anchor_goes_at_the_end_after_a_blank_line():
    assert blocks.place("x()\n", M, ["a()"], "\n") == "x()\n\n" + M.open + "\na()\n" + M.close + "\n"
    assert blocks.place("", M, ["a()"], "\n") == M.open + "\na()\n" + M.close + "\n"


@pytest.mark.parametrize("anchor", [None, _above])
def test_a_block_already_in_its_place_comes_back_as_it_was(anchor):
    text = blocks.place("top\n\nfind_package(Zephyr)\n", M, ["a()"], "\n", anchor)

    assert blocks.place(text, M, ["a()"], "\n", anchor) == text


def test_two_blocks_in_one_place_keep_their_order():
    first, second = Marker("z", "gcore", "a"), Marker("z", "gcore", "b")
    text = "find_package(Zephyr)\n"

    for _ in range(2):
        text = blocks.place(text, first, ["a()"], "\n", _above)
        text = blocks.place(text, second, ["b()"], "\n", _above)

    assert text.index(first.open) < text.index(second.open) < text.index("find_package")
    assert text.count(first.open) == 1


def test_a_block_found_away_from_its_anchor_is_moved():
    text = "find_package(Zephyr)\n\n" + blocks.lines(M, ["a()"])

    moved = blocks.place(text, M, ["a()"], "\n", _above)

    assert moved.index(M.open) < moved.index("find_package")


def test_a_half_written_block_is_not_placed():
    assert blocks.place(M.open + "\n", M, ["a()"], "\n") is False


def test_crlf_is_kept_when_placing():
    placed = blocks.place("x()\r\n", M, ["a()"], "\r\n")

    assert "\n" not in placed.replace("\r\n", "")



# ----------------------------------------------------------------------------
# From 2.1.0: the lines under the places they go, with no label and no where
# ----------------------------------------------------------------------------

PLACES = ("module", "before-zephyr", "after-zephyr")


def test_each_place_is_one_group_named_after_it():
    found = blocks.groups({"before-zephyr": ["a()", "b()"], "module": ["c()"]}, "zephyr.cmake", PLACES, "module",
                          rooted=True)

    assert [(g.label, g.where, g.lines) for g in found] == [
        ("before-zephyr", "before-zephyr", ["a()", "b()"]), ("module", "module", ["c()"])]


def test_an_options_groups_are_named_after_it_too():
    found = blocks.groups({"module": ["c()"]}, "options.lfs.zephyr.cmake", PLACES, "module", legacy=False,
                          prefix="lfs", rooted=True)

    assert [g.label for g in found] == ["lfs-module"]


def test_a_place_with_no_lines_is_no_group():
    assert blocks.groups({"module": [], "after-zephyr": None}, "zephyr.cmake", PLACES, "module", rooted=True) == []


def test_a_place_there_is_not_is_refused():
    from lib_installer.core.manifest import ManifestError

    with pytest.raises(ManifestError, match="one of: module, before-zephyr, after-zephyr"):
        blocks.groups({"before": ["a()"]}, "zephyr.cmake", PLACES, "module", rooted=True)


def test_before_2_1_0_the_places_are_refused():
    from lib_installer.core.manifest import ManifestError

    with pytest.raises(ManifestError, match="new in 2.1.0"):
        blocks.groups({"module": ["a()"]}, "zephyr.cmake", PLACES, "module")
