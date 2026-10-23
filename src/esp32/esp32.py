"""
What lib-installer knows about ESP-IDF: what an ESP-IDF project is.

The core does everything a library needs whatever it is installed into. This
says the rest for ESP-IDF: the part of installer.yml only ESP-IDF reads, the
checks against the project's sdkconfig, and the integration, which makes the
library a component of the project (component.py) and adds what it needs to
the project's own files (project.py).
"""

import os
import re
from pathlib import Path

from . import component, project
from ..core import blocks, installer, titles
from ..core.manifest import ManifestError, asks_for, count_of, section_keys, unknown_warnings
from ..core.target import CHANGED, INFO, MANUAL, OK, WARN, Finding, Outcome, Platform

# The release from which the esp32 section gives every line it writes under
# where it goes: project, the project's own files, and library, the
# component's own folder, each list in groups under their titles when it
# likes. A manifest asking for less keeps the meanings it was written for,
# and one asking for it stops an installer from before, which would read the
# keys the old way.
RENAMED = (4, 0, 0)

# The keys of the esp32 section of a manifest asking for 4.0.0, and of its two
# parts: what each writes, and into which file.
KEYS = ("settings", "project", "library")
PROJECT_KEYS = ("conf", "cmake")
LIBRARY_KEYS = ("requires", "cmake")

# The keys of the esp32 section of a manifest asking for less.
BEFORE_KEYS = ("settings", "requires", "cmake")

# A Kconfig symbol as ESP-IDF writes them, without CONFIG_ in front.
SYMBOL = re.compile(r"^[A-Z0-9_]+$")

# A value a required symbol may be given in sdkconfig.defaults: y or n, a
# number, a hex number, or a string in quotes. Written into the file as it
# stands, so nothing else gets through.
VALUE = re.compile(r'^(?:y|n|-?[0-9]+|0x[0-9A-Fa-f]+|"[^"\\\n]*")$')

# Where a group of CMake lines goes: the component's own CMakeLists.txt,
# after idf_component_register(), where ${COMPONENT_LIB} is its library; the
# project's, above include(project.cmake), for what ESP-IDF reads as the
# project starts, such as EXTRA_COMPONENT_DIRS; or the project's, at its end,
# for what needs the project's own targets.
COMPONENT_PLACE = "component"
BEFORE_PROJECT = "before-project"
AFTER_PROJECT = "after-project"
PLACES = (COMPONENT_PLACE, BEFORE_PROJECT, AFTER_PROJECT)

# An ESP-IDF component's name, as it lands unquoted in REQUIRES: esp_timer,
# esp_driver_i2c, esp-tls.
COMPONENT = re.compile(r"^[A-Za-z0-9_.+-]+$")

# What a setting can be, as Kconfig names its types.
TYPES = ("bool", "int", "hex", "string")

_INT = re.compile(r"^-?[0-9]+$")
_HEX = re.compile(r"^0x[0-9A-Fa-f]+$")

symbol_of = component.symbol_of


def _symbol(text, where):
    """A symbol written in installer.yml, without CONFIG_ in front, or ManifestError."""
    found = str(text).strip()

    if found.startswith("CONFIG_"):
        found = found[len("CONFIG_"):]

    if not SYMBOL.match(found):
        raise ManifestError(
            f"{where} has {text!r}. Write a Kconfig symbol in capitals, digits and _, "
            "such as FREERTOS_HZ or CONFIG_FREERTOS_HZ."
        )

    return found


class Requirement:
    """
    A symbol the project has to have, and the value it needs:
    CONFIG_FREERTOS_HZ=1000, in sdkconfig.defaults. From requires.kconfig, or
    esp32.project.conf from 4.0.0, which key names.
    """

    def __init__(self, text, key="requires.kconfig"):
        name, _, value = str(text).partition("=")
        self.symbol = _symbol(name, key)
        self.value = value.strip() or "y"
        # The title of the group it is listed in, and its note, from 4.0.0.
        self.group = None
        self.note = None

        if not VALUE.match(self.value):
            raise ManifestError(
                f"{key} has {text!r}. Give a symbol, which is set to y, or "
                'SYMBOL=value, with y, n, a number, 0x and a hex number, or "text".'
            )

    @property
    def line(self):
        """The line in sdkconfig.defaults."""
        return f"CONFIG_{self.symbol}={self.value}"

    def __repr__(self):
        return f"Requirement({self.line})"


