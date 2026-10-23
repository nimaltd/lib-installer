"""
What lib-installer knows about Zephyr: what a Zephyr application is.

The core does everything a library needs whatever it is installed into. This
says the rest for Zephyr: the part of installer.yml only Zephyr reads, the
checks against the application's prj.conf, and the integration, which makes
the library a Zephyr module of the application (module.py) and adds it to the
application's CMakeLists.txt and prj.conf (app.py).
"""

import re
from pathlib import Path

from . import app, module
from ..core import blocks, console, titles
from ..core.installer import InstallError
from ..core.manifest import ManifestError, asks_for, count_of, unknown_warnings
from ..core.target import CHANGED, INFO, MANUAL, OK, WARN, Finding, Outcome, Platform

# The release from which the zephyr section names the library's switch under
# symbol, where kconfig named it, and gives every line it writes under where
# it goes: project, the application's own files, and library, the library's
# own folder. A manifest asking for less keeps the meanings it was written
# for, and one asking for it stops an installer from before, which would read
# the keys the old way.
RENAMED = (4, 0, 0)

# The keys of the zephyr section of a manifest asking for 4.0.0, and of its
# two parts: what each writes, and into which file.
KEYS = ("symbol", "settings", "project", "library")
PROJECT_KEYS = ("conf", "sysbuild", "cmake")
LIBRARY_KEYS = ("kconfig", "conf", "cmake")

# The keys of the zephyr section of a manifest asking for less, which a key
# beside them is warned about in.
BEFORE_KEYS = ("kconfig", "defaults", "settings", "cmake", "sysbuild")

# A Kconfig symbol as Zephyr writes them, without CONFIG_ in front.
SYMBOL = re.compile(r"^[A-Z0-9_]+$")

# A value a required symbol may be given in prj.conf: y or n, a number, a hex
# number, or a string in quotes. Written into prj.conf as it stands, so nothing
# else gets through.
VALUE = re.compile(r'^(?:y|n|-?[0-9]+|0x[0-9A-Fa-f]+|"[^"\\\n]*")$')

# Where a group of CMake lines goes: the module's own CMakeLists.txt, inside
# its if(CONFIG_...); the application's, above find_package(Zephyr), for what
# Zephyr reads as it starts, such as EXTRA_CONF_FILE; or the application's, at
# its end, for what needs the application's own targets.
MODULE = "module"
BEFORE_ZEPHYR = "before-zephyr"
AFTER_ZEPHYR = "after-zephyr"
PLACES = (MODULE, BEFORE_ZEPHYR, AFTER_ZEPHYR)

# What a setting can be, as Kconfig names its types.
TYPES = ("bool", "int", "hex", "string")

_INT = re.compile(r"^-?[0-9]+$")
_HEX = re.compile(r"^0x[0-9A-Fa-f]+$")


def symbol_of(name):
    """The Kconfig symbol for a library name: EE24 for ee24, ONE_WIRE for one-wire."""
    return re.sub(r"[^A-Za-z0-9]", "_", str(name)).upper()


def _symbol(text, where):
    """A symbol written in installer.yml, without CONFIG_ in front, or ManifestError."""
    found = str(text).strip()

    if found.startswith("CONFIG_"):
        found = found[len("CONFIG_"):]

    if not SYMBOL.match(found):
        raise ManifestError(
            f"{where} has {text!r}. Write a Kconfig symbol in capitals, digits and _, "
            "such as I2C or CONFIG_I2C."
        )

    return found


