"""
Reading and validating an installer.yml manifest.

Every library this installs carries one of these at the root of its repository. It answers
three questions: what the library is, what it needs from the project, and which
files make it up.

The "what it is" part matters more than it first appears. A library can itself
be an RTOS, so saying only what a library requires is not enough. A library
declares its kind, and declares what it provides, and another library's
requirement is then satisfied by whatever provides that thing.
"""

import hashlib
import re
from pathlib import Path, PurePosixPath

from . import target, yamlreader

MANIFEST_NAME = "installer.yml"

# What the manifest was called before 1.9.0. A release tagged before the
# rename has only this one, and --ref can still ask for it.
LEGACY_MANIFEST_NAME = "library.yml"

MANIFEST_NAMES = (MANIFEST_NAME, LEGACY_MANIFEST_NAME)

# What a library is. Used for grouping and for satisfying requirements.
KINDS = (
    "driver",      # talks to a chip or a peripheral
    "middleware",  # sits between the application and a driver
    "rtos",        # is itself an operating system
    "protocol",    # implements a wire protocol
    "filesystem",  # stores files
    "utility",     # general help, no hardware of its own
    "bsp",         # board support, pin maps and wiring
)

# Finer grouping, used when listing libraries to a user.
CATEGORIES = (
    "sensor",
    "storage",
    "display",
    "communication",
    "wireless",
    "rtos",
    "timing",
    "power",
    "input",
    "math",
    "system",
)

class ManifestError(Exception):
    """A manifest is missing, unreadable, or does not describe a usable library."""


# Where a library's version lives: the @version tag in its header's file comment.
_VERSION_TAG = re.compile(r"@version\s+(\S+)")

# What a compiler takes. Keil, IAR and a Makefile name each of these files one
# by one, so this also decides which files an update has to tell them about.
COMPILED = (".c", ".cpp", ".cc", ".cxx", ".s", ".asm")

# A define as -D takes it: NAME, or NAME=value. The manifest arrives over the
# network and each define is written as it stands into XML, a Makefile and a
# Keil list, so only characters all of them hold safely, with nothing to quote,
# get through. A space or a quote could otherwise carry a second compiler flag
# in with it.
DEFINE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:=[A-Za-z0-9_.+/-]+)?$")


def define_name(define):
    """The name a define sets, without its value: HSE_VALUE from HSE_VALUE=8000000."""
    return str(define).split("=", 1)[0].strip()


# The installer release that every installer shares from 2.0.0 on, and the one
# that brought once files into the project's folder. Every installer of the
# family has the same version, so a manifest asking any of them for this one
# or newer was written for what it brings, whichever installer reads it.
MODERN = (2, 0, 0)

# The release from which every path naming a place in the project starts at the
# project's folder: an extra with a root lands there, as the library's own, and
# a run step's script and unless are found there. {library} stands for the
# folder the library is installed in, wherever --dir put it. In a list of
# files a to is another place where the list puts its files, the library's
# folder or, for once, the project's, and an extra's root one in the project's.
ROOTED = (2, 1, 0)
LIBRARY = "{library}"

# lib-installer 3.0.0, one installer for every platform. A manifest asking for
# it names the platforms the library works on, under platform, since nothing
# else says which kind of project it goes into.
NAMED = (3, 0, 0)

# The platforms lib-installer installs into, as platform: and --platform name them.
PLATFORMS = ("stm32", "zephyr", "esp32", "arduino", "pio")

# The release from which a key a platform's section does not have is refused,
# where before it was passed by without a word, and whatever it said with it.
# A manifest asking for less is told about it, and installs as it did.
CHECKED = (4, 0, 0)

# A character a folder of install.include_dirs cannot hold: each is written as
# it stands into the project's own files, an IDE's XML, a list Keil separates
# with ;, a Makefile, so one of these would break the file it lands in.
_UNSAFE_FOLDER = re.compile(r"[\"'<>&;\x00-\x1f]")


def platforms_of(data):
    """
    The platforms a parsed manifest says it works on, as a list, or None when
    it says nothing. platform is one name, platform: stm32, or a list of them,
    platform: [stm32, zephyr].
    """
    value = data.get("platform") if isinstance(data, dict) else None

    if value is None:
        return None

    names = value if isinstance(value, list) else [value]
    found = [str(name).strip().lower() for name in names]

    if not found or not all(name in PLATFORMS for name in found):
        raise ManifestError(
            f"platform has {value!r}. Name the platform it works on, one of {', '.join(PLATFORMS)}, "
            "such as platform: stm32, or a list of them, such as platform: [stm32, zephyr]."
        )

    return list(dict.fromkeys(found))

# A key under requires naming an installer: lib_installer, and the keys read
# before 3.0.0, installer, stm32_installer, zephyr_installer and the others.
_INSTALLER_KEY = re.compile(r"^(?:[a-z0-9]+_)?installer$")

# A drive letter, as in C:/x or C:x, which Windows reads as a place of its own.
_DRIVE = re.compile(r"^[A-Za-z]:")


def unsafe_path(text):
    """
    Why a path in a manifest could lead out of the folder it is read in, or None.

    A manifest arrives over the network before any of it is trusted, so a path
    such as "../../.ssh/id_rsa" or "C:/Windows/win.ini" has to be refused, not
    followed. Backslashes count as separators wherever the manifest is read:
    "..\\x" leaves the folder on Windows, and has to be refused on Linux as well,
    so one manifest means the same on both.
    """
    text = str(text).replace("\\", "/")

    if not text.strip():
        return "it is empty"

    if text.startswith("/"):
        return "it starts at the root of the drive"

    if _DRIVE.match(text):
        return "it names a drive"

    if ".." in text.split("/"):
        return "it climbs out with .."

    return None


def include_folder(value):
    """
    A folder of install.include_dirs, as a path inside the library, or
    ManifestError. It is written into the project's own files as it stands,
    so it has to stay inside the library, and hold nothing those files would
    read as anything but a path.
    """
    text = str(value).replace("\\", "/").strip()
    why = unsafe_path(text)

    if why is None and _UNSAFE_FOLDER.search(text):
        why = ("it holds a quote, <, >, &, ; or a control character, which an IDE's project file "
               "would not read as a path")

    if why:
        raise ManifestError(f"install.include_dirs has {value!r}: {why}. Give a folder inside the library, "
                            "such as src.")

    return text