class Peripheral:
    """Hardware the library uses, for the user to give it in their code or menuconfig."""

    def __init__(self, data):
        data = data if isinstance(data, dict) else {"type": data}
        self.type = str(data.get("type", "")).lower()
        self.count = count_of(data.get("count", 1), f"requires.peripherals {self.type}")
        self.note = str(data.get("note", "") or "")

    def describe(self):
        many = f" x{self.count}" if self.count > 1 else ""
        detail = f", {self.note}" if self.note else ""

        return f"{self.type.upper()}{many}{detail}"


class Setting:
    """
    One setting of the library, a Kconfig symbol the user sets in menuconfig.

    Written into the component's Kconfig, so the C code reads it as
    CONFIG_<name> from sdkconfig.h. Everything is checked here, since all of
    it is written into a file Kconfig reads, and the manifest comes over the
    network.
    """

    def __init__(self, data):
        if not isinstance(data, dict):
            raise ManifestError("esp32.settings holds one entry per setting, each with a name and a type.")

        self.name = _symbol(data.get("name", ""), "esp32.settings")
        where = f"esp32.settings {self.name}"
        self.type = str(data.get("type", "")).lower()

        if self.type not in TYPES:
            raise ManifestError(f"{where} has type {data.get('type')!r}. Use one of: {', '.join(TYPES)}.")

        self.prompt_given = bool(data.get("prompt"))
        self.prompt = component.one_line(data.get("prompt") or self.name)
        self.help = [line.rstrip() for line in str(data.get("help") or "").strip().splitlines()]
        self.range = self._range(data.get("range"), where)

        if "default" not in data or data["default"] is None:
            raise ManifestError(f"{where} has no default. Every setting needs one, so it builds as it is.")

        self.default = self._value(data["default"], where)

    def _number(self, value, where):
        """An int or hex value as a number, for comparing with the range."""
        text = str(value).strip()

        if isinstance(value, bool) or not (_INT.match(text) or _HEX.match(text)):
            raise ManifestError(f"{where}: {value!r} is not a number.")

        return int(text, 0)

    def _range(self, value, where):
        """The smallest and largest the setting may be, or None."""
        if value is None:
            return None

        if self.type not in ("int", "hex"):
            raise ManifestError(f"{where} has a range, which only an int or a hex setting can have.")

        if not isinstance(value, list) or len(value) != 2:
            raise ManifestError(f"{where}: write the range as [smallest, largest].")

        low, high = (self._number(item, where) for item in value)

        if low > high:
            raise ManifestError(f"{where}: the range starts above where it ends.")

        return (low, high)

    def _value(self, value, where):
        """The default as Kconfig writes it."""
        if self.type == "bool":
            if value is True or str(value).lower() in ("y", "yes", "true"):
                return "y"

            if value is False or str(value).lower() in ("n", "no", "false"):
                return "n"

            raise ManifestError(f"{where}: the default of a bool is true or false, not {value!r}.")

        if self.type == "string":
            text = str(value)

            if "\n" in text:
                raise ManifestError(f"{where}: the default is one line of text.")

            return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'

        number = self._number(value, where)

        if self.range and not (self.range[0] <= number <= self.range[1]):
            raise ManifestError(f"{where}: the default {value} is outside its range.")

        return self.format(number)

    def format(self, number):
        """A number written the way this setting's type writes it."""
        return hex(number) if self.type == "hex" else str(number)

    @property
    def line(self):
        """The setting at its default, as a line of sdkconfig."""
        return f"CONFIG_{self.name}={self.default}"

    def __repr__(self):
        return f"Setting({self.line})"


def _components(value, key):
    """
    The ESP-IDF components the library's code uses, such as esp_timer, as key
    lists them, each once. They go into REQUIRES of its component, which is
    how ESP-IDF puts their headers on the library's include path.
    """
    value = value or []

    if not isinstance(value, list):
        raise ManifestError(f"{key} is a list of ESP-IDF components, such as [esp_timer].")

    found = []

    for entry in value:
        if isinstance(entry, dict):
            raise ManifestError(
                f"{key} has {entry!r}. It is a plain list of ESP-IDF components, such as [esp_timer], "
                "with no titles or notes."
            )

        name = str(entry).strip()

        if not COMPONENT.match(name):
            raise ManifestError(
                f"{key} has {entry!r}. Write an ESP-IDF component by its name, "
                "such as esp_timer or esp_driver_i2c."
            )

        if name not in found:
            found.append(name)

    return found


