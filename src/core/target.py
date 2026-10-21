"""
What one platform adds to the core.

The core fetches a library, reads its installer.yml, copies its files and keeps
what the user wrote. What a project looks like belongs to each platform:
STM32CubeIDE, Keil and IAR for one, Zephyr's CMake and Kconfig for another. So
each platform fills in a Target, and the one chosen for the run is handed to
use() before anything else runs. The core asks it wherever the answer depends
on the kind of project.

Read it as target.current at the time of use, never imported by name: an
import would keep the default it found then.
"""

# How seriously to take a Finding.
OK = "ok"
WARN = "warn"
INFO = "info"

# What an integration did to the project.
CHANGED = "changed"
ALREADY = "already"
MANUAL = "manual"
SKIPPED = "skipped"


class Finding:
    """One observation about the project, with how seriously to take it."""

    def __init__(self, level, message, hint=""):
        self.level = level
        self.message = message
        self.hint = hint

    def __repr__(self):
        return f"Finding({self.level}, {self.message!r})"


class Outcome:
    """What an integration did, and what the user still has to do themselves."""

    def __init__(self, ide, status, message, steps=None, backup=None, blocks=None):
        self.ide = ide
        self.status = status
        self.message = message
        self.steps = steps or []
        self.backup = backup
        # The blocks this left in project files, {file: {marker name:
        # fingerprint}}, for the record: see blocks.py.
        self.blocks = blocks or {}

    @property
    def needs_user(self):
        return self.status == MANUAL

    def __repr__(self):
        return f"Outcome({self.ide}, {self.status})"


class Target:
    """The answers that depend on the kind of project. Each platform gives its own."""

    # The command, as messages name it, such as lib-installer.
    name = "installer"

    # Its version, which requires.installer in a manifest is compared with.
    version = "0.0.0"

    # The file in the project that remembers what was installed, and where.
    record_name = ".installer.json"

    # What the user's project is called in the help, such as "STM32 project".
    project = "project"

    # What --ide can choose from. None of them means there is no --ide.
    integrations = ()

    # The key under requires that gives the oldest of this installer a library
    # works with, such as lib_installer.
    requires_key = "installer"

    # Other names the same key has had, still read, such as zephyr_installer
    # before 3.0.0.
    requires_aliases = ()

    # Said when no project file was recognised, and what to do instead.
    no_project = "No project file was recognised here, so nothing was registered."
    no_project_hint = "Add the folder to your include paths and the .c files to your build."

    # Added to name where a message gives a command to type, such as
    # " --platform zephyr" when the run needed one.
    command_suffix = ""

    @property
    def command(self):
        """The command as a message tells the user to type it."""
        return self.name + self.command_suffix

    @property
    def update_command(self):
        """The line that updates this installer."""
        return f"pip install --upgrade {self.name}"

    def add_arguments(self, parser):
        """Command line options of this installer's own, added to the core's."""

    def take_arguments(self, args, ask):
        """
        What this installer's own options were given as, before anything runs.

        ask(prompt) puts a question to the user and returns what was typed, or
        None when nobody is there to answer, so a question is asked only when
        it can be.
        """

    def project_root(self, given):
        """
        The folder this run works in, once take_arguments() has run.

        given is --project, or the folder the command was run from. A target
        whose libraries live somewhere of their own, such as Arduino's
        libraries folder, answers with that. Raise installer.InstallError to
        stop the run with a reason.
        """
        return given

    def dependency_root(self, project_root):
        """
        The folder a library another one needs is installed into, and looked
        for in. The project's own, unless the target keeps them elsewhere.
        """
        return project_root

    def default_folder(self, library):
        """The folder offered for a library installed for the first time."""
        return library.name

    def folder_for(self, library, project_root):
        """
        The folder offered for a library installed for the first time into
        project_root, which is the project, or where dependency_root() keeps
        what other libraries need.
        """
        return self.default_folder(library)

    def once_root(self, project_root):
        """
        The folder a 2.0.0 manifest's once files land in: the project's own, or
        None for a target with no project of its own, such as Arduino's
        sketchbook, where such a file has nowhere to go and is refused.
        """
        return project_root

    # Said when once_root() has no folder, with the way to get one.
    no_once_root = "This kind of project has no folder of its own to put them in."

    def managed_files(self, project_root, library):
        """
        Files in the project a once file must never be, because the installer
        edits them or reads them as the project's own: paths from once_root(),
        or patterns such as *.ioc. The record is always one of them.
        """
        return [self.record_name]

    def include_line(self, library, destination, project_root):
        """
        What goes between the quotes of the #include the last line names, or
        None for the first header, relative to its include folder.
        """
        return None

    def read_manifest(self, manifest, data):
        """Read this target's own part of installer.yml onto manifest, once the rest is read."""

    def read_option(self, option, data):
        """Read this target's own section of one option onto it, such as its CMake lines."""

    def read_requirements(self, requirements, data):
        """Read what this kind of project checks from requires, onto requirements."""

    def requirements_empty(self, requirements):
        """Whether the part of requires this target reads asks for nothing."""
        return True

    def warnings(self, manifest):
        """Values in a manifest this target does not know, as sentences."""
        return []

    def check(self, library, project_root):
        """Findings about the project, before the library goes in."""
        return []

    def integrate(self, project_root, library, destination, only=None, dropped=(),
                  dropped_defines=()):
        """Register an installed library with the project. Returns a list of Outcome."""
        return []

    def uninstall(self, project_root, library):
        """
        Take a library out of the project's build, before its files go.

        library is an installer.Installed: its name, its folder, its compiled
        files and its defines, as the record remembers them. Returns a list of
        Outcome.
        """
        return []


class Platform(Target):
    """
    One of lib-installer's platforms: a target with the one command, record
    and key of lib-installer, which also says which platform it is, and what
    its installer was called before 3.0.0, so a project installed then moves
    over on the first run.
    """

    name = "lib-installer"
    record_name = ".lib-installer.json"
    requires_key = "lib_installer"

    # The keys the five installers read before 3.0.0, still read: a library
    # asking stm32_installer: 2.1.0 is one 3.0.0 installs.
    requires_aliases = ("installer", "stm32_installer", "zephyr_installer", "esp32_installer",
                        "arduino_installer", "pio_installer")

    # Its name, as platform: in installer.yml and --platform give it.
    platform = None

    # The installer it was before 3.0.0, such as zephyr-installer.
    legacy = None

    # How messages name the platform, such as ESP-IDF.
    label = None

    def legacy_roots(self, given):
        """
        The folders where a record of the installer before 3.0.0 can be, which
        the first run moves over before anything reads them: the project's.
        """
        return [given]

    @property
    def legacy_record(self):
        """The record that installer kept, such as .zephyr-installer.json."""
        return f".{self.legacy}.json" if self.legacy else None

    def legacy_files(self, project_root):
        """
        The project's files that can hold blocks between the old installer's
        markers, which the first run of 3.0.0 renames to lib-installer's.
        """
        return []


current = Target()


def use(chosen):
    """Make chosen the target the core asks from now on."""
    global current
    current = chosen