def count_of(value, where):
    """How many of a peripheral a library needs: a whole number of one or more, or ManifestError."""
    if isinstance(value, bool) or not str(value).strip().isdigit() or int(str(value).strip()) < 1:
        raise ManifestError(f"{where} has a count of {value!r}. Give how many, a whole number from 1.")

    return int(str(value).strip())


def section_keys(data, section, known):
    """
    The keys of a platform's section, such as esp32, that it does not have.
    A manifest asking for 4.0.0 is refused for one, with the keys it does
    have; one asking for less gets a warning, and installs as it did.
    """
    part = data.get(section) if isinstance(data, dict) else None
    unknown = [str(key) for key in part if key not in known] if isinstance(part, dict) else []

    if unknown and asks_for(data, CHECKED):
        raise ManifestError(f"{section} has {', '.join(unknown)}. It holds {', '.join(known)}.")

    return unknown


def unknown_warnings(section, unknown):
    """What is said of the keys section_keys() found in a manifest asking for less than 4.0.0."""
    return [f"{section}.{key} is no key lib-installer reads, so it was left out" for key in unknown]


def asks_for(data, version):
    """Whether a manifest asks any installer for version, as (2, 1, 0), or newer."""
    requires = data.get("requires") if isinstance(data, dict) else None

    if not isinstance(requires, dict):
        return False

    for key, value in requires.items():
        if _INSTALLER_KEY.match(str(key)):
            wanted = _version_tuple(value)

            if wanted is not None and wanted >= version:
                return True

    return False


def asks_for_modern(data):
    """Whether a manifest asks any installer for 2.0.0 or newer."""
    return asks_for(data, MODERN)


def in_library(text):
    """
    (True, the rest) for a path starting with {library}, which names a place in
    the library's folder, else (False, the path), which names one from the
    project's folder.
    """
    text = str(text).replace("\\", "/")

    if text == LIBRARY or text.startswith(LIBRARY + "/"):
        return True, text[len(LIBRARY):].lstrip("/")

    return False, text


def _version_tuple(text):
    """(1, 2, 0) from "1.2.0", or None when it is not three whole numbers."""
    parts = str(text).strip().split(".")

    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None

    return tuple(int(part) for part in parts)


def check_installer(data):
    """
    Refuse a manifest written for a newer installer than this one.

    Called before anything else in the file is read. A manifest that needs a
    newer installer may use something this one does not understand, and reading
    it wrongly without a word is worse than stopping with the way forward.

    Raises:
        ManifestError, naming the version needed and how to update.
    """
    installer = target.current
    requires = data.get("requires")

    if not isinstance(requires, dict):
        return

    # lib_installer, and the keys of the five installers before 3.0.0, so a
    # manifest written for one of them is still checked against this version.
    for key in (installer.requires_key,) + tuple(getattr(installer, "requires_aliases", ())):
        if requires.get(key) is None:
            continue

        wanted = _version_tuple(requires[key])

        if wanted is None:
            raise ManifestError(
                f"requires.{key} is {requires[key]!r}. Write it as three numbers, "
                "like 1.1.0. YAML reads an unquoted 1.10 as the decimal number 1.1."
            )

        have = _version_tuple(installer.version) or (0, 0, 0)

        if wanted > have:
            needed = ".".join(str(part) for part in wanted)
            raise ManifestError(
                f"This library needs {installer.name} {needed} or newer, and this one is "
                f"{installer.version}. Nothing was changed.\n"
                f"Update it with:\n    {installer.update_command}"
            )


def _header_version(root, headers):
    """The @version tag in the first header's file comment, or None."""
    if not headers:
        return None

    try:
        with open(Path(root) / headers[0].source, encoding="utf-8", errors="replace") as handle:
            found = _VERSION_TAG.search(handle.read(4096))
    except OSError:
        return None

    return found.group(1) if found else None


# How files are laid out inside the folder they are installed into.
LAYOUTS = (
    "flat",    # every file at the top, so one include path covers the library
    "mirror",  # keep the repository's own folders, for a library too big to flatten
)


class OnceFile:
    """
    A file copied once and then left alone, because it belongs to the user.

    Usually a configuration header, but the rule is about ownership rather than
    content: a port layer someone fills in, or a table they tune, wants exactly
    the same treatment.
    """

    def __init__(self, source, destination):
        self.source = source
        self.destination = destination

    def __repr__(self):
        return f"OnceFile({self.source!r} -> {self.destination!r})"


class FileEntry:
    """One file, where it lives in the repository and where it lands."""

    def __init__(self, source, destination):
        self.source = Path(source)
        # Kept as posix text, because it ends up in CMake, Keil and IAR project
        # files, and every one of them is happy with forward slashes.
        self.destination = str(destination).replace("\\", "/")

    @property
    def folder(self):
        """The destination's folder, relative to the install folder. "." at the top."""
        parent = Path(self.destination).parent.as_posix()

        return "." if parent in ("", ".") else parent

    def __repr__(self):
        return f"FileEntry({self.source.as_posix()!r} -> {self.destination!r})"


def is_pattern(path):
    """Whether a manifest entry names more than one file."""
    return any(ch in str(path) for ch in "*?[")


def _wildcard(pattern):
    """
    A test of whether a repository path matches a wildcard, the way a shell
    matches one: the whole path, with * and ? staying inside one folder, ** for
    any number of folders, none included, and [...] a set of characters. So
    *.c is the .c files at the top, src/*.c those in src, and src/**/*.c every
    one below src, however deep.

    The same test for a checkout and for GitHub's listing. PurePath.match,
    used before, matched from the end of the path and read ** as *, so from
    GitHub *.c took the .c files of every folder and src/**/*.c missed
    src/x.c, where a checkout's glob did neither.
    """
    out = []
    i = 0

    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:[^/]*/)*")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        elif pattern[i] == "[" and "]" in pattern[i + 2:]:
            # A ] right after the [ is one of the set, as a shell reads it.
            end = pattern.index("]", i + 2)
            body = pattern[i + 1:end]
            body = "^" + body[1:] if body.startswith("!") else body
            out.append("[" + body.replace("\\", "\\\\") + "]")
            i = end + 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1

    found = re.compile("".join(out) + r"\Z")

    return lambda path: found.match(path) is not None