def _refuse_moved(data):
    """
    In a manifest asking for 4.0.0, the keys of the esp32 section from before,
    each refused with where it went.
    """
    moved = {
        "requires": "esp32.library.requires from 4.0.0: the ESP-IDF components the library's code uses. List "
                    "them there, under library and then requires.",
        "cmake": "esp32.project.cmake and esp32.library.cmake from 4.0.0: the lines of the project's "
                 "CMakeLists.txt under project, by their place, before-project or after-project, and those of "
                 "the component's own under library.",
    }

    for key, where in moved.items():
        if key in data:
            raise ManifestError(f"esp32.{key} is {where}")


def _refuse_new(data):
    """
    In a manifest asking for less than 4.0.0, the keys of the esp32 section new
    in it, refused: an installer from before would not read them, and would
    install the library without what they say.
    """
    for key in ("project", "library"):
        if key in data:
            raise ManifestError(f"esp32.{key} is new in 4.0.0: ask for it under requires, as lib_installer: 4.0.0.")


class Esp32Part:
    """
    The esp32 section of installer.yml, with what it leaves out filled in.
    renamed is whether the manifest asks for 4.0.0, whose esp32 section lists
    what it writes under where it goes: project, the project's own files, and
    library, the component's own folder, each list in groups under their
    titles when it likes.
    """

    def __init__(self, library, data, renamed=False):
        if data is None:
            data = {}

        if not isinstance(data, dict):
            raise ManifestError("esp32 should hold settings, project and library." if renamed
                                else "esp32 should hold requires, cmake and settings.")

        # The keys of the release the manifest asks for. A key written as the
        # other release has it is refused with the name to use, rather than
        # read wrongly.
        if renamed:
            _refuse_moved(data)
        else:
            _refuse_new(data)

        self.renamed = renamed
        settings = data.get("settings") or []

        if not isinstance(settings, list):
            raise ManifestError("esp32.settings is a list, one entry per setting.")

        self.settings = [Setting(entry) for entry in settings]
        names = [setting.name for setting in self.settings]
        twice = sorted({name for name in names if names.count(name) > 1})

        if twice:
            raise ManifestError(f"esp32.settings has {', '.join(twice)} more than once.")

        if renamed:
            self._read_parts(library, data)
        else:
            self._read_before(library, data)

    def _read_parts(self, library, data):
        """
        What a manifest asking for 4.0.0 writes, by where it goes: under
        project, into the project's sdkconfig.defaults and CMakeLists.txt, each
        in a block of the library's; under library, into its component's
        REQUIRES and CMakeLists.txt.
        """
        project = titles.part(data.get("project"), "esp32.project", PROJECT_KEYS)
        own = titles.part(data.get("library"), "esp32.library", LIBRARY_KEYS)

        # The symbols it sets in the project's sdkconfig.defaults. One given
        # twice is refused: the line read last would quietly undo the first.
        self.conf_key = "esp32.project.conf"
        self.conf = titles.listed(project.get("conf"), self.conf_key, lambda text: Requirement(text, self.conf_key))
        symbols = [entry.symbol for entry in self.conf]
        twice = sorted({name for name in symbols if symbols.count(name) > 1})

        if twice:
            raise ManifestError(f"{self.conf_key} has {', '.join(twice)} more than once.")

        self.requires = _components(own.get("requires"), "esp32.library.requires")

        # Lines of CMake: the project's, under before-project, above
        # include(project.cmake), and after-project, at its end; and the
        # component's own, after idf_component_register().
        self.cmake = titles.cmake_groups(project.get("cmake"), own.get("cmake"), "esp32",
                                         (BEFORE_PROJECT, AFTER_PROJECT), COMPONENT_PLACE)

        # From 4.0.0 each platform's settings are in its own section, so
        # requires.kconfig, which every platform read, is refused.
        if getattr(library.requires, "kconfig", None):
            raise ManifestError(
                "requires.kconfig is esp32.project.conf from 4.0.0: the symbols a library sets in the project's "
                "sdkconfig.defaults. List them there, under project and then conf."
            )

    def _read_before(self, library, data):
        """What a manifest asking for less than 4.0.0 writes, read the way it was written for."""
        self.conf_key = "requires.kconfig"
        self.conf = list(getattr(library.requires, "kconfig", []))
        self.requires = _components(data.get("requires"), "esp32.requires")

        # Lines of CMake the library needs beyond its files, by the place they
        # go, from 2.1.0: component, the component's CMakeLists.txt, after
        # idf_component_register(), or before-project and after-project, the
        # project's, above include(project.cmake) or at its end. Before,
        # labelled groups each with a where; and a plain list of lines, the
        # form from before 2.0.0: one group, in the component.
        self.cmake = blocks.groups(data.get("cmake"), "esp32.cmake", PLACES, COMPONENT_PLACE,
                                   rooted=getattr(library, "rooted", False))


