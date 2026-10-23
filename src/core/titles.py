"""
Titles and notes, from 4.0.0: the comments a manifest gives the lines it writes.

A list a library writes into a file of the project's, or of its own, can be
given in groups, a mapping of each group's title to its list, and a setting
can carry a note, as a mapping of one, SYMBOL=value: its note. Every file
written from them carries both as comments, the same way on every platform:
a group's title between two lines of stars, a note as a comment of its own
above its setting. The sign is the file's own: # in Kconfig, CMake and
sdkconfig.defaults, ; in platformio.ini.

From 4.0.0 a platform's section also gives every line under where it goes:
project, the project's own files, and library, the library's own folder. The
groups of CMake lines read from there are here too, since Zephyr and ESP-IDF
read them the same way, each with places of its own.
"""

import re

from . import blocks
from .manifest import ManifestError

# How many stars the lines around a title have: 80 columns with their "# ".
WIDTH = 78

# A comment Kconfig reads as a setting, "# CONFIG_FOO is not set", which no
# title or note of a manifest may be.
_NOT_SET = re.compile(r"^(?:SB_)?CONFIG_\S+ is not set")


def stars(sign="#"):
    """A line of stars, above and below a title, as a comment of the file's."""
    return f"{sign} " + "*" * WIDTH


STARS = stars()


def comment(value, what):
    """
    A title or a note of the manifest's, as the comment the installer writes it
    into a file with: one line, which every file it goes into reads as a
    comment and nothing else, and which is never taken for a line that starts
    or ends a block.
    """
    text = "" if value is None or isinstance(value, (list, dict)) else str(value).strip()

    if not text or "\n" in text or "\r" in text:
        raise ManifestError(f"{what} is {value!r}. Give it one line of text.")

    if ">>>" in text or "<<<" in text or "USER CODE" in text:
        raise ManifestError(
            f"{what} is {text!r}, which has what the installer marks its blocks with. Say it another way."
        )

    if _NOT_SET.match(text):
        raise ManifestError(f"{what} is {text!r}, which Kconfig would read as a setting. Say it another way.")

    return text


def listed(value, key, make, notes=True):
    """
    The entries of a list under key, each made by make(text): a plain list, or
    from 4.0.0 groups of them, a mapping of each group's title to its list. An
    entry of a list of settings can carry a note, as a mapping of one,
    SYMBOL=value: its note; a line of CMake cannot, since a line holding ': '
    is CMake's own and goes in quotes. Each entry is given the title of its
    group and its note, None when it has none, and one make() gives None for,
    a blank line of CMake, is passed by.
    """
    if value is None:
        return []

    if isinstance(value, list):
        parts = [(None, value)]
    elif isinstance(value, dict):
        parts = list(value.items())
    else:
        raise ManifestError(f"{key} is a list, or groups of lists, each under its title.")

    found = []

    for title, entries in parts:
        if title is not None:
            title = comment(title, f"A title under {key}")

            if not isinstance(entries, list) or not entries:
                raise ManifestError(f"{key} has the title {title!r} with no list under it. Give its lines there.")

        for entry in entries:
            note = None

            if isinstance(entry, dict):
                if not notes:
                    raise ManifestError(
                        f"{key} has {entry!r}, which YAML reads as a mapping: a line holding ': ' goes in quotes."
                    )

                if len(entry) != 1:
                    raise ManifestError(
                        f"{key} has {entry!r}. Give one setting, with its note after a colon, such as "
                        "LOG=n: no messages."
                    )

                (entry, note), = entry.items()
                note = comment(note, f"The note of {entry} under {key}")

            if entry is None:
                raise ManifestError(f"{key} has an empty entry. A comment for the file goes in a title or a note.")

            made = make(entry)

            if made is None:
                continue

            made.group = title
            made.note = note
            found.append(made)

    return found


def titled(title, sign="#"):
    """A group's title between two lines of stars, as comment lines."""
    return [stars(sign), f"{sign} {title}", stars(sign)]


