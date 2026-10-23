"""
What lib-installer knows about PlatformIO: what a PlatformIO project is.

A library goes into the project's lib folder, which PlatformIO's Library
Dependency Finder searches for every framework it builds with, and where one
library finds another: measured, a library in lib/ including the header of
another in lib/ builds, so what a library needs goes there too. Each gets a
library.json (library_json.py), and the defines it needs go into
platformio.ini (ini.py), since a define in library.json reaches the library's
own files and nothing else. So do the build flags a manifest asking for 4.0.0
gives under pio.project.build_flags.
"""

import re
from pathlib import Path

from . import ini, library_json
from ..core import titles
from ..core.manifest import ManifestError, asks_for, section_keys, unknown_warnings
from ..core.target import INFO, MANUAL, WARN, Finding, Outcome, Platform

LIB = "lib"

# The release from which the pio section gives everything under where it
# goes: project, the project's platformio.ini, and library, the library's own
# library.json. A manifest asking for less keeps the meanings it was written
# for, and one asking for it stops an installer from before, which would pass
# the new keys by.
RENAMED = (4, 0, 0)

# The keys of the pio section of a manifest asking for 4.0.0, and of its two
# parts: what each writes, and into which file.
KEYS = ("project", "library")
PROJECT_KEYS = ("build_flags",)
LIBRARY_KEYS = ("frameworks", "platforms", "dependencies")

# The keys of the pio section of a manifest asking for less.
BEFORE_KEYS = LIBRARY_KEYS

# A framework or a platform as platformio.ini names it: arduino, espidf,
# stm32cube, espressif32, ststm32, native.
_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

# A library of the PlatformIO Registry: owner/name, with @version when one is needed.
_REGISTRY = re.compile(r"^(?:[A-Za-z0-9_.-]+/)?[A-Za-z0-9 _.+-]+(?:@\S+)?$")

# A line of build_flags: words of letters, digits and _ . + - / = , :, the
# first an option, such as -O2, -Wl,-u,_printf_float or -I include. It goes
# into platformio.ini as it stands, and PlatformIO hands it to the compiler
# and the linker of every file of the build, so nothing platformio.ini, SCons
# or a shell would read as more than a flag gets through: no ; or #, which
# start a comment, no quote, no $, which SCons expands, and no ! at the start,
# which has PlatformIO run a command.
_FLAG = re.compile(r"^-[A-Za-z0-9_.+=,:/-]+(?: +[A-Za-z0-9_.+=,:/-]+)*$")


def _plain(value, key):
    """
    What goes into library.json, refused with a title or a note: JSON has no
    comments to write them as.
    """
    if isinstance(value, dict) or (isinstance(value, list) and any(isinstance(entry, dict) for entry in value)):
        raise ManifestError(
            f"{key} has a title or a note, which library.json, being JSON, has no room for. Give a plain list."
        )


def _names(data, key, where="pio"):
    """frameworks or platforms: a list of names, or [] for any."""
    value = data.get(key)

    if value is None or value == "*" or value == ["*"]:
        return []

    if isinstance(value, str):
        value = [part.strip() for part in value.split(",")]

    if where != "pio":
        _plain(value, f"{where}.{key}")

    if not isinstance(value, list) or not all(_NAME.match(str(name)) for name in value):
        raise ManifestError(
            f"{where}.{key} is a list of names as platformio.ini writes them, such as "
            f"{'[arduino, espidf]' if key == 'frameworks' else '[espressif32, ststm32]'}, or \"*\" for any."
        )

    return [str(name) for name in value]


def _dependencies(value, key):
    """The libraries of the PlatformIO Registry it needs, as library.json writes them: {"owner/name": "version"}."""
    value = value or []

    if key != "pio.dependencies":
        _plain(value, key)

    if not isinstance(value, list) or not all(_REGISTRY.match(str(d).strip()) for d in value):
        raise ManifestError(
            f"{key} is a list of PlatformIO Registry libraries, such as "
            "[bblanchon/ArduinoJson@^7.0.0]: owner/name, and @version when one is needed."
        )

    # * for any version.
    found = {}

    for entry in value:
        name, _, version = str(entry).strip().partition("@")

        # One version each: a second would take the first's place unseen.
        if name in found:
            raise ManifestError(f"{key} has {name} more than once. Give it once, with the version that will do.")

        found[name] = version or "*"

    return found