def idf_components(name):
    """
    The folder of ESP-IDF's own component of this name, when there is one.

    Read from IDF_PATH, which ESP-IDF's own shell sets. A project component of
    the same name takes the place of ESP-IDF's in the build.
    """
    idf = os.environ.get("IDF_PATH")

    if not idf:
        return None

    path = Path(idf) / "components" / name

    return path if path.is_dir() else None


class Esp32(Platform):
    """An ESP-IDF project: CMakeLists.txt with include(project.cmake), main, and sdkconfig."""

    platform = "esp32"
    legacy = "esp32-installer"
    label = "ESP-IDF"
    project = "ESP-IDF project"
    no_project = "No ESP-IDF project was recognised here, so nothing was registered."
    no_project_hint = "Run this from your project's folder, the one holding CMakeLists.txt and main/."

    def __init__(self, version):
        self.version = version

    def legacy_files(self, project_root):
        """The project's files esp32-installer wrote its blocks into."""
        root = Path(project_root)

        return [root / project.CMAKELISTS, root / project.DEFAULTS, root / project.MAIN]

    def default_folder(self, library):
        """Libraries go into the project's components folder, where ESP-IDF finds them."""
        return f"{project.COMPONENTS}/{library.name}"

    def managed_files(self, project_root, library):
        """
        The project's files this edits or reads as the project's own, which a
        once file must never be.
        """
        return [self.record_name, project.CMAKELISTS, project.MAIN, project.SDKCONFIG, project.DEFAULTS]

    def read_manifest(self, manifest, data):
        renamed = asks_for(data, RENAMED)
        manifest.esp32 = Esp32Part(manifest, data.get("esp32"), renamed)
        # A key the section does not have, such as a misspelt settings, which
        # would take what it says with it unseen.
        manifest.esp32.unknown = section_keys(data, "esp32", KEYS if renamed else BEFORE_KEYS)

        # Each option's own groups of CMake lines, read now that the release
        # the manifest asks for, which says where they are, is known.
        for option in manifest.options.values():
            option.esp32_cmake = titles.option_cmake(option, "esp32", renamed, PLACES, COMPONENT_PLACE)

        # A label names one group, among the library's and all its options'.
        labels = [group.label for group in manifest.esp32.cmake]

        for option in manifest.options.values():
            labels += [group.label for group in getattr(option, "esp32_cmake", [])]

        twice = sorted({label for label in labels if labels.count(label) > 1})

        if twice:
            raise ManifestError(f"esp32.cmake has two groups labelled {', '.join(twice)}, its "
                                "options' groups counted. Give each its own label.")

    def read_option(self, option, data):
        """
        An option's own esp32 part, kept for read_manifest(): its groups of
        CMake lines, written while it is taken, are where the release the
        manifest asks for says, which is known once the whole manifest is read.
        """
        part = data.get("esp32") if isinstance(data, dict) else None

        if part is not None and not isinstance(part, dict):
            raise ManifestError(f"options.{option.name}.esp32 should hold cmake, or project and library "
                                "from 4.0.0.")

        option.esp32_part = part or {}
        option.esp32_cmake = []

    def read_requirements(self, requirements, data):
        """The ESP-IDF part of requires: Kconfig symbols, and hardware."""
        kconfig = data.get("kconfig") or []

        if not isinstance(kconfig, list):
            raise ManifestError("requires.kconfig is a list of symbols, such as [FREERTOS_HZ=1000].")

        requirements.kconfig = [Requirement(entry) for entry in kconfig]
        requirements.peripherals = [Peripheral(entry) for entry in (data.get("peripherals") or [])]

    def requirements_empty(self, requirements):
        return not (requirements.kconfig or requirements.peripherals)

    def warnings(self, manifest):
        part = getattr(manifest, "esp32", None)
        prefix = symbol_of(manifest.name)
        found = []

        for setting in (part.settings if part else []):
            if not setting.name.startswith(prefix + "_"):
                found.append(f"esp32.settings {setting.name} does not start with {prefix}_, "
                             "so it may be taken by another component")

            if not setting.prompt_given:
                found.append(f"esp32.settings {setting.name} has no prompt, so menuconfig shows only its name")

        return found + unknown_warnings("esp32", getattr(part, "unknown", []))

    def _folder(self, library, project_root):
        """The library's folder: the one it is in already, or the one it is offered."""
        recorded = installer.installed_libraries(project_root).get(library.name)

        if isinstance(recorded, dict) and isinstance(recorded.get("folder"), str):
            return recorded["folder"]

        return self.default_folder(library)

    def check(self, library, project_root):
        """What the project is missing for this library. Never stops an install."""
        findings = []

        if project.find_project(project_root) is None:
            findings.append(Finding(
                WARN, "No CMakeLists.txt with include(.../project.cmake) here",
                "Run this from your ESP-IDF project's folder, or give it with --project.",
            ))

            return findings

        name = component.component_name(self._folder(library, project_root))
        own = idf_components(name)

        if own is not None:
            findings.append(Finding(
                WARN, f"ESP-IDF has a component called {name}, and this one would take its place",
                f"Install it into a folder of another name, such as --dir components/{name}_lib.",
            ))

        if library.esp32.conf and project.names_its_defaults(project_root):
            findings.append(Finding(
                WARN, "This project sets SDKCONFIG_DEFAULTS, so ESP-IDF may not read sdkconfig.defaults",
                f"Keep {project.DEFAULTS} in that list, or set the lines below in one of yours.",
            ))

        taken = project.user_defaults(project_root, library.name)
        ours = project.in_block(project_root, library.name)
        have = project.configured(project_root)

        for symbol, value, line in project.wanted(library):
            if symbol in taken and taken[symbol] == value:
                findings.append(Finding(
                    WARN, f"{project.DEFAULTS} already sets {line}, so the block has it commented out",
                    "Your line is the one used. Nothing to do.",
                ))
            elif symbol in taken:
                findings.append(Finding(
                    WARN, f"{project.DEFAULTS} sets CONFIG_{symbol}={taken[symbol]}, and {library.name} "
                    f"needs {value}. The block has it commented out",
                    "Your line is the one used. Change it if the library is to work.",
                ))
            elif symbol in have and have[symbol] != value:
                findings.append(Finding(
                    WARN, f"sdkconfig has CONFIG_{symbol}={have[symbol]}, and {library.name} needs {value}",
                    "sdkconfig is what ESP-IDF builds with. Set it in idf.py menuconfig.",
                ))
            elif ours.get(symbol) == value:
                findings.append(Finding(OK, f"{line} is in {project.DEFAULTS}"))
            else:
                findings.append(Finding(INFO, f"{line} goes into {project.DEFAULTS}"))

        for peripheral in library.requires.peripherals:
            findings.append(Finding(INFO, f"Needs {peripheral.describe()}",
                                    "Set it up in your code, or in idf.py menuconfig."))

        return findings

    def requires_of(self, library, project_root):
        """
        Every component the library's component needs: ESP-IDF's own from
        installer.yml, then the libraries it depends on, by the names their
        folders give them, as the record has them.
        """
        recorded = installer.installed_libraries(project_root)
        names = list(library.esp32.requires)

        for dependency in library.dependencies:
            entry = recorded.get(dependency.name)
            folder = entry.get("folder") if isinstance(entry, dict) else None
            name = component.component_name(folder) if isinstance(folder, str) else dependency.name

            if name not in names:
                names.append(name)

        return names

    def integrate(self, project_root, library, destination, only=None, dropped=(),
                  dropped_defines=()):
        """
        Make the library a component of the project, and give it what it needs.

        dropped and dropped_defines need nothing here: the component's files
        are written again from the new manifest on every install, so a file or
        a define that has gone is simply no longer in them.
        """
        outcomes = [component.write(library, destination, self.requires_of(library, project_root))]
        outcomes.extend(project.integrate(project_root, library, destination))

        return outcomes

    def uninstall(self, project_root, library):
        """
        Take the library out of the project's files, and delete the component
        files this wrote into its folder.
        """
        destination = library.destination
        defined = component.symbols(destination) if destination is not None else []
        name = component.component_name(destination) if destination is not None else None
        outcomes = project.uninstall(project_root, library.name, name)

        if destination is not None:
            saved = component.remove(destination)

            if saved is not None:
                outcomes.append(Outcome(
                    component.NAME, CHANGED,
                    f"Your lines in its CMakeLists.txt are saved, in {saved.name}.",
                    backup=saved,
                ))

        # A setting the user set in sdkconfig.defaults names a symbol that is
        # gone now. ESP-IDF only warns about it, but the line is the user's,
        # so it is named rather than taken out.
        lines = project.leftover(project_root, defined)

        if lines:
            outcomes.append(Outcome(
                project.DEFAULTS, MANUAL,
                f"{project.DEFAULTS} still sets what came with {library.name}, which ESP-IDF no "
                "longer knows. Take these lines out:",
                lines,
            ))

        return outcomes
