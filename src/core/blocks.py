"""
Marked blocks in a project's own files, the same on every platform.

The installer adds a library's lines to a file the project owns, such as a
CMakeLists.txt or platformio.ini, between two marker lines that name it:

    # >>> lib-installer: gcore >>>
    ...
    # <<< lib-installer: gcore <<<

and finds them again by those markers on the next install, to write them anew
or take them out. A label after the library's name keeps several blocks of one
library apart, "gcore/conf" and "gcore/report", and the sign is the file's own
comment sign: # in CMake and Kconfig, ; in platformio.ini.

Three rules hold in every file:

- A file with only one marker of a block is never changed: whatever is written
  could land in the wrong place. The lines to add by hand are given instead.
- The file is backed up before any change, and its line endings are kept.
- Lines outside the blocks are never touched.

What each block held when it was written is kept in the record, as a
fingerprint, so the next install can tell the user edited inside one.
"""

import hashlib
import re

from .files import backup

# A label, as a manifest writes it: like an option's name.
LABEL = re.compile(r"^[a-z][a-z0-9_-]*$")


class Marker:
    """The two lines around one block, and the name the record keeps it by."""

    def __init__(self, installer, library, label=None, sign="#"):
        self.name = f"{library}/{label}" if label else str(library)
        self.open = f"{sign} >>> {installer}: {self.name} >>>"
        self.close = f"{sign} <<< {installer}: {self.name} <<<"

    def __repr__(self):
        return f"Marker({self.name})"


def span(text, marker):
    """
    Where a block is in text: (start, end), from its first marker's first
    character to its last marker's last; None when there is none; False when
    only one of its markers is there, or they stand the wrong way round.
    """
    found = spans(text, marker)

    if found is False:
        return False

    return found[0] if found else None


def spans(text, marker):
    """
    Every block of this marker in text, for a file that holds one in several
    places, as platformio.ini does in each environment. [] for none, False when
    a marker is left without its partner.
    """
    found = []
    at = 0

    while True:
        start = text.find(marker.open, at)
        stray = text.find(marker.close, at)

        if start < 0:
            # A closing marker with no opening one before it.
            return False if stray >= 0 else found

        if 0 <= stray < start:
            return False

        end = text.find(marker.close, start + len(marker.open))

        if end < 0:
            return False

        nested = text.find(marker.open, start + len(marker.open))

        if 0 <= nested < end:
            return False

        found.append((start, end + len(marker.close)))
        at = end + len(marker.close)


def line_start(text, at):
    """Where the line holding position at begins."""
    return text.rfind("\n", 0, at) + 1


def body(text, block_span):
    """The lines between a block's two markers, as text."""
    start, end = block_span
    first = text.find("\n", start)
    last = line_start(text, end)

    return text[first + 1:last] if 0 <= first < last else ""


def fingerprint(text):
    """
    What a block holds, as a short hash. Line endings and the indentation the
    block was written with do not count, since an editor changes those freely.
    """
    lines = [line.strip() for line in text.replace("\r\n", "\n").split("\n") if line.strip()]

    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()[:16]


def outside(text, marker):
    """The text with every block of this marker taken out, for reading what is the user's."""
    found = spans(text, marker)

    if not found:
        return text

    out = []
    at = 0

    for start, end in found:
        out.append(text[at:start])
        at = end

    out.append(text[at:])

    return "".join(out)


def cut(text, block_span, newline):
    """
    The text with a block taken out, with the line it stood on and the one
    blank line that came with it: below it, or above it when it ends the file.
    """
    start, end = block_span
    start = line_start(text, start)

    if text.startswith(newline, end):
        end += len(newline)

    if text.startswith(newline, end):
        end += len(newline)
    elif end == len(text) and text[:start].endswith(newline + newline):
        start -= len(newline)

    return text[:start] + text[end:]


def line_ending(text):
    """The line ending a file uses: CRLF when it has any, otherwise LF."""
    return "\r\n" if "\r\n" in text else "\n"


def lines(marker, content, indent="", newline="\n"):
    """A block as text: its markers around content, each line indented as given."""
    rows = [marker.open] + list(content) + [marker.close]

    return newline.join(indent + row if row else row for row in rows) + newline


def save(path, text, updated, write):
    """
    Write updated to path when it differs from text, backing the file up
    first. Returns (changed, backup): backup is None for a file that did not
    exist. write(path, text) is the installer's own, which keeps the bytes and
    line endings it reads.
    """
    if updated == text:
        return False, None

    saved = backup(path) if path.exists() else None
    path.parent.mkdir(parents=True, exist_ok=True)
    write(path, updated)

    return True, saved


def edited(recorded, file_name, marker, text):
    """
    Whether the user changed what is inside a block since it was written, by
    the fingerprint the record keeps. False when the record does not know it.
    """
    found = span(text, marker)

    if not found or not isinstance(recorded, dict):
        return False

    known = recorded.get(file_name)

    if not isinstance(known, dict) or marker.name not in known:
        return False

    return fingerprint(body(text, found)) != known[marker.name]