class Requirement:
    """
    A symbol the application has to have, and the value it needs: CONFIG_I2C=y,
    in its Kconfig file. From requires.kconfig, or zephyr.project.conf from
    4.0.0, which key names.
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
        """The line in prj.conf."""
        return f"CONFIG_{self.symbol}={self.value}"

    def __repr__(self):
        return f"Requirement({self.line})"


class SysbuildSetting:
    """
    A setting of sysbuild, which builds MCUboot and the application as images
    of one build: SB_CONFIG_BOOTLOADER_MCUBOOT=y in the application's
    sysbuild.conf. Written as zephyr.sysbuild lists it, or zephyr.project.sysbuild
    from 4.0.0, which key names, without SB_CONFIG_.

    The value is written exactly as given. "${APP_DIR}/sign_key.pem" is expanded
    by sysbuild itself, when it writes each image's configuration, so it must
    reach sysbuild.conf as it is.
    """

    def __init__(self, text, key="zephyr.sysbuild"):
        name, _, value = str(text).partition("=")
        name = name.strip()

        if name.startswith("SB_CONFIG_"):
            name = name[len("SB_CONFIG_"):]

        self.symbol = _symbol(name, key)
        self.value = value.strip() or "y"
        self.group = None
        self.note = None

        if not VALUE.match(self.value):
            raise ManifestError(
                f"{key} has {text!r}. Give a symbol, which is set to y, or "
                'SYMBOL=value, with y, n, a number, 0x and a hex number, or "text".'
            )

    @property
    def line(self):
        """The line in sysbuild.conf."""
        return f"SB_CONFIG_{self.symbol}={self.value}"

    def __repr__(self):
        return f"SysbuildSetting({self.line})"


class Default:
    """
    A setting the library gives another symbol while its own is on, from
    zephyr.library.kconfig, or zephyr.defaults before 4.0.0, which key names:
    BT, which is set to y, or BT_L2CAP_TX_MTU=498. Written into the library's
    Kconfig as a configdefault, so it holds only while the library is switched
    on, and a line of the application's own Kconfig files that sets the same
    symbol wins.
    """

    def __init__(self, text, key):
        name, _, value = str(text).partition("=")
        self.symbol = _symbol(name, key)
        self.value = value.strip() or "y"
        self.group = None
        self.note = None

        if not VALUE.match(self.value):
            raise ManifestError(
                f"{key} has {text!r}. Give a symbol, which is set to y, or "
                'SYMBOL=value, with y, n, a number, 0x and a hex number, or "text".'
            )

    @property
    def line(self):
        """The setting as prj.conf would write it."""
        return f"CONFIG_{self.symbol}={self.value}"

    def __repr__(self):
        return f"Default({self.line})"


class Assignment:
    """
    A setting of the library's Kconfig fragment, from zephyr.library.conf:
    BT_AUTO_PHY_PERIPHERAL_2M, which is set to y, or BT_L2CAP_TX_MTU=247.
    Written into zephyr/<name>.conf in the library's folder, which Zephyr reads
    after prj.conf, so it is an assignment where a default is not: it sets a
    member of a choice, or a symbol Kconfig reads before the library's own, and
    wins over a line of prj.conf.
    """

    def __init__(self, text, key="zephyr.library.conf"):
        name, _, value = str(text).partition("=")
        self.symbol = _symbol(name, key)
        self.value = value.strip() or "y"
        self.group = None
        self.note = None

        if not VALUE.match(self.value):
            raise ManifestError(
                f"{key} has {text!r}. Give a symbol, which is set to y, or "
                'SYMBOL=value, with y, n, a number, 0x and a hex number, or "text".'
            )

    @property
    def line(self):
        """The line in the fragment."""
        return f"CONFIG_{self.symbol}={self.value}"

    def __repr__(self):
        return f"Assignment({self.line})"


class Peripheral:
    """Hardware the library uses, for the user to give it in the devicetree."""

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
    One setting of the library, a Kconfig symbol the user sets in prj.conf.

    Written into the library's Kconfig, so the C code reads it as
    CONFIG_<name>. Everything is checked here, since all of it is written into
    a file Kconfig reads, and the manifest comes over the network.
    """

    def __init__(self, data, library_symbol):
        if not isinstance(data, dict):
            raise ManifestError("zephyr.settings holds one entry per setting, each with a name and a type.")

        self.name = _symbol(data.get("name", ""), "zephyr.settings")
        where = f"zephyr.settings {self.name}"

        if self.name == library_symbol:
            raise ManifestError(f"{where} is the library's own symbol. Give the setting a name of its own.")

        self.type = str(data.get("type", "")).lower()

        if self.type not in TYPES:
            raise ManifestError(f"{where} has type {data.get('type')!r}. Use one of: {', '.join(TYPES)}.")

        self.prompt_given = bool(data.get("prompt"))
        self.prompt = module.one_line(data.get("prompt") or self.name)
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
        """The setting at its default, as a line of prj.conf."""
        return f"CONFIG_{self.name}={self.default}"

    def __repr__(self):
        return f"Setting({self.line})"