def expand(root, entry, known=None):
    """
    Turn one manifest entry into the repository paths it names.

    An entry is a file, a folder, or a wildcard. A folder means every file
    beneath it, and a wildcard is matched the way a shell would. Results come
    back sorted, so a manifest produces the same install every time.

    Args:
        root: the repository root, used when matching against a local checkout.
        entry: the path, folder or pattern written in the manifest.
        known: every path in the repository, for matching without a checkout.
            The online install passes this, since it has no files on disk yet.

    Returns:
        A list of repository relative Paths, empty when nothing matched.
    """
    text = Path(entry).as_posix()

    if known is not None:
        if is_pattern(text):
            matches = _wildcard(text)

            return sorted(Path(p) for p in known if matches(p))

        if text in known:
            return [Path(text)]

        prefix = text.rstrip("/") + "/"

        return sorted(Path(p) for p in known if p.startswith(prefix))

    if is_pattern(text):
        # Matched against the checkout's paths exactly as against GitHub's
        # listing, so a wildcard means the same however the library arrived.
        matches = _wildcard(text)
        found = (p.relative_to(root) for p in root.rglob("*") if p.is_file())

        return sorted(p for p in found if p.parts[0] != ".git" and matches(p.as_posix()))

    target = root / text

    if target.is_file():
        return [Path(text)]

    if target.is_dir():
        return sorted(p.relative_to(root) for p in target.rglob("*") if p.is_file())

    return []


def _code_lists(data, where, rooted):
    """
    The headers and the sources data lists, data being a manifest or one of
    its options: under files, as every release reads them, or from 2.1.0 on
    their own, with no files around them. Both at once is refused, so no list
    is read twice. (None, None) when it lists neither.
    """
    files = data.get("files")
    loose = [key for key in ("headers", "sources") if key in data]

    if loose and files is not None:
        raise ManifestError(
            f"{where} has both files and {' and '.join(loose)}. List the headers and the sources in one place."
        )

    if loose:
        if not rooted:
            raise ManifestError(
                f"{where} lists {' and '.join(loose)} without files around them, which is new in 2.1.0: ask "
                f"for it under requires, as {target.current.requires_key}: 2.1.0, or put them under files."
            )

        return data.get("headers"), data.get("sources")

    if files is None:
        return None, None

    if not isinstance(files, dict):
        raise ManifestError(f"{where}: files should hold 'headers' and 'sources' lists.")

    return files.get("headers"), files.get("sources")


def _entries(root, raw, layout, known=None, rooted=False):
    """
    Read a files: list, where each item is a path, a folder, a wildcard, or a
    {from, to} pair.

    A plain entry takes its destination from the layout, and from 2.1.0, rooted,
    keeps its path. A pair says exactly where in the library's folder the file
    goes, and so it can only name one file. From 2.1.0 its from may be left out
    when it is the same path as its to. A root, a place in the project's folder,
    is refused: the code is built in the library's.
    """
    result = []

    for item in raw or []:
        if isinstance(item, dict) and "root" in item:
            raise ManifestError(
                f"headers and sources have {item!r}. Code is built in the library's folder, so it has no "
                "root, a place in the project's: give it a to in the library's folder, or list it under "
                "once to give the project a copy of its own."
            )

        if isinstance(item, dict) and rooted and "from" not in item and item.get("to"):
            item = dict(item, **{"from": item["to"]})

        _check_source(item["from"] if isinstance(item, dict) and "from" in item else item, "files")

        if isinstance(item, dict):
            if "from" not in item:
                raise ManifestError(f"a files entry is missing 'from': {item!r}")

            source = Path(item["from"])
            destination = item.get("to")

            if destination and is_pattern(source):
                place = "each keeps its path" if rooted else "let the layout place them"
                raise ManifestError(
                    f"'{source.as_posix()}' matches many files, so it cannot have a "
                    f"single 'to' of '{destination}'. Drop the 'to' and {place}, or list "
                    f"the files one by one."
                )

            if destination:
                result.append(FileEntry(source, destination))
                continue

            raw_entry = source
        else:
            raw_entry = Path(item)

        found = expand(root, raw_entry, known)

        if not found:
            # Kept so load() can refuse it by name rather than silently
            # installing nothing, which is what a wrong pattern feels like.
            result.append(FileEntry(raw_entry, _placed(raw_entry, layout)))
            continue

        for path in found:
            result.append(FileEntry(path, _placed(path, layout, raw_entry)))

    return result


def _check_source(text, where):
    """
    Refuse a path to a file of the library that leads out of the library.

    Read from a folder or a zip, a "from" of "../secret.txt" would copy a file
    from beside the library into the user's project, and from GitHub it would
    write the download outside the folder it was made in.
    """
    if isinstance(text, dict):
        return

    reason = unsafe_path(text)

    if reason:
        raise ManifestError(
            f"{where} lists {str(text)!r}, a file outside the library, which is never read: "
            f"{reason}. Name files from the library's own folder."
        )


def _placed(source, layout, entry=None):
    """
    Where a file lands when the manifest does not say.

    A folder keeps its shape whatever the layout, because "copy this folder"
    only means one thing, and flattening it would collide the moment two
    subfolders held the same file name.
    """
    if entry is not None and not is_pattern(entry):
        prefix = Path(entry).as_posix().rstrip("/") + "/"
        if source.as_posix().startswith(prefix):
            return source.as_posix()

    if layout == "mirror":
        return source.as_posix()

    return source.name