class Flag:
    """A line of pio.project.build_flags, and the title of its group and its note."""

    def __init__(self, text, key):
        line = text.strip() if isinstance(text, str) else None

        if not line or not _FLAG.match(line):
            raise ManifestError(
                f"{key} has {text!r}. Give a flag as the compiler takes it, such as -O2, -Wl,-u,_printf_float "
                "or -I include, in letters, digits and _ . + - / = , : only."
            )

        self.text = line
        self.group = None
        self.note = None


def _refuse_moved(data):
    """
    In a manifest asking for 4.0.0, the keys of the pio section from before,
    each refused with where it went.
    """
    for key in LIBRARY_KEYS:
        if key in data:
            raise ManifestError(
                f"pio.{key} is pio.library.{key} from 4.0.0: what goes into the library's library.json is "
                "under library."
            )


def _refuse_new(data):
    """
    In a manifest asking for less than 4.0.0, the keys of the pio section new
    in it, refused: an installer from before would pass them by.
    """
    for key in KEYS:
        if key in data:
            raise ManifestError(f"pio.{key} is new in 4.0.0: ask for it under requires, as lib_installer: 4.0.0.")


class PioPart:
    """
    The pio section of installer.yml, with what it leaves out filled in.
    renamed is whether the manifest asks for 4.0.0, whose pio section gives
    what goes into the project's platformio.ini under project, and what goes
    into the library's library.json under library.
    """

    def __init__(self, data, renamed=False):
        if data is None:
            data = {}

        if not isinstance(data, dict):
            raise ManifestError("pio should hold project and library." if renamed
                                else "pio should hold frameworks, platforms and dependencies.")

        # The keys of the release the manifest asks for. A key written as the
        # other release has it is refused with the name to use, rather than
        # read wrongly.
        if renamed:
            _refuse_moved(data)
            project = titles.part(data.get("project"), "pio.project", PROJECT_KEYS)
            own = titles.part(data.get("library"), "pio.library", LIBRARY_KEYS)
            where = "pio.library"
        else:
            _refuse_new(data)
            project = {}
            own = data
            where = "pio"

        # The flags it gives every file of the build, from 4.0.0: written after
        # its defines in its block of build_flags, each group under its title
        # and a flag with its note, as comments of platformio.ini.
        key = "pio.project.build_flags"
        self.build_flags = titles.listed(project.get("build_flags"), key, lambda text: Flag(text, key))
        flags = [flag.text for flag in self.build_flags]
        twice = sorted({flag for flag in flags if flags.count(flag) > 1})

        if twice:
            raise ManifestError(f"{key} has {', '.join(twice)} more than once.")

        # What goes into its library.json.
        self.frameworks = _names(own, "frameworks", where)
        self.platforms = _names(own, "platforms", where)
        self.dependencies = _dependencies(own.get("dependencies"), f"{where}.dependencies")


def _platform(text):
    """A platform from platformio.ini as a plain name: espressif32 from platformio/espressif32@^6.5."""
    name = text.split("@")[0].strip()

    return None if "://" in name or name.endswith(".git") else name.split("/")[-1]


