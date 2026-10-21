"""
Run steps: commands a library runs once its files are in place.

A library can need something made in the project that no file can carry, such
as a key it signs its images with, made fresh for each product. Its manifest
names a step for that under run, and the step runs once the library is in.

It runs on the user's own computer, with the user's rights, so it is never run
without a word. The user sees exactly what will run and answers, or says so in
advance with --run or --yes. Nothing in a manifest can turn the question off:
a library that changed hands on GitHub must not be able to run something
unseen on the next install.

A step whose file is already there is skipped without a question, since the
file is what it makes. One with no such file that ran before, and runs the same
thing, is not asked again either: an update is not the moment to make a second
key.
"""

import os
import subprocess
import sys
from pathlib import Path

from . import console, manifest, target


class Outcome:
    """What became of one step, so the record and the exit code can say."""

    def __init__(self, step, status, note=""):
        self.step = step
        self.status = status
        self.note = note


# What became of a step.
RAN = "ran"
FAILED = "failed"
SKIPPED = "skipped"
NOT_RUN = "not run"


def _library_folder(project_root, destination):
    """
    The library's folder as a step names it: from the project's folder, where
    the step runs, or in full when it is somewhere else.
    """
    try:
        return Path(destination).resolve().relative_to(Path(project_root).resolve()).as_posix()
    except ValueError:
        return Path(destination).resolve().as_posix()


def _words(step, project_root, destination):
    """The command and the arguments, {library} in them standing for the library's folder."""
    words = list(step.command or []) + list(step.args)

    if not step.rooted or project_root is None or destination is None:
        return words

    folder = _library_folder(project_root, destination)

    return [word.replace(manifest.LIBRARY, folder) for word in words]


def script_path(library, step, project_root=None, destination=None):
    """
    The script a step starts. Before 2.1.0, in the library as it was fetched;
    from 2.1.0, from the project's folder, or the library's with {library}.
    """
    if not step.rooted or project_root is None:
        return Path(library.root) / step.script

    return Path(destination if step.in_library else project_root) / step.script


def unless_path(step, project_root, destination=None):
    """The file whose being there skips a step: from the project's folder, or the library's with {library}."""
    if step.unless_in_library and destination is not None:
        return Path(destination) / step.unless

    return Path(project_root) / step.unless


def argv(library, step, project_root=None, destination=None):
    """What runs: the installer's own Python and the script, or the command, then the arguments."""
    words = _words(step, project_root, destination)

    if step.script is not None:
        return [sys.executable, str(script_path(library, step, project_root, destination))] + words

    return words


def shown(library, step, project_root=None, destination=None):
    """The command as the user reads it, and could type it in the project's folder."""
    words = _words(step, project_root, destination)

    if step.script is not None:
        if step.rooted and project_root is not None and step.in_library:
            script = _library_folder(project_root, destination) + "/" + step.script.as_posix()
        else:
            script = step.script.as_posix()

        words = ["python", script] + words

    return subprocess.list2cmdline(words) if os.name == "nt" else " ".join(_quoted(w) for w in words)


def _quoted(word):
    """A word as a POSIX shell would need it."""
    if word and all(c.isalnum() or c in "-_./=:@%+," for c in word):
        return word

    return "'" + word.replace("'", "'\\''") + "'"


def environment(library, project_root, destination):
    """The environment a step runs in: the user's own, and where things are."""
    env = dict(os.environ)
    env.update({
        "INSTALLER_PROJECT": str(project_root),
        "INSTALLER_LIBRARY": str(destination),
        "INSTALLER_NAME": library.name,
        "INSTALLER_VERSION": library.version or "",
        "INSTALLER": target.current.name,
        "INSTALLER_PLATFORM": getattr(target.current, "platform", None) or "",
    })

    return env


def run(library, project_root, destination, ask, turn_on=(), turn_off=(), assume_yes=False, recorded=None):
    """
    Run a library's steps, each as its rules say, and say what became of each.

    ask(prompt) puts a question and returns the answer, or None when nobody is
    there to answer. recorded is what ran before, label to fingerprint, from the
    record. Returns the outcomes, one per step.
    """
    if not library.run:
        return []

    recorded = recorded if isinstance(recorded, dict) else {}
    folder = Path(project_root)
    outcomes = []

    print()
    print(console.heading("Run"))

    for step in library.run:
        label = f"  {step.label:<12} "
        command = shown(library, step, folder, destination)

        if step.unless is not None and unless_path(step, folder, destination).exists():
            print(label + console.note(f"skipped, {step.unless} is already there"))
            outcomes.append(Outcome(step, SKIPPED))
            continue

        if step.label in turn_off:
            print(label + console.note(f"skipped, as asked with --no-run {step.label}"))
            outcomes.append(Outcome(step, SKIPPED))
            continue

        if (step.unless is None and recorded.get(step.label) == step.fingerprint()
                and step.label not in turn_on):
            print(label + console.note(f"ran before. Run it again with --run {step.label}"))
            outcomes.append(Outcome(step, SKIPPED))
            continue

        print(label + (step.description or step.label))
        print(f"               {console.strong(command)}")

        if step.label in turn_on:
            go = True
        elif assume_yes:
            go = True
        else:
            reply = ask(console.strong("               Run it? [Y/n]: "))

            if reply is None:
                print(console.warn(
                    f"               not run, nobody was there to ask. Run it with --run {step.label}."
                ))
                outcomes.append(Outcome(step, NOT_RUN))
                continue

            go = reply.lower() in ("", "y", "yes")

        if not go:
            print(console.note("               not run, as answered"))
            outcomes.append(Outcome(step, NOT_RUN))
            continue

        outcomes.append(_execute(library, step, folder, destination))

    return outcomes


def _execute(library, step, folder, destination):
    """Run one step, its output straight to the user's screen, and say how it went."""
    sys.stdout.flush()

    try:
        code = subprocess.run(argv(library, step, folder, destination), cwd=str(folder),
                              env=environment(library, folder, destination)).returncode
    except FileNotFoundError:
        program = step.command[0] if step.command else sys.executable
        print(console.warn(f"               failed: {program} is not installed, or not on the PATH"))
        return Outcome(step, FAILED, f"{program} not found")
    except OSError as error:
        print(console.warn(f"               failed: {error}"))
        return Outcome(step, FAILED, str(error))

    if code != 0:
        print(console.warn(f"               failed, it ended with code {code}"))
        return Outcome(step, FAILED, f"code {code}")

    print(console.good("               done"))

    return Outcome(step, RAN)