class Dependency:
    """
    Another library this one needs, and the oldest version of it that will do.

    Written in installer.yml as "osal" or "osal >= 1.1.0", with an owner in front
    when it is not a NimaLTD library: "someone/osal >= 1.1.0". A tag, a branch or
    a commit after an @ fetches exactly that, "someone/osal@v1.2.0", where
    without one it comes from the repository's default branch.

    A repository with no installer.yml of its own, such as a library its authors
    never wrote one for, is written as a mapping, with an installer.yml for it
    that this library carries:

        - source: littlefs-project/littlefs@v2.9.3
          manifest: manifests/littlefs.yml
          minimum: 2.9.0
    """

    _FORM = re.compile(
        r"^([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?)"   # name, or owner/name
        r"(?:@([A-Za-z0-9_.][A-Za-z0-9_./-]*))?"      # @tag, @branch or @commit
        r"\s*(?:>=\s*(\S+))?$"                       # >= the oldest version
    )

    _HELP = ('Write a library as its name, like "osal", with an owner for anyone '
             'else\'s, like "someone/lib", then @ and a tag, branch or commit if one is '
             'wanted, like "someone/lib@v1.2.0", and the oldest version that will do, '
             'like "osal >= 1.1.0".')

    def __init__(self, text):
        manifest = None
        minimum = None

        if isinstance(text, dict):
            if not text.get("source"):
                raise ManifestError(f"requires.libraries has {text!r}, with no source. {self._HELP}")

            manifest = text.get("manifest")
            minimum = text.get("minimum")
            spoken = str(text["source"]).strip()
        else:
            spoken = str(text).strip()

        found = self._FORM.match(spoken)

        if not found or ".." in (found.group(2) or ""):
            raise ManifestError(f'requires.libraries has "{spoken}". {self._HELP}')

        self.source = found.group(1)
        self.ref = found.group(2)
        self.name = str(text.get("name")) if isinstance(text, dict) and text.get("name") else self.source.split("/")[-1]
        self.minimum_text = found.group(3) or (str(minimum).strip() if minimum is not None else None)
        self.minimum = None

        # The installer.yml for a repository that has none, a file of the
        # library that needs it. Read like any other file of the library, so
        # it cannot be one from outside it either.
        self.manifest = None

        if manifest is not None:
            _check_source(manifest, f"requires.libraries ({self.source})")
            self.manifest = Path(str(manifest))

        if self.minimum_text is not None:
            self.minimum = _version_tuple(self.minimum_text)

            if self.minimum is None:
                raise ManifestError(
                    f'requires.libraries has "{spoken}". The version is three numbers, like 1.1.0.'
                )

    @property
    def fetch(self):
        """What to fetch: owner/name, with @ref when one was given."""
        return f"{self.source}@{self.ref}" if self.ref else self.source

    def satisfied_by(self, version):
        """Whether a library at this version will do. Any version will, with no minimum."""
        if self.minimum is None:
            return True

        have = _version_tuple(version) if version else None

        return have is not None and have >= self.minimum

    def __str__(self):
        name = f"{self.name}@{self.ref}" if self.ref else self.name

        if self.minimum_text is None:
            return name

        return f"{name} >= {self.minimum_text}"

    def __repr__(self):
        return f"Dependency({self})"


# An option's name, as typed after --with. Lower case only, so one word on the
# command line always means one option.
OPTION_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")


class Option:
    """
    A part of a library the user chooses at install, as littlefs is for spif.

    It brings files of the library's own, installed only when it is chosen, and
    other libraries it needs, installed with it. A file it brings is a library
    file like any other: replaced on every install, its USER CODE kept, and
    removed by the update that turns the option off.
    """

    def __init__(self, root, name, data, layout, known=None, rooted=False):
        if not isinstance(data, dict):
            raise ManifestError(f"options.{name} should hold a description, and the files and libraries it brings.")

        self.name = name
        self.description = str(data.get("description") or "").strip()
        self.libraries = [Dependency(x) for x in (data.get("libraries") or [])]
        # Whether the manifest asks for 2.1.0, for the target's part of an option.
        self.rooted = rooted

        headers, sources = _code_lists(data, f"options.{name}", rooted)
        self.headers = _entries(root, headers, layout, known, rooted)
        self.sources = _entries(root, sources, layout, known, rooted)

        # What the target reads of an option's own, such as zephyr.cmake.
        target.current.read_option(self, data)

    @property
    def code_files(self):
        return self.headers + self.sources

    def __repr__(self):
        return f"Option({self.name})"


class RunStep:
    """
    A command run once the library's files are in place, such as a script that
    makes a signing key.

    It runs on the user's own computer, so the user is always asked first, and
    is shown exactly what will run. Nothing in the manifest can turn the
    question off: only the user can, with --run or --yes. A file the step makes
    can be named with unless, and when it is already in the project's folder
    the step is skipped without a question.

        run:
          - label: signing-key
            description: Make MCUboot's signing key, sign_key.pem
            script: scripts/make_key.py      # Python, run with the installer's own
            args: [sign_key.pem]
            unless: sign_key.pem
          - label: other
            command: [imgtool, keygen, -k, sign_key.pem, -t, ecdsa-p256]

    From 2.1.0, rooted, the script is found from the project's folder, where an
    extra with a root or a once file put it, or in the library's own folder when
    it starts with {library}, and unless may start with {library} too. {library}
    in args and command stands for that folder. Before, the script was found in
    the library as it was fetched.
    """

    def __init__(self, data, rooted=False):
        self.rooted = rooted
        self.in_library = False
        self.unless_in_library = False

        if not isinstance(data, dict):
            raise ManifestError(f"run has {data!r}. Each step is a mapping with a label and a script or a command.")

        self.label = str(data.get("label") or "")

        if not OPTION_NAME.match(self.label):
            raise ManifestError(
                f"run has a step labelled {self.label!r}. Label a step in lower case letters, digits, "
                "_ and -, starting with a letter, since it is typed after --run."
            )

        self.description = str(data.get("description") or "").strip()
        script = data.get("script")
        command = data.get("command")

        if (script is None) == (command is None):
            raise ManifestError(f"run.{self.label} needs a script or a command, and only one of them.")

        self.script = None
        self.command = None

        if script is not None:
            if rooted:
                self.in_library, script = in_library(script)

            _check_source(script, f"run.{self.label}")

            if not str(script).lower().endswith(".py"):
                raise ManifestError(
                    f"run.{self.label} has the script {script!r}. A script is Python, run with the "
                    "installer's own Python, so it works the same on every computer. Anything else "
                    "goes in command."
                )

            self.script = Path(str(script))
        else:
            if not isinstance(command, list) or not command or not all(
                isinstance(part, (str, int, float)) and str(part) for part in command
            ):
                raise ManifestError(
                    f"run.{self.label}.command should be a list: the program, then each argument, "
                    "like [imgtool, keygen, -k, sign_key.pem]. It is run as it is, with no shell."
                )

            self.command = [str(part) for part in command]

        args = data.get("args") or []

        if not isinstance(args, list) or not all(isinstance(a, (str, int, float)) for a in args):
            raise ManifestError(f"run.{self.label}.args should be a list of words.")

        self.args = [str(a) for a in args]
        self.unless = data.get("unless")

        if self.unless is not None:
            if rooted:
                self.unless_in_library, self.unless = in_library(self.unless)

            reason = unsafe_path(self.unless)

            if reason:
                raise ManifestError(
                    f"run.{self.label}.unless is {data.get('unless')!r}, outside the project's folder: {reason}."
                )

            self.unless = str(self.unless).replace("\\", "/")

    @property
    def written(self):
        """The script as the manifest wrote it, {library} and all, in posix form."""
        if self.script is None:
            return None

        return (LIBRARY + "/" if self.in_library else "") + self.script.as_posix()

    def fingerprint(self):
        """What the step runs, as a short hash, so a changed step is asked about again."""
        script = self.written if self.in_library else str(self.script or "")
        text = "\0".join([script, *(self.command or []), "\0", *self.args])

        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    def __repr__(self):
        return f"RunStep({self.label})"