class PlatformIO(Platform):
    """A PlatformIO project: platformio.ini, src/, and lib/ for its libraries."""

    platform = "pio"
    legacy = "pio-installer"
    label = "PlatformIO"
    project = "PlatformIO project"
    no_project = "No platformio.ini here, so nothing was registered."
    no_project_hint = "Run this from your project's folder, the one holding platformio.ini."

    def __init__(self, version):
        self.version = version

    def legacy_files(self, project_root):
        """platformio.ini, where pio-installer wrote its blocks."""
        return [Path(project_root) / ini.NAME]

    def managed_files(self, project_root, library):
        """platformio.ini, which this edits, and which a once file must never be."""
        return [self.record_name, ini.NAME]

    def default_folder(self, library):
        """Libraries go into lib/, which PlatformIO searches for every framework."""
        return f"{LIB}/{library.name}"

    def read_manifest(self, manifest, data):
        renamed = asks_for(data, RENAMED)
        manifest.pio = PioPart(data.get("pio"), renamed)
        # A key the section does not have, such as a misspelt frameworks.
        manifest.pio.unknown = section_keys(data, "pio", KEYS if renamed else BEFORE_KEYS)

    def warnings(self, manifest):
        return unknown_warnings("pio", getattr(getattr(manifest, "pio", None), "unknown", []))

    def read_requirements(self, requirements, data):
        """Hardware the library uses, named to the user: I2C, or I2C, 400 kHz."""
        found = []

        for entry in data.get("peripherals") or []:
            if isinstance(entry, dict):
                note = entry.get("note")
                found.append(str(entry.get("type", "")).upper() + (f", {note}" if note else ""))
            else:
                found.append(str(entry).upper())

        requirements.peripherals = found

    def requirements_empty(self, requirements):
        return not requirements.peripherals

    def check(self, library, project_root):
        """What the project is missing for this library. Never stops an install."""
        path = Path(project_root) / ini.NAME

        try:
            text = ini.read(path)
        except (OSError, UnicodeDecodeError):
            return [Finding(WARN, "No platformio.ini here",
                            "Run this from your PlatformIO project's folder, or give it with --project.")]

        findings = []
        wanted = library.pio

        # PlatformIO leaves a library a build cannot use out of that build
        # without a word, and its header is then simply not found.
        for env, (frameworks, platform) in ini.environments(text).items():
            missing = [f for f in frameworks if wanted.frameworks and f not in wanted.frameworks]
            plain = _platform(platform) if platform else None

            if missing:
                findings.append(Finding(
                    WARN, f"[env:{env}] builds with {', '.join(missing)}, which {library.name} does not list, "
                    "so PlatformIO leaves it out of that build",
                    f"{library.name} lists: {', '.join(wanted.frameworks)}.",
                ))
            elif wanted.platforms and plain and plain not in wanted.platforms:
                findings.append(Finding(
                    WARN, f"[env:{env}] builds for {plain}, which {library.name} does not list, "
                    "so PlatformIO leaves it out of that build",
                    f"{library.name} lists: {', '.join(wanted.platforms)}.",
                ))

        if library.defines:
            findings.append(Finding(INFO, f"{', '.join(library.defines)} goes into build_flags in platformio.ini"))

        if wanted.build_flags:
            flags = [flag.text for flag in wanted.build_flags]
            findings.append(Finding(INFO, f"{', '.join(flags)} {'go' if len(flags) > 1 else 'goes'} into "
                                    "build_flags in platformio.ini"))

        for name, version in wanted.dependencies.items():
            findings.append(Finding(INFO, f"Needs {name}{'' if version == '*' else ' ' + version}, from the "
                                    "PlatformIO Registry", "PlatformIO installs it by itself at the next build."))

        for peripheral in library.requires.peripherals:
            findings.append(Finding(INFO, f"Needs {peripheral}", "Set it up in your code."))

        return findings

    def integrate(self, project_root, library, destination, only=None, dropped=(), dropped_defines=()):
        """
        Write the library's library.json, and its defines and build flags into
        platformio.ini.

        dropped needs nothing here: library.json names the files of the new
        version only. dropped_defines needs nothing either: the block of
        defines is written again from the new manifest, so one that has gone is
        no longer in it.
        """
        outcomes = [library_json.write(library, destination)]
        outcome = ini.integrate(project_root, library)

        if outcome is not None:
            outcomes.append(outcome)

        try:
            in_lib = Path(destination).resolve().parent == (Path(project_root) / LIB).resolve()
        except OSError:
            in_lib = True

        if not in_lib:
            outcomes.append(Outcome(
                "lib_extra_dirs", MANUAL,
                f"PlatformIO looks for libraries in {LIB}/, and {library.name} is not in it.",
                [f"Add its folder's parent to lib_extra_dirs in the [env] section of {ini.NAME}, "
                 f"or install it into {LIB}/ with --dir {LIB}/{library.name}."],
            ))

        return outcomes

    def uninstall(self, project_root, library):
        """Its library.json, and its defines and build flags, go before its files do."""
        library_json.remove(library)
        outcome = ini.uninstall(project_root, library.name)

        return [outcome] if outcome is not None else []