def _refuse_moved(data):
    """
    In a manifest asking for 4.0.0, the keys of the zephyr section from before,
    each refused with where it went, and any key the section does not have.
    """
    if "defaults" in data:
        raise ManifestError(
            "zephyr.defaults is zephyr.library.kconfig from 4.0.0. List the settings there, under library "
            "and then kconfig."
        )

    if isinstance(data.get("kconfig"), str):
        raise ManifestError(
            f"zephyr.kconfig has {data['kconfig']!r}, one symbol. From 4.0.0 the library's switch is "
            f"zephyr.symbol, as symbol: {data['kconfig']}, and its settings of other symbols are "
            "zephyr.library.kconfig."
        )

    moved = {
        "kconfig": "zephyr.library.kconfig from 4.0.0. List the settings there, under library and then kconfig.",
        "conf": "zephyr.library.conf from 4.0.0. List the settings there, under library and then conf.",
        "sysbuild": "zephyr.project.sysbuild from 4.0.0. List the settings there, under project and then "
                    "sysbuild.",
        "cmake": "zephyr.project.cmake and zephyr.library.cmake from 4.0.0: the lines of the application's "
                 "CMakeLists.txt under project, by their place, before-zephyr or after-zephyr, and those of the "
                 "library's own under library.",
    }

    for key, where in moved.items():
        if key in data:
            raise ManifestError(f"zephyr.{key} is {where}")

    unknown = [str(key) for key in data if key not in KEYS]

    if unknown:
        raise ManifestError(f"zephyr has {', '.join(unknown)}. From 4.0.0 it holds {', '.join(KEYS)}.")


def _refuse_new(data):
    """
    In a manifest asking for less than 4.0.0, the keys of the zephyr section
    new in it, refused: an installer from before would not read them.
    """
    if "symbol" in data:
        raise ManifestError(
            "zephyr.symbol is new in 4.0.0: ask for it under requires, as lib_installer: 4.0.0, or "
            "name the library's switch under zephyr.kconfig."
        )

    if isinstance(data.get("kconfig"), list):
        raise ManifestError(
            "zephyr.kconfig names the library's switch, one symbol, in a manifest asking for less than "
            "4.0.0. A list of settings is zephyr.defaults there, and zephyr.library.kconfig from 4.0.0: "
            "ask for it under requires, as lib_installer: 4.0.0."
        )

    for key in ("project", "library"):
        if key in data:
            raise ManifestError(
                f"zephyr.{key} is new in 4.0.0: ask for it under requires, as lib_installer: 4.0.0."
            )