class Requirements:
    """
    Everything a library needs from the project it is dropped into.

    The libraries it needs are read here. The rest of requires depends on the
    kind of project, so the target reads it: hal_modules and peripherals for
    STM32, for one.
    """

    def __init__(self, data):
        data = data or {}
        self.libraries = [Dependency(x) for x in (data.get("libraries") or [])]
        target.current.read_requirements(self, data)

    def is_empty(self):
        """True when there is nothing worth telling the user about."""
        return not self.libraries and target.current.requirements_empty(self)


class Manifest:
    """What an installer.yml says about one library."""

    def __init__(self, root, data, known=None):
        self.root = Path(root)
        self.name = data["name"]
        self.description = data.get("description", "")
        self.repository = data.get("repository", "")
        self.license = data.get("license", "")

        # The platforms it works on, None for any. Named in every manifest
        # asking for 3.0.0, and checked against the platform of the run, so a
        # library for STM32 is refused in a Zephyr application here, not after
        # it went in and the build failed on the HAL. A target that is no
        # platform, as in the core's own tests, checks neither.
        self.platforms = platforms_of(data)
        running = getattr(target.current, "platform", None)

        if running and self.platforms is None and asks_for(data, NAMED):
            raise ManifestError(
                f"{self.name} asks for lib-installer 3.0.0 and names no platform. Add the one "
                f"it works on, such as platform: stm32, one of {', '.join(PLATFORMS)}."
            )

        if running and self.platforms is not None and running not in self.platforms:
            raise ManifestError(
                f"{self.name} works on {', '.join(self.platforms)}, as platform in its "
                f"installer.yml says, not on {running}, so it was not installed."
            )

        self.kind = str(data.get("kind", "driver")).lower()
        self.category = str(data.get("category", "")).lower()
        self.provides = [str(x).lower() for x in (data.get("provides") or [])]

        # A library that is an operating system satisfies an RTOS requirement,
        # whether or not whoever wrote the manifest remembered to say so.
        if self.kind == "rtos" and "rtos" not in self.provides:
            self.provides.append("rtos")

        self.requires = Requirements(data.get("requires"))

        # Written for 2.0.0 or newer: once files land in the project's folder,
        # as the project's own, rather than in the library's. A manifest from
        # before keeps the meaning it was written for, so a release tagged
        # then, whose header includes the configuration it lists under once,
        # still builds.
        self.modern = asks_for_modern(data)
        # Written for 2.1.0 or newer: every path naming a place in the project
        # starts at its folder, or at the library's with {library}, and every
        # file keeps the path it has in the repository. See ROOTED.
        self.rooted = asks_for(data, ROOTED)

        install = data.get("install") or {}
        layout = str(install.get("layout", "flat")).lower()

        if self.rooted and "layout" in install and layout != "mirror":
            raise ManifestError(
                f"install.layout is {install['layout']!r}. From 2.1.0 every file keeps the path it has in the "
                "repository, so leave install.layout out."
            )

        # From 2.1.0 there is no choosing: a file keeps its path, as mirror did.
        self.layout = "mirror" if self.rooted else layout

        headers, sources = _code_lists(data, "installer.yml", self.rooted)
        self.headers = _entries(self.root, headers, self.layout, known, self.rooted)
        self.sources = _entries(self.root, sources, self.layout, known, self.rooted)

        # The version lives in the code, in the @version tag of the first
        # header's file comment, so it cannot drift from what it describes. A
        # version written in installer.yml is only a fallback, for a header that
        # does not carry one.
        declared = data.get("version")
        self.version = _header_version(self.root, self.headers) or (
            str(declared) if declared is not None else ""
        )

        # Every once file lands in the project's folder, and a to is another
        # place there. From 2.1.0, rooted, an entry may be its path alone,
        # landing at that path, and a from left out is the same path as its to.
        # Before, each is a mapping with a from, and a to left out meant the
        # file's name alone, at the top.
        self.once = [self._once_file(entry) for entry in data.get("once") or []]

        # Which folders go on the IDE's include path. Worked out from where the
        # headers land, see include_dirs, unless the manifest says. Each is
        # written into the project's own files as it stands, so it is checked.
        declared = install.get("include_dirs")

        if declared and not isinstance(declared, list):
            raise ManifestError("install.include_dirs is a list of folders inside the library, such as [src].")

        self.declared_include_dirs = [include_folder(d) for d in declared] if declared else None
        # Defines the whole project is built with, for a library that reads its
        # settings through one, as littlefs reads LFS_DEFINES. The whole project
        # and not only the library's own files, because a define can change
        # what its header declares, and every file including it has to agree.
        # Checked in load(), since each is written into the user's project as
        # it stands.
        declared = install.get("defines") or []

        if not isinstance(declared, list):
            raise ManifestError("install.defines should be a list, one define per line.")

        self.defines = [str(d).strip() for d in declared]

        # Parts the user chooses at install. None is chosen until choose() says,
        # so whatever installs a library without asking, an older caller or a
        # test, gets it without its options rather than with all of them.
        options = data.get("options") or {}

        if not isinstance(options, dict):
            raise ManifestError("options should name each option, with what it brings under it.")

        self.options = {}

        for name, value in options.items():
            if not OPTION_NAME.match(str(name)):
                raise ManifestError(
                    f"options has {name!r}. Name an option in lower case letters, digits, _ and -, "
                    "starting with a letter, since it is typed after --with."
                )

            self.options[str(name)] = Option(self.root, str(name), value, self.layout, known, self.rooted)

        self.chosen = []
        # Copied verbatim alongside the code. The Apache licence wants both of
        # these to travel with it, and NOTICE is what carries the attribution.
        # Extras are optional by nature, so an entry that matches nothing is a
        # warning rather than a refusal. Silence was the old behaviour and it
        # made a mistyped pattern look exactly like a working one.
        self.extras = []
        # Extras with a root, from 2.1.0: the library's own files in the
        # project's folder, such as its tools, written again on every install as
        # every extra is, and taken out by an uninstall.
        self.placed = []
        self.empty_extras = []

        for item in data.get("extras") or ["LICENSE.md", "NOTICE"]:
            if isinstance(item, dict):
                self._extra(item, known)
                continue

            _check_source(item, "extras")
            found = expand(self.root, item, known)

            for path in found:
                self.extras.append(FileEntry(path, _placed(path, self.layout, item)))

            if not found and item not in ("LICENSE.md", "NOTICE"):
                self.empty_extras.append(str(item))

        # Commands run once the files are in place. Each is asked about first.
        steps = data.get("run") or []

        if not isinstance(steps, list):
            raise ManifestError("run should be a list of steps, each with a label and a script or a command.")

        self.run = [RunStep(step, self.rooted) for step in steps]
        labels = [step.label for step in self.run]
        twice = sorted({label for label in labels if labels.count(label) > 1})

        if twice:
            raise ManifestError(f"run has two steps labelled {', '.join(twice)}. Give each its own label.")

        self._check_scripts()

        # Where the library came from, filled in by whoever fetched it: GitHub,
        # with the ref asked for and the commit it was, or a zip or a folder.
        self.origin = {}

        # Last, so the target sees the library as read: a section of its own,
        # such as zephyr for a Zephyr application, comes from here.
        target.current.read_manifest(self, data)

    def _extra(self, item, known):
        """
        An extra written as a mapping, from 2.1.0: a file, a folder or a
        wildcard of the library, with a to, a place in the library's folder, or
        a root, one in the project's, where it is the library's own, such as
        its tools. A file lands at the place itself; the files of a folder keep
        their path below it; those a wildcard matches keep their names, under
        it. from may be left out when it is the same path: "root: tools" takes
        the library's tools/ to the project's tools/.
        """
        if not self.rooted:
            raise ManifestError(
                f"extras has {item!r}. An extra with a to or a root is new in 2.1.0: ask for it under "
                f"requires, as {target.current.requires_key}: 2.1.0."
            )

        if "to" in item and "root" in item:
            raise ManifestError(
                f"extras has {item!r}, with both a to and a root. An extra lands in one place: a to is one "
                "in the library's folder, and a root one in the project's."
            )

        key = "root" if "root" in item else "to"
        place = item.get(key)
        source = item.get("from") or place

        if not place:
            raise ManifestError(
                f"extras has {item!r}. An extra written as a mapping has a to, a place in the library's "
                "folder, or a root, a place in the project's, and a from when the library's path is not "
                "the same."
            )

        _check_source(source, "extras")
        place = self._landing(place, source, "extras", key, in_project=key == "root")
        source = str(source).replace("\\", "/").rstrip("/")
        found = expand(self.root, source, known)

        for path in found:
            if is_pattern(source):
                landing = f"{place}/{path.name}"
            elif path.as_posix() == source:
                landing = place
            else:
                landing = f"{place}/{path.relative_to(source).as_posix()}"

            (self.placed if key == "root" else self.extras).append(FileEntry(path, landing))

        if not found:
            self.empty_extras.append(source)

    def _once_file(self, entry):
        """A once entry, as the file of the library it copies and where in the project that lands."""
        if isinstance(entry, dict) and "root" in entry:
            raise ManifestError(
                f"once has {entry!r}. A once file always lands in the project's folder, so another place "
                "there is a to. A root is for an extra, which would otherwise go in the library's folder."
            )

        if not self.rooted and not (isinstance(entry, dict) and entry.get("from")):
            raise ManifestError(f"once has {entry!r}. Each entry is a mapping with a from, and a to if wanted.")

        given = (entry.get("from") or entry.get("to")) if isinstance(entry, dict) else entry

        if not given:
            raise ManifestError(f"once has {entry!r}. Each entry is a path, or a mapping with a from and a to.")

        _check_source(given, "once")
        source = str(given).replace("\\", "/")
        to = entry.get("to") if isinstance(entry, dict) else None

        if not to:
            return OnceFile(Path(source), source if self.rooted else Path(source).name)

        if not self.rooted:
            return OnceFile(Path(source), str(to).replace("\\", "/"))

        return OnceFile(Path(source), self._landing(to, source, "once", "to", in_project=True))

    def _landing(self, place, source, where, key, in_project):
        """
        A to or a root, checked and written with forward slashes: one place,
        never a wildcard, inside the folder it names a place in, the project's
        or the library's, and so never with {library}.
        """
        folder = "the project's folder" if in_project else "the library's folder"

        if is_pattern(place):
            raise ManifestError(f"{where} puts {source!r} at {place!r}. A {key} is one place, never a wildcard.")

        if in_library(place)[0]:
            if not in_project:
                why = f"A to is a place in the library's folder already, so leave {LIBRARY} out."
            elif where == "extras":
                why = "A root is a place in the project's folder: for one in the library's, give it a to."
            else:
                why = "A once file is the project's own, so it lands in the project's folder, never the library's."

            raise ManifestError(f"{where} puts {source!r} at {place!r}. {why}")

        reason = unsafe_path(place)

        if reason:
            raise ManifestError(f"{where} puts {source!r} at {place!r}, outside {folder}: {reason}.")

        return str(place).replace("\\", "/").rstrip("/")

    def _check_scripts(self):
        """
        A 2.1.0 manifest's run step starts a script the install itself puts in
        place: an extra with a root or a once file, in the project's folder, or a
        file of the library's folder named with {library}. Anything else would
        not be there to run, and saying so now beats a failed step later.
        """
        if not self.rooted:
            return

        in_project = {e.destination for e in self.placed + self.once}
        in_library = {e.destination for e in self.extras + self.all_code_files}

        for step in self.run:
            if step.script is None:
                continue

            where = in_library if step.in_library else in_project

            if step.script.as_posix() not in where:
                raise ManifestError(
                    f"run.{step.label} starts {step.written}, which nothing in this installer.yml puts there, "
                    "so it would not be there to run. A path in run starts at the project's folder: copy "
                    "the script there with an extra's root or a once file, or name it in the library's folder "
                    f"as {LIBRARY}/..."
                )

    def choose(self, names):
        """Take these options in this install, and no others."""
        unknown = [name for name in names if name not in self.options]

        if unknown:
            raise ManifestError(f"{self.name} has no option called {', '.join(unknown)}.")

        self.chosen = [name for name in self.options if name in names]

    def _chosen_files(self, kind):
        """The headers or the sources of the options taken."""
        return [entry for name in self.chosen for entry in getattr(self.options[name], kind)]

    @property
    def code_files(self):
        """
        Headers and sources together, with those of the options taken. These
        are replaced on every install.
        """
        return self.headers + self.sources + self._chosen_files("headers") + self._chosen_files("sources")

    @property
    def all_code_files(self):
        """Every code file the manifest names, whatever is chosen, for checking it."""
        return self.headers + self.sources + [e for option in self.options.values() for e in option.code_files]

    @property
    def include_dirs(self):
        """
        The folders that go on the IDE's include path.

        Where the headers land, those of the options taken included, unless
        the manifest names them. An option that is not taken adds nothing, so
        no include path points at a folder that was never installed.
        """
        if self.declared_include_dirs:
            return list(self.declared_include_dirs)

        return sorted({entry.folder for entry in self.headers + self._chosen_files("headers")}) or ["."]

    @property
    def dependencies(self):
        """The libraries this one needs, with those the options taken bring."""
        return self.requires.libraries + [d for name in self.chosen for d in self.options[name].libraries]

    @property
    def build_sources(self):
        """
        File names the IDE has to compile, as they end up in the install folder.

        A template can be a .c file, a port layer the user fills in, and that
        file has to reach the build like any other source. Leaving it out is
        silent: the file exists, the project looks right, and the link fails
        with undefined references.

        Only files a compiler can actually take are listed, and that filter
        covers `sources` as well as `once`. Keil and IAR name every file in the
        project explicitly, so anything that gets in here shows up in the IDE's
        file tree and is handed to the compiler. A README that reached it by way
        of a mistyped manifest would be visible, confusing, and a build error.
        """
        # A once file of a 2.0.0 manifest is the project's, in the project's
        # folder, and the project builds it or not, as it does its own files.
        once = [] if self.modern else list(self.once)

        return [
            entry.destination
            for entry in list(self.sources) + self._chosen_files("sources") + once
            if Path(entry.destination).suffix.lower() in COMPILED
        ]

    @property
    def required_files(self):
        """
        Every repository path the manifest promises, those of every option
        included, chosen or not: its code, its once files, the scripts its run
        steps start, and the installer.yml it carries for a library that has
        none. Extras are optional. A 2.1.0 step's script names a place in the
        project, not the repository, and _check_scripts sees to it instead.
        """
        carried = [d.manifest for d in self.requires.libraries + [
            d for option in self.options.values() for d in option.libraries] if d.manifest is not None]
        scripts = [step.script for step in self.run if step.script is not None and not step.rooted]

        return ([entry.source for entry in self.all_code_files] + [e.source for e in self.once]
                + scripts + carried)

    def present_extras(self):
        """Extras to copy. Already expanded, so every one of these exists."""
        return list(self.extras)

    def clashes(self):
        """
        Files claimed as both code and once.

        Code is overwritten on every install and a once file never is, so one
        claimed as both would have the user's edits quietly replaced while the
        output still reported it as kept. A wildcard that happens to sweep up
        the config header is the usual way this happens.
        """
        code = {entry.source.as_posix() for entry in self.all_code_files}

        return sorted(code & {entry.source.as_posix() for entry in self.once})

    def shared_option_files(self):
        """
        Files an option brings that the library, or another option, also lists.

        A file belongs to one place. One that is the library's and an option's
        both would be removed by the update that turns the option off, while the
        library still needs it.
        """
        owner = {entry.source.as_posix(): None for entry in self.headers + self.sources}
        shared = set()

        for name, option in self.options.items():
            for entry in option.code_files:
                path = entry.source.as_posix()

                if path in owner and owner[path] != name:
                    shared.add(path)

                owner.setdefault(path, name)

        return sorted(shared)

    def missing_files(self):
        """Files the manifest promises but the repository does not contain."""
        return [p for p in self.required_files if not (self.root / p).is_file()]

    def summary(self):
        """A one line description of what this library is, for listings."""
        parts = [self.kind]

        if self.category and self.category != self.kind:
            parts.append(self.category)

        return " / ".join(parts)

    def __repr__(self):
        return f"Manifest({self.name} {self.version} {self.kind})"