def annotated(entries, line, sign="#", blank=True):
    """
    The lines of entries, each written by line(entry): the title of an entry's
    group between two lines of stars above the group's first entry, and an
    entry's note, when it has one, as a comment of its own above it. A title
    that does not start them comes after a blank line, unless blank is off,
    for a file that reads a blank line as the end of the list, as
    platformio.ini does build_flags.
    """
    lines = []
    title = None

    for entry in entries:
        group = getattr(entry, "group", None)

        if group is not None and group != title:
            if lines and blank:
                lines.append("")

            lines.extend(titled(group, sign))
            title = group

        note = getattr(entry, "note", None)

        if note:
            lines.append(f"{sign} {note}")

        lines.append(line(entry))

    return lines


def grouped(entries):
    """Whether any of entries is in a group, so the file written from them sets its titles apart."""
    return any(getattr(entry, "group", None) for entry in entries)


class Line:
    """A line of a list of lines, such as one of CMake, and the title of its group."""

    def __init__(self, text, key):
        if not isinstance(text, str):
            raise ManifestError(f"{key} is a list of lines, each in quotes when it holds a colon.")

        if "\n" in text or "\r" in text:
            raise ManifestError(f"{key} has a line that runs onto another. Give each line on its own.")

        # The space it starts with is kept, for the body of an if().
        self.text = text.rstrip()
        self.group = None
        self.note = None


def line_of(text, key):
    """A line of CMake, or None for a blank one, which is passed by."""
    line = Line(text, key)

    return line if line.text.strip() else None


def part(value, key, keys):
    """A part of a platform's section, such as zephyr.project: a mapping of some of keys, {} when left out."""
    if value is None:
        return {}

    if not isinstance(value, dict):
        raise ManifestError(f"{key} holds {', '.join(keys)}, each a key of its own under it.")

    unknown = [str(name) for name in value if name not in keys]

    if unknown:
        raise ManifestError(f"{key} has {', '.join(unknown)}. It holds {', '.join(keys)}.")

    return value


def cmake_groups(project, library, key, places, own, prefix=None):
    """
    The groups of CMake lines of a manifest asking for 4.0.0: those of
    {key}.project.cmake, the project's own CMakeLists.txt, under places, and
    those of {key}.library.cmake, the library's own, in the place own. Each
    place is one group, labelled after it, or for an option after the option
    and it, as the places of 2.1.0 were, so the blocks in the files keep their
    names. A title of the manifest's is written among the lines, between two
    lines of stars.
    """
    given = part(project, f"{key}.project.cmake", places)
    found = []

    for where, value in list(given.items()) + [(own, library)]:
        name = f"{key}.library.cmake" if where == own else f"{key}.project.cmake.{where}"
        entries = listed(value, name, lambda text, name=name: line_of(text, name), notes=False)
        lines = annotated(entries, lambda line: line.text)

        if lines:
            found.append(blocks.Group(f"{prefix}-{where}" if prefix else where, where, lines))

    return found


def option_cmake(option, section, renamed, places, own):
    """
    An option's own groups of CMake lines, written while it is taken: under
    project.cmake and library.cmake of its part for the platform, section,
    from 4.0.0, and under cmake before, with own among places. The part is
    the one read_option() kept, as option.<section>_part.
    """
    given = getattr(option, f"{section}_part", None) or {}
    key = f"options.{option.name}.{section}"

    if not renamed:
        if "project" in given or "library" in given:
            raise ManifestError(
                f"{key}.project and {key}.library are new in 4.0.0: ask for it under requires, as "
                "lib_installer: 4.0.0, or give the lines under cmake."
            )

        return blocks.groups(given.get("cmake"), f"{key}.cmake", places, own, legacy=False,
                             prefix=option.name, rooted=getattr(option, "rooted", False))

    if "cmake" in given:
        raise ManifestError(
            f"{key}.cmake is {key}.project.cmake and {key}.library.cmake from 4.0.0, by the "
            "CMakeLists.txt each line goes into."
        )

    given = part(given, key, ("project", "library"))
    project = part(given.get("project"), f"{key}.project", ("cmake",))
    library = part(given.get("library"), f"{key}.library", ("cmake",))

    return cmake_groups(project.get("cmake"), library.get("cmake"), key,
                        tuple(where for where in places if where != own), own, prefix=option.name)