class ZephyrPart:
    """
    The zephyr section of installer.yml, with what it leaves out filled in.
    renamed is whether the manifest asks for 4.0.0, whose zephyr section names
    the library's switch under symbol, and lists what it writes under where it
    goes: project, the application's own files, and library, its own folder,
    each list in groups under their titles when it likes.
    """

    def __init__(self, library, data, renamed=False):
        if data is None:
            data = {}

        if not isinstance(data, dict):
            raise ManifestError("zephyr should hold kconfig and settings.")

        # The keys of the release the manifest asks for. A key written as the
        # other release has it is refused with the name to use, rather than
        # read wrongly.
        if renamed:
            _refuse_moved(data)
        else:
            _refuse_new(data)

        self.renamed = renamed
        switch = "symbol" if renamed else "kconfig"
        given = data.get(switch)

        # From 4.0.0 the switch can carry a note, as a setting's does, a
        # mapping of one, GCORE: its note, written above it in the block.
        self.symbol_note = None

        if renamed and isinstance(given, dict):
            if len(given) != 1:
                raise ManifestError(
                    f"zephyr.symbol has {given!r}. Give the library's switch alone, or with its note after a "
                    "colon, on a line of its own below symbol, such as GCORE: builds gcore."
                )

            (given, note), = given.items()
            self.symbol_note = titles.comment(note, f"The note of {given} under zephyr.symbol")

        self.symbol = _symbol(given, f"zephyr.{switch}") if given else symbol_of(library.name)

        settings = data.get("settings") or []

        if not isinstance(settings, list):
            raise ManifestError("zephyr.settings is a list, one entry per setting.")

        self.settings = [Setting(entry, self.symbol) for entry in settings]
        names = [setting.name for setting in self.settings]
        twice = sorted({name for name in names if names.count(name) > 1})

        if twice:
            raise ManifestError(f"zephyr.settings has {', '.join(twice)} more than once.")

        if renamed:
            self._read_parts(library, data)
        else:
            self._read_before(library, data)

        self._check(library)

    def _read_parts(self, library, data):
        """
        What a manifest asking for 4.0.0 writes, by where it goes: under
        project, into the application's prj.conf, sysbuild.conf and
        CMakeLists.txt, each in a block of the library's; under library, into
        its own Kconfig, Kconfig fragment and CMakeLists.txt.
        """
        project = titles.part(data.get("project"), "zephyr.project", PROJECT_KEYS)
        own = titles.part(data.get("library"), "zephyr.library", LIBRARY_KEYS)

        self.prj_key = "zephyr.project.conf"
        self.sysbuild_key = "zephyr.project.sysbuild"
        self.defaults_key = "zephyr.library.kconfig"
        self.conf_key = "zephyr.library.conf"

        self.prj = titles.listed(project.get("conf"), self.prj_key, lambda text: Requirement(text, self.prj_key))
        self.sysbuild = titles.listed(project.get("sysbuild"), self.sysbuild_key,
                                      lambda text: SysbuildSetting(text, self.sysbuild_key))
        self.defaults = titles.listed(own.get("kconfig"), self.defaults_key,
                                      lambda text: Default(text, self.defaults_key))
        self.conf = titles.listed(own.get("conf"), self.conf_key, lambda text: Assignment(text, self.conf_key))
        self.cmake = titles.cmake_groups(project.get("cmake"), own.get("cmake"), "zephyr",
                                         (BEFORE_ZEPHYR, AFTER_ZEPHYR), MODULE)

        # From 4.0.0 each platform's settings are in its own section: what a
        # library sets in the application's prj.conf is zephyr.project.conf,
        # and requires.kconfig, which every platform read, is refused, as
        # ESP-IDF refuses it.
        if getattr(library.requires, "kconfig", None):
            raise ManifestError(
                "requires.kconfig is zephyr.project.conf from 4.0.0: the settings a library writes into the "
                "application's prj.conf, beside its switch. List them there, under project and then conf."
            )

    def _read_before(self, library, data):
        """What a manifest asking for less than 4.0.0 writes, read the way it was written for."""
        # Lines of CMake the library needs beyond its files, by the place they
        # go, from 2.1.0: module, the module's CMakeLists.txt, or before-zephyr
        # and after-zephyr, the application's, above find_package(Zephyr) or at
        # its end. Before, labelled groups each with a where; and a plain list
        # of lines, the form from before 2.0.0: one group, in the module.
        self.cmake = blocks.groups(data.get("cmake"), "zephyr.cmake", PLACES, MODULE,
                                   rooted=getattr(library, "rooted", False))

        # Settings of sysbuild, for the application's sysbuild.conf.
        self.sysbuild_key = "zephyr.sysbuild"
        sysbuild = data.get("sysbuild") or []

        if not isinstance(sysbuild, list):
            raise ManifestError("zephyr.sysbuild is a list of settings, such as [BOOTLOADER_MCUBOOT].")

        self.sysbuild = [SysbuildSetting(entry) for entry in sysbuild]

        # Settings the library gives other symbols while its own is on, from
        # 2.1.0, written as requires.kconfig is. Each becomes a configdefault
        # in its Kconfig, so the application's prj.conf holds only the
        # library's switch, and any line of its own there wins.
        self.defaults_key = "zephyr.defaults"
        defaults = data.get("defaults") or []

        if not isinstance(defaults, list):
            raise ManifestError("zephyr.defaults is a list of settings, such as [BT, BT_L2CAP_TX_MTU=498].")

        if defaults and not getattr(library, "rooted", False):
            raise ManifestError(
                "zephyr.defaults is new in 2.1.0: ask for it under requires, as zephyr_installer: 2.1.0."
            )

        self.defaults = [Default(entry, self.defaults_key) for entry in defaults]

        # A Kconfig fragment of the library's own is new in 4.0.0.
        self.conf_key = "zephyr.conf"

        if data.get("conf"):
            raise ManifestError(
                "zephyr.conf is no key of a manifest asking for less than 4.0.0. A library's Kconfig fragment "
                "is zephyr.library.conf from 4.0.0: ask for it under requires, as lib_installer: 4.0.0."
            )

        self.conf = []

        # The settings it writes into the application's Kconfig file, beside
        # its switch.
        self.prj_key = "requires.kconfig"
        self.prj = list(getattr(library.requires, "kconfig", []))

        # A key the section does not have, such as a misspelt defaults, which
        # would take what it says with it unseen: warned about, since a
        # release made with it has to keep installing as it did.
        self.unknown = [str(key) for key in data if key not in BEFORE_KEYS]

    def _check(self, library):
        """
        What every release refuses of the lists: a symbol given twice in one,
        the library's switch where it cannot be, a symbol in two of them, which
        would never count in one, and the fragment's place taken by a file of
        the library's own.
        """
        prj = [entry.symbol for entry in self.prj]

        # requires.kconfig was never checked so, and a manifest from before
        # keeps installing as it did.
        if self.renamed:
            twice = sorted({name for name in prj if prj.count(name) > 1})

            if twice:
                raise ManifestError(f"{self.prj_key} has {', '.join(twice)} more than once.")

            if self.symbol in prj:
                raise ManifestError(
                    f"{self.prj_key} has {self.symbol}, the library's own switch, which the installer writes "
                    "last in the block by itself, y, under the library's name. Give it a note under "
                    f"zephyr.symbol, as {self.symbol}: its note."
                )

        names = [setting.symbol for setting in self.sysbuild]
        twice = sorted({name for name in names if names.count(name) > 1})

        if twice:
            raise ManifestError(f"{self.sysbuild_key} has {', '.join(twice)} more than once.")

        # The library's settings of other symbols: defaults, which hold while it
        # is on, and which any line of the application's own wins over.
        key = self.defaults_key
        names = [default.symbol for default in self.defaults]
        twice = sorted({name for name in names if names.count(name) > 1})

        if twice:
            raise ManifestError(f"{key} has {', '.join(twice)} more than once.")

        if self.symbol in names:
            raise ManifestError(
                f"{key} has {self.symbol}, the library's own switch. prj.conf switches it, "
                "and the defaults hold while it is on."
            )

        # A symbol set in prj.conf is an assignment, and a default for it would
        # never be used.
        both = sorted(set(prj) & set(names))

        if both:
            raise ManifestError(
                f"{', '.join(both)} {'is' if len(both) == 1 else 'are'} in both {self.prj_key} and "
                f"{key}. Give each in one of them: {self.prj_key} sets it in prj.conf, "
                f"{key} gives it a default while the library is on."
            )

        # The library's Kconfig fragment, read after the application's Kconfig
        # files: assignments, for what a default cannot set, a member of a
        # choice, or a symbol Kconfig reads before the library's Kconfig.
        conf = self.conf_key
        assigned = [setting.symbol for setting in self.conf]
        twice = sorted({name for name in assigned if assigned.count(name) > 1})

        if twice:
            raise ManifestError(f"{conf} has {', '.join(twice)} more than once.")

        if self.symbol in assigned:
            raise ManifestError(
                f"{conf} has {self.symbol}, the library's own switch. The application's Kconfig file "
                f"switches it, and {conf}, read after it, would decide in its place."
            )

        # What the fragment sets is set after prj.conf, and over any default,
        # so the same symbol in prj.conf's block or among the defaults would
        # never count.
        both = sorted(set(prj) & set(assigned))

        if both:
            raise ManifestError(
                f"{', '.join(both)} {'is' if len(both) == 1 else 'are'} in both {self.prj_key} and "
                f"{conf}. Give each in one of them: {self.prj_key} sets it in prj.conf, {conf} "
                "in the library's own Kconfig fragment, read after prj.conf."
            )

        both = sorted(set(names) & set(assigned))

        if both:
            raise ManifestError(
                f"{', '.join(both)} {'is' if len(both) == 1 else 'are'} in both {key} and "
                f"{conf}. Give each in one of them: {key} gives it a default while the "
                f"library is on, {conf} sets it in every build."
            )

        # The fragment's place in the library's folder, which a file of the
        # library's own would share, each install writing over the other.
        place = f"zephyr/{module.fragment_name(library)}"
        files = getattr(library, "extras", []) + getattr(library, "all_code_files", [])

        if self.conf and place in {entry.destination for entry in files}:
            raise ManifestError(
                f"installer.yml puts a file of {library.name}'s own at {place}, where the installer writes "
                f"the lines of {conf}. Give the file another place, or its lines under {conf}."
            )