def _warnings(manifest):
    """Things worth saying out loud that are not bad enough to refuse the install."""
    found = []

    if manifest.kind not in KINDS:
        found.append(f"kind '{manifest.kind}' is not one of: {', '.join(KINDS)}")

    if manifest.category and manifest.category not in CATEGORIES:
        found.append(f"category '{manifest.category}' is not one of: {', '.join(CATEGORIES)}")

    found.extend(target.current.warnings(manifest))

    if manifest.layout not in LAYOUTS:
        found.append(f"install.layout '{manifest.layout}' is not one of: {', '.join(LAYOUTS)}")

    for entry in manifest.empty_extras:
        found.append(f"extras entry '{entry}' matched no file")

    for name, option in manifest.options.items():
        if not option.description:
            found.append(f"option '{name}' has no description, so the question about it is only its name")

    return found


def _escapes(destination):
    """
    Whether a destination would write outside the folder it was given.

    A manifest is downloaded from the internet before any of it is trusted, so a
    "to" of "../../Core/Src/main.c" has to be caught rather than obeyed.
    """
    text = str(destination)

    # A leading slash has to count here. Windows does not call "/etc/passwd"
    # absolute, because it has no drive letter, but it still resolves to the
    # root of the current drive rather than to anywhere inside the folder.
    if text.startswith(("/", "\\")):
        return True

    return Path(text).is_absolute() or ".." in Path(text).parts