def fingerprints(text, markers):
    """{marker name: fingerprint} for each of these blocks found in text."""
    found = {}

    for marker in markers:
        place = span(text, marker)

        if place:
            found[marker.name] = fingerprint(body(text, place))

    return found


def labels(text, installer, library, sign="#"):
    """The labels of this library's labelled blocks in text, in the order they stand."""
    pattern = re.compile(re.escape(f"{sign} >>> {installer}: {library}/") + r"([a-z][a-z0-9_-]*) >>>")

    return list(dict.fromkeys(pattern.findall(text)))


def place(text, marker, content, newline, anchor=None):
    """
    text with a block of content in its place: taken out from wherever it is,
    and put back above the line anchor(text) gives the start of, with a blank
    line after it, or, with no anchor or none found, at the end of the file
    after a blank line. Done that way, a block already in its place comes back
    exactly as it was. False when the block is half written.
    """
    found = span(text, marker)

    if found is False:
        return False

    rest = cut(text, found, newline) if found else text
    block = newline.join([marker.open] + list(content) + [marker.close])
    at = anchor(rest) if anchor is not None else None

    if at is not None:
        return rest[:at] + block + newline + newline + rest[at:]

    head = rest.rstrip("\r\n")

    return (head + newline + newline if head else "") + block + newline


class Group:
    """
    Lines a library adds to a file of the project's, with a label and a place,
    such as a group of CMake lines for a Zephyr application's
    CMakeLists.txt.

    legacy is a plain list of lines from a manifest written before groups:
    written as it always was, so an update changes nothing.
    """

    def __init__(self, label, where, lines, legacy=False):
        self.label = label
        self.where = where
        self.lines = lines
        self.legacy = legacy

    def __repr__(self):
        return f"Group({self.label} in {self.where})"


def _group_lines(value, key, indented=True):
    """
    The lines of a group: text, one line each, blank ones dropped. Each keeps
    the space it starts with, for the body of an if() or a foreach(), unless
    indented is off, for the plain lists from before groups, written as they
    always were.
    """
    from .manifest import ManifestError

    if not isinstance(value, list) or not all(isinstance(line, str) for line in value):
        raise ManifestError(f"{key} is a list of lines, each in quotes when it holds a colon.")

    if any("\n" in line or "\r" in line for line in value):
        raise ManifestError(f"{key} has a line that runs onto another. Give each line on its own.")

    return [line.rstrip() if indented else line.strip() for line in value if line.strip()]


def _placed_groups(value, key, places, prefix, rooted):
    """The groups of a mapping of places to their lines, one group a place, in the manifest's order."""
    from . import target
    from .manifest import ManifestError

    if not rooted:
        raise ManifestError(
            f"{key} gives its lines under the places they go, which is new in 2.1.0: ask for it under "
            f"requires, as {target.current.requires_key}: 2.1.0, or give a list of groups."
        )

    found = []

    for where, lines in value.items():
        where = str(where)

        if where not in places:
            raise ManifestError(f"{key} has {where!r}. Give the lines under one of: {', '.join(places)}.")

        written = _group_lines(lines or [], f"{key}.{where}")

        if written:
            found.append(Group(f"{prefix}-{where}" if prefix else where, where, written))

    return found


def groups(value, key, places, default, legacy=True, prefix=None, rooted=False):
    """
    The groups of a manifest key such as zephyr.cmake: a list of groups, each
    with a label, where it goes, one of places, default when it does not say,
    and its lines. A plain list of lines, the form from before groups, is one
    group labelled after the key's last part, in default, unless legacy is off.

    From 2.1.0, rooted, it may be a mapping of places to their lines instead,
    with no label and no where: each place is one group, labelled after it, or
    for an option after the option and it, prefix-place, so an option's group
    never takes the name of the library's.
    """
    from .manifest import ManifestError

    if value is None or value == [] or value == {}:
        return []

    if isinstance(value, dict):
        return _placed_groups(value, key, places, prefix, rooted)

    if not isinstance(value, list):
        raise ManifestError(f"{key} is a list of groups, each with a label, a where and its lines.")

    if all(isinstance(item, str) for item in value):
        if not legacy:
            raise ManifestError(f"{key} is a list of groups, each with a label, a where and its lines.")

        lines = _group_lines(value, key, indented=False)

        return [Group(key.rsplit(".", 1)[-1], default, lines, legacy=True)] if lines else []

    if not all(isinstance(item, dict) for item in value):
        raise ManifestError(f"{key} mixes lines and groups. Put every line inside a group.")

    found = []

    for item in value:
        label = str(item.get("label") or "")

        if not LABEL.match(label):
            raise ManifestError(
                f"{key} has a group labelled {label!r}. Label a group in lower case letters, digits, "
                "_ and -, starting with a letter."
            )

        where = str(item.get("where") or default)

        if where not in places:
            raise ManifestError(f"{key}.{label} goes where {where!r}. Use one of: {', '.join(places)}.")

        found.append(Group(label, where, _group_lines(item.get("lines") or [], f"{key}.{label}.lines")))

    names = [group.label for group in found]
    twice = sorted({name for name in names if names.count(name) > 1})

    if twice:
        raise ManifestError(f"{key} has two groups labelled {', '.join(twice)}. Give each its own label.")

    return found