class Zephyr(Platform):
    """A Zephyr application: CMakeLists.txt with find_package(Zephyr), and prj.conf."""

    platform = "zephyr"
    legacy = "zephyr-installer"
    label = "Zephyr"
    project = "Zephyr application"
    no_project = "No Zephyr application was recognised here, so nothing was registered."
    no_project_hint = "Run this from your application's folder, the one holding CMakeLists.txt and prj.conf."

    def __init__(self, version):
        self.version = version
        # The Kconfig file chosen for this run, by --conf or by the answer to
        # the question, which is asked once however many libraries go in.
        self.conf_given = None
        self.conf_chosen = None
        self.ask = None
        # The file each library of this run goes into, settled by check()
        # and used by integrate(), so the two always agree.
        self.conf_of = {}

    def legacy_files(self, project_root):
        """The application's files zephyr-installer wrote its blocks into."""
        root = Path(project_root)
        found = [app.CMAKELISTS, app.SYSBUILD_CONF] + app.conf_files(root)

        return [root / name for name in found]

    def add_arguments(self, parser):
        parser.add_argument(
            "--conf",
            default=None,
            metavar="FILE",
            help="the Kconfig file of the application that switches the library on, such as "
            "prj.conf or boards/nrf52840dk_nrf52840.conf. Asked when the application has more "
            "than one, prj.conf otherwise. A library already in one stays there.",
        )

    def take_arguments(self, args, ask):
        self.conf_given = getattr(args, "conf", None)
        self.ask = ask

    def project_root(self, given):
        """The application's folder. Refuses sysbuild.conf as the Kconfig file of --conf."""
        if self.conf_given is not None and Path(self.conf_given).name == app.SYSBUILD_CONF:
            raise InstallError(
                f"{app.SYSBUILD_CONF} holds the settings of sysbuild, not the application's, so a "
                "library is not switched on there. Its sysbuild settings go in zephyr.sysbuild of "
                "its installer.yml. Leave out --conf, or give prj.conf or a board's own file."
            )

        return given

    def managed_files(self, project_root, library):
        """
        The application's files this edits, which a once file must never be:
        CMakeLists.txt, the Kconfig file with the library's block, and
        sysbuild.conf when the library has sysbuild settings.
        """
        found = [self.record_name, app.CMAKELISTS]
        found.append(self.conf_of.get(library.name) or app.holding(project_root, library.name) or app.PRJ_CONF)

        if getattr(getattr(library, "zephyr", None), "sysbuild", None):
            found.append(app.SYSBUILD_CONF)

        return found

    def default_folder(self, library):
        """Libraries go together in modules/ of the application."""
        return f"modules/{library.name}"

    def conf_for(self, library, project_root):
        """
        The Kconfig file this library's symbols go into, as a path from the
        application's folder.

        The one that already has its block, on an update. Otherwise the one
        given with --conf, or chosen earlier in this run. Otherwise, with more
        than one to choose from and someone to ask, the answer, and prj.conf
        when there is nobody or nothing to choose.
        """
        if library.name in self.conf_of:
            return self.conf_of[library.name]

        chosen = app.holding(project_root, library.name) or self.conf_given or self.conf_chosen

        if chosen is None:
            offered = app.conf_files(project_root)
            chosen = app.PRJ_CONF

            if len(offered) > 1 and self.ask is not None:
                print()
                print(console.note("This application has more than one Kconfig file: " + ", ".join(offered)))
                answer = self.ask(console.strong(f"Kconfig file for the libraries [{app.PRJ_CONF}]: "))
                chosen = answer or app.PRJ_CONF

            self.conf_chosen = chosen

        chosen = Path(chosen).as_posix()
        self.conf_of[library.name] = chosen

        return chosen

    def read_manifest(self, manifest, data):
        renamed = asks_for(data, RENAMED)
        manifest.zephyr = ZephyrPart(manifest, data.get("zephyr"), renamed)

        # Each option's own groups of CMake lines, read now that the release
        # the manifest asks for, which says where they are, is known.
        for option in manifest.options.values():
            option.zephyr_cmake = titles.option_cmake(option, "zephyr", renamed, PLACES, MODULE)

        # A label names one group, among the library's and all its options'.
        labels = [group.label for group in manifest.zephyr.cmake]

        for option in manifest.options.values():
            labels += [group.label for group in getattr(option, "zephyr_cmake", [])]

        twice = sorted({label for label in labels if labels.count(label) > 1})

        if twice:
            raise ManifestError(f"zephyr.cmake has two groups labelled {', '.join(twice)}, its "
                                "options' groups counted. Give each its own label.")

    def read_option(self, option, data):
        """
        An option's own zephyr part, kept for read_manifest(): its groups of
        CMake lines, written while it is taken, are where the release the
        manifest asks for says, which is known once the whole manifest is read.
        """
        part = data.get("zephyr") if isinstance(data, dict) else None

        if part is not None and not isinstance(part, dict):
            raise ManifestError(f"options.{option.name}.zephyr should hold cmake.")

        option.zephyr_part = part or {}
        option.zephyr_cmake = []

    def read_requirements(self, requirements, data):
        """The Zephyr part of requires: Kconfig symbols, and hardware."""
        kconfig = data.get("kconfig") or []

        if not isinstance(kconfig, list):
            raise ManifestError("requires.kconfig is a list of symbols, such as [I2C].")

        requirements.kconfig = [Requirement(entry) for entry in kconfig]
        requirements.peripherals = [Peripheral(entry) for entry in (data.get("peripherals") or [])]

    def requirements_empty(self, requirements):
        return not (requirements.kconfig or requirements.peripherals)

    def warnings(self, manifest):
        part = getattr(manifest, "zephyr", None)
        found = []

        for setting in (part.settings if part else []):
            if not setting.name.startswith(part.symbol + "_"):
                found.append(f"zephyr.settings {setting.name} does not start with {part.symbol}_, "
                             "so it may be taken by another library")

            if not setting.prompt_given:
                found.append(f"zephyr.settings {setting.name} has no prompt, so menuconfig shows only its name")

        return found + unknown_warnings("zephyr", getattr(part, "unknown", []))

    def check(self, library, project_root):
        """What the application is missing for this library. Never stops an install."""
        findings = []

        if app.find_cmakelists(project_root) is None:
            findings.append(Finding(
                WARN, "No CMakeLists.txt with find_package(Zephyr) here",
                "Run this from your application's folder, or give it with --project.",
            ))

            return findings

        conf = self.conf_for(library, project_root)
        assigned = app.assigned(project_root, library.name, conf)
        ours = app.in_block(project_root, library.name, conf)

        for symbol, value, line in app.wanted(library):
            have = assigned.get(symbol)

            # The library's own switch is no requirement, and is only worth a
            # line when the user has set it already.
            if symbol == library.zephyr.symbol and have is None:
                continue

            if have is None and ours.get(symbol) == value:
                findings.append(Finding(OK, f"{line} is in {conf}"))
            elif have is None:
                findings.append(Finding(INFO, f"{line} goes into {conf}"))
            elif have[0] == value:
                # The same, so nothing is wrong, but the block will not set it,
                # and the user should know which line does.
                findings.append(Finding(
                    WARN, f"{have[1]} already sets {line}, so the block has it commented out",
                    "Your line is the one used. Nothing to do.",
                ))
            else:
                findings.append(Finding(
                    WARN, f"{have[1]} sets CONFIG_{symbol}={have[0]}, and {library.name} needs {value}. "
                    "The block has it commented out",
                    "Your line is the one used. Change it if the library is to work.",
                ))

        # The library's settings of other symbols, zephyr.library.kconfig or,
        # before 4.0.0, zephyr.defaults, which hold while it is on. A line of
        # the application's that sets the same symbol wins, and says so.
        part = library.zephyr

        for default in part.defaults:
            have = assigned.get(default.symbol)

            if have is None or have[0] == default.value:
                findings.append(Finding(OK, f"{default.line} by default, while CONFIG_{part.symbol} is on"))
            else:
                findings.append(Finding(
                    INFO, f"{have[1]} sets CONFIG_{default.symbol}={have[0]}, in place of "
                    f"{library.name}'s default {default.value}",
                    "Your line is the one used.",
                ))

        # The library's Kconfig fragment, zephyr.library.conf, read after the
        # application's Kconfig files. A line of the application's that sets
        # the same symbol loses to it, and is named, since nothing else would
        # say so.
        fragment = f"zephyr/{module.fragment_name(library)}"

        for setting in part.conf:
            have = assigned.get(setting.symbol)

            if have is None or have[0] == setting.value:
                findings.append(Finding(OK, f"{setting.line} in {fragment}, read after {conf}"))
            else:
                findings.append(Finding(
                    WARN, f"{have[1]} sets CONFIG_{setting.symbol}={have[0]}, and {library.name}'s "
                    f"{part.conf_key} sets {setting.value}",
                    f"{fragment} is read after {have[1]}, so its line is the one used. A file given "
                    "with -DEXTRA_CONF_FILE is read after it.",
                ))

        for peripheral in library.requires.peripherals:
            findings.append(Finding(
                INFO, f"Needs {peripheral.describe()}",
                "Enable it in your board's devicetree, or in an overlay of the application.",
            ))

        return findings

    def integrate(self, project_root, library, destination, only=None, dropped=(),
                  dropped_defines=()):
        """
        Make the library a module of the application, and switch it on.

        dropped and dropped_defines need nothing here: the module's files are
        written again from the new manifest on every install, so a file or a
        define that has gone is simply no longer in them.
        """
        outcomes = [module.write(library, destination)]
        outcomes.extend(app.integrate(project_root, library, destination,
                                      self.conf_for(library, project_root)))

        return outcomes

    def uninstall(self, project_root, library):
        """
        Take the library out of the application's CMakeLists.txt and Kconfig
        file, and delete the module files and the Kconfig fragment this wrote
        into its folder.
        """
        defined = module.symbols(library.destination) if library.destination is not None else []
        outcomes = app.uninstall(project_root, library.name)

        if library.destination is not None:
            saved = module.remove(library.destination)

            if saved is not None:
                outcomes.append(Outcome(
                    module.NAME, CHANGED,
                    f"Your lines in zephyr/CMakeLists.txt are saved, in zephyr/{saved.name}.",
                    backup=saved,
                ))

        # A setting the user set below the block names a symbol that is gone
        # now, and Zephyr stops on a symbol it does not know. The line is the
        # user's, so it is named rather than taken out.
        for conf, lines in app.leftover(project_root, defined).items():
            outcomes.append(Outcome(
                conf, MANUAL,
                f"{conf} still sets what came with {library.name}, and Zephyr stops on a symbol it "
                "does not know. Take these lines out:",
                lines,
            ))

        return outcomes