def _within_root(path, root):
    """Whether a resolved path is root or inside it. 3.8 has no is_relative_to."""
    try:
        Path(path).relative_to(root)
    except ValueError:
        return False

    return True


def manifest_path(folder):
    """
    The manifest in a folder: installer.yml, or library.yml in a release from
    before the rename. None when it holds neither.
    """
    for name in MANIFEST_NAMES:
        path = Path(folder) / name

        if path.is_file():
            return path

    return None


def load(library_root, strict=False, known=None):
    """
    Read the installer.yml at the root of a library repository.

    Args:
        library_root: the folder holding installer.yml, or library.yml in a release from
            before the rename.
        strict: treat unknown kinds and categories as errors. Useful in the
            library author's own CI, too fussy for a user installing something.
        known: every path in the repository, when the files are not on disk yet.
            Folder and wildcard entries are matched against this instead.

    Returns:
        A Manifest.

    Raises:
        ManifestError, with a message aimed at a human, whenever the manifest is
        absent, malformed, or promises files that are not there.
    """
    root = Path(library_root).resolve()
    path = manifest_path(root)

    if path is None:
        raise ManifestError(f"No {MANIFEST_NAME} in {root}, so there is nothing that says how to install it.")

    try:
        data = yamlreader.parse(path.read_text(encoding="utf-8"))
    except yamlreader.YamlError as error:
        raise ManifestError(f"{path} is not valid YAML: {error}") from error

    if not isinstance(data, dict):
        raise ManifestError(f"{path} should hold a mapping of settings, not a bare value.")

    # Before anything else is read, since a manifest for a newer installer may
    # not even have the fields this one expects.
    check_installer(data)

    if "name" not in data:
        raise ManifestError(f"{path} is missing the required 'name' field.")

    # headers and sources, under files or, from 2.1.0, on their own.
    if not any(key in data for key in ("files", "headers", "sources")):
        raise ManifestError(f"{path} is missing the required 'files' field, or headers and sources of its own.")

    manifest = Manifest(root, data, known)

    if not manifest.code_files:
        raise ManifestError(f"{path} lists no headers and no sources, so there is nothing to install.")

    missing = manifest.missing_files()
    if missing:
        listed = ", ".join(str(p) for p in missing)
        raise ManifestError(f"{path} lists files that do not exist in the repository: {listed}")

    # Always refused, never merely warned about. A manifest can arrive over the
    # network, and a destination like "../../Core/Src/main.c" would write into
    # the user's own code rather than the folder they agreed to.
    escaping = [
        entry.destination
        for entry in manifest.all_code_files + manifest.once + manifest.placed
        if _escapes(entry.destination) or unsafe_path(entry.destination)
    ]

    # Two files of the code that land in one place, which flat does to two of
    # one name in different folders: the second would quietly replace the
    # first. Checked for the files installed together, the library's and each
    # option's, since two options may well bring a port.c each. One file listed
    # twice, by a wildcard and by name, is no clash. From 2.1.0 an extra's to
    # can put it anywhere in the library's folder, so the extras are in each.
    base = manifest.headers + manifest.sources
    always = manifest.extras if manifest.rooted else []

    for group in [base] + [base + option.code_files for option in manifest.options.values()]:
        sources = {}

        for entry in group + always:
            sources.setdefault(entry.destination, set()).add(entry.source.as_posix())

        clashing = sorted(landing for landing, found in sources.items() if len(found) > 1)

        if clashing:
            hint = "" if manifest.rooted else ", or keep every path with install.layout: mirror"
            raise ManifestError(
                f"{path} lists two files that land at {', '.join(clashing)} in the library's folder, so one "
                f"would replace the other. Give one a to of its own{hint}."
            )

    # A file found where the manifest says, that is a link to somewhere else: a
    # folder or a zip can hold one, and following it would copy a file from
    # outside the library.
    for source in manifest.required_files + [entry.source for entry in manifest.extras + manifest.placed]:
        try:
            outside = not _within_root((root / source).resolve(), root)
        except OSError:
            outside = True

        if outside:
            raise ManifestError(
                f"{path} lists {Path(source).as_posix()}, which leads outside the library, so it is "
                "never read. A link to a file elsewhere has to be replaced by the file itself."
            )

    destinations = [entry.destination for entry in manifest.once]
    twice = sorted({d for d in destinations if destinations.count(d) > 1})

    if twice:
        raise ManifestError(f"{path} lists two once files that both land in {', '.join(twice)}.")

    # An extra with a root is written on every install, a once file never is,
    # so one place cannot be both; nor two extras.
    landings = [entry.destination for entry in manifest.placed]
    twice = sorted({d for d in landings if landings.count(d) > 1 or (manifest.modern and d in destinations)})

    if twice:
        raise ManifestError(f"{path} lists two files that both land in the project at {', '.join(twice)}.")

    shared = manifest.shared_option_files()
    if shared:
        raise ManifestError(
            f"{path} lists these both in an option and somewhere else, so turning the option "
            f"off would remove a file still needed: " + ", ".join(shared)
        )

    clashing = manifest.clashes()
    if clashing:
        raise ManifestError(
            f"{path} lists these as both code and configuration, so an update would "
            f"overwrite the user's settings: " + ", ".join(clashing) + ". Narrow the "
            f"pattern, or list the files one by one."
        )

    if escaping:
        raise ManifestError(
            f"{path} sends files outside the install folder, which is never allowed: "
            + ", ".join(escaping)
        )

    # Refused like an escaping path, and for the same reason: what is written
    # here lands in the user's project files as it stands.
    for define in manifest.defines:
        if not DEFINE.match(define):
            raise ManifestError(
                f"{path}: install.defines has {define!r}. Write a define as NAME or "
                "NAME=value, using letters, digits and _ . + - / only."
            )

    names = [define_name(d) for d in manifest.defines]
    twice = sorted({name for name in names if names.count(name) > 1})

    if twice:
        raise ManifestError(f"{path}: install.defines sets {', '.join(twice)} more than once.")

    problems = _warnings(manifest)
    if problems and strict:
        raise ManifestError(f"{path}: " + "; ".join(problems))

    manifest.warnings = problems

    return manifest
