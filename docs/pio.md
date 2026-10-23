# lib-installer for PlatformIO

Installs embedded C and C++ libraries into a PlatformIO project, from GitHub, from a zip, or from a folder, for any framework.

It puts a library into your project's `lib` folder, which PlatformIO builds from for every framework: Arduino, ESP-IDF, STM32Cube, or none at all on the native platform. A library written for any project gets the `library.json` PlatformIO builds it by, the defines it needs go into `platformio.ini`, the libraries it needs go in first, and its settings are kept through every update.

This page is what lib-installer does in a PlatformIO project, and what a library's `installer.yml` can say for PlatformIO. How to install lib-installer, every command, and what is the same on every platform are in the [README](../README.md).

## Installing a library

From your project's folder, the one holding `platformio.ini`, install a library by its GitHub owner and name:

```bash
lib-installer owner/example
```

To see it work first, take [lib-installer-example-pio](https://github.com/nimaltd/lib-installer-example-pio), a library made for trying the installer on. It builds with every framework, and on the native platform too, so you can run it on your computer with no board at all. Its README walks through a setting kept through an update, an option, and an uninstall.

### Where a library goes

Into `lib`, in a folder of its own:

```
my-project/
  platformio.ini            the defines of a library that has some, in build_flags
  .lib-installer.json       what is installed here, and where
  src/
    main.c
  lib/
    example/
      library.json          written by the installer: how PlatformIO builds the library
      src/
        example.h           the library's files, as its installer.yml lists them
        example_config.h    its settings, between USER CODE lines
        example.c
```

PlatformIO builds a library of `lib` once your code includes one of its headers, for every environment in `platformio.ini`, so the library is your project's own, with your project's settings. You include it by its name:

```c
#include "example.h"
```

The installer asks for the folder, with `lib/example` as the answer when you just press Enter. A folder outside `lib` works too, given with `--dir`, but PlatformIO does not look there, so the installer says what to add to `platformio.ini`:

```
Project
  manual  lib_extra_dirs  PlatformIO looks for libraries in lib/, and example is not in it.
          Add its folder's parent to lib_extra_dirs in the [env] section of platformio.ini, or install it into lib/ with --dir lib/example.
```

### library.json

PlatformIO builds a library by its `library.json`. A library written for any project has none, so the installer writes one from the library's `installer.yml`, and writes it again on every install:

```json
{
  "name": "example",
  "version": "1.0.0",
  "frameworks": "*",
  "platforms": "*",
  "build": {
    "srcDir": ".",
    "srcFilter": ["-<*>", "+<src/example.c>"],
    "includeDir": "src"
  }
}
```

It names the library's source files one by one, so PlatformIO builds those and nothing else: a test or an example in the library's folder is left alone. Its description, licence, repository and author go in too, and the frameworks, platforms and PlatformIO Registry libraries the library lists, as [below](#for-someone-writing-a-library).

A library made for PlatformIO that ships its own `library.json`, listed in its `installer.yml` so it is installed, keeps it: the installer writes one only for a library that has none.

### Defines

A library that needs a define for the whole build, such as littlefs's `LFS_DEFINES`, lists it in its `installer.yml`, and the installer puts it into `build_flags` in `platformio.ini`, between two lines that say whose it is:

```ini
[env]
build_flags =
    ; >>> lib-installer: example >>>
    -DEXAMPLE_FAST
    ; <<< lib-installer: example <<<

[env:uno]
platform = atmelavr
board = uno
framework = arduino
```

`[env]` is shared by every environment, so that is where it goes, and the installer adds the section when an environment needs it and the file has none. An environment with `build_flags` of its own does not take them from `[env]`, so it gets the same lines in its own. Everything else in the file is left as you wrote it.

Not in `library.json`: PlatformIO gives the `build_flags` of a `library.json` to the library's own files and to nothing else, so your code, which includes the library's header, would not see the define, and the two would not agree on what the header declares.

Every install writes the lines again from the library's new `installer.yml`, and an uninstall takes them out, with the section the installer added, so `platformio.ini` is back to the byte it was.

### Build flags

A library can need a flag of its own for the whole build, from 4.0.0, such as `-Wl,-u,_printf_float`, without which `printf("%f")` prints nothing on many chips. It goes into the same block, after the defines, and a title or a note the library gives it is written as a comment of `platformio.ini`'s, `;`:

```ini
[env]
build_flags =
    ; >>> lib-installer: example >>>
    -DEXAMPLE_FAST
    ; ******************************************************************************
    ; Printing
    ; ******************************************************************************
    ; printf("%f") prints nothing without it
    -Wl,-u,_printf_float
    ; <<< lib-installer: example <<<
```

PlatformIO reads the comments as comments, and gives every environment the flags, as it does the defines. There is no blank line in the block: in an ini file one reads as the end of the value, to a person and to many a tool, if not to PlatformIO.

### Frameworks and platforms

PlatformIO leaves a library out of any build whose framework or platform the library does not list, without a word, and your `#include` then simply finds nothing. So before anything is written, the installer reads every environment in `platformio.ini` and names any the library will not build in:

```
Requirements
  check   [env:esp32] builds with espidf, which example does not list, so PlatformIO leaves it out of that build
          example lists: arduino.
```

It is a warning and nothing more. The library still goes in, for the environments it does build in.

### A library that needs another

What a library needs goes into `lib` too, beside it, and installs first. In `lib` every library finds the others' headers, so nothing else is needed. It comes from the release the library names for it, or else from its default branch. One already there at a version that will do is left alone. Everything is fetched before anything is installed, so when a library cannot be had, nothing is changed.

A library from the [PlatformIO Registry](https://registry.platformio.org), such as ArduinoJson, is a different thing: the library lists it, the installer writes it into the library's `library.json`, and PlatformIO installs it by itself at the next build.

### Settings

A library's settings are in its configuration header, between `USER CODE BEGIN` and `USER CODE END`:

```c
/* USER CODE BEGIN EXAMPLE_CONFIGURATION */
#define EXAMPLE_PERIOD_MS           250U
/* USER CODE END EXAMPLE_CONFIGURATION */
```

Change them there. Every install and update keeps what is between those lines. The library is in your project's `lib`, so they are your project's settings, for every environment it builds.

### Files that become yours

A library can bring files that belong to your project rather than to the library: a partition table, a file of secrets for you to fill in. Each is a start, made for you to change, so it is created in your project's folder only when it is not there:

```
Files
  written lib/example/src/example.h
  created partitions.csv  yours from now on
```

From then on it is yours. An update never writes over it, and says so with `kept partitions.csv  yours`. An uninstall leaves it where it is, with `kept partitions.csv  yours, not removed`. A library can never put such a file over `platformio.ini`, nor outside your project's folder.

### What you see

A first install from GitHub, of a library that needs I2C and a define:

```
Fetching owner/example ...

example 1.2.0
Driver for the X chip
driver / storage

Requirements
  note    EXAMPLE_FAST goes into build_flags in platformio.ini
  note    Needs I2C, 400 kHz
          Set it up in your code.

Folder to install example into [lib/example]:

Files
  written lib/example/src/example.h
  written lib/example/src/example_config.h
  written lib/example/src/example.c

Project
  updated library.json  Wrote example's library.json, which PlatformIO builds it by.
  updated platformio.ini  Added example's defines to platformio.ini, for every environment.
          backup: platformio.ini.20261017-091500.bak

Done. #include "example.h" and you are away.
```

### Updating a library

Run the same command again. Every file of the library is replaced, so an update updates, and `library.json` and the lines in `platformio.ini` are written again from the new `installer.yml`. What you wrote between `USER CODE BEGIN` and `USER CODE END` is kept. Outside those lines, the next install replaces it, and when that would lose something of yours the file is saved beside it first, as a `.bak`. `platformio.ini` is saved the same way, before each change, as `platformio.ini.<date>-<time>.bak`.

The record of what is installed, and where, is `.lib-installer.json`, beside `platformio.ini`. For each library it also keeps where it came from, down to the commit, the block written into `platformio.ini`, and the steps that ran.

### Uninstalling a library

```bash
lib-installer --uninstall example
```

Its files go, its `library.json`, and its lines in `platformio.ini`. What was yours is saved before it goes, as a `.bak` beside it: a configuration header with your settings in it, or any file of the library you changed by hand. A file you put in the library's folder yourself is left where it is, and the folder with it, and so are the [files that became yours](#files-that-become-yours).

A library another one needs stays, and the installer says which needs it. One that came in only because the library needed it stays too, and the installer says how to take it out.

## For someone writing a library

Put an `installer.yml` at the root of the repository. Any library can have one, whoever wrote it, and the one file serves every platform: each reads its own section and leaves the others' alone.

Every key lib-installer reads is below, each with what it does, as a manifest asking for 4.0.0 writes it. Only `name` and its `headers` or `sources` are required; leave out what your library does not need. What changed in 4.0.0, and how a manifest from before reads, is under [Where everything goes, from 4.0.0](#where-everything-goes-from-400), and what changed in 2.1.0 under [Paths, from 2.1.0](#paths-from-210). For a working one to copy, see [lib-installer-example-pio](https://github.com/nimaltd/lib-installer-example-pio).

```yaml
name: example                      # the library's name, and its folder in lib/
description: Driver for the X chip # one line: shown while installing, and in library.json
repository: https://github.com/owner/example  # where it comes from; its owner is the author
license: Apache-2.0                # the licence's SPDX name
platform: pio                      # the platform it works on, or several: [pio, zephyr]
version: 1.0.0                     # only when the first header has no @version tag

kind: driver                       # driver, middleware, rtos, protocol, filesystem,
                                   # utility or bsp: library.json's keywords
category: storage                  # sensor, storage, display, communication, wireless,
                                   # rtos, timing, power, input, math or system
provides: []                       # what it gives other libraries: [rtos] for an RTOS

requires:
  lib_installer: 4.0.0             # the oldest lib-installer that reads this file
  libraries:                       # other libraries, installed first into lib/
    - osal >= 1.0.0                # no owner means nimaltd
    - owner/lib                    # anyone else's, as owner/name
    - owner/lib@v1.2.0             # a tag, branch or commit, not its default branch
    - source: owner/other@v2.9.3   # a repository with no installer.yml of its own,
      manifest: manifests/other.yml  # with one this library carries for it
      minimum: 2.9.0               # the oldest version that will do
  peripherals:                     # hardware it uses, named to the user
    - type: i2c                    # what it is
      note: 400 kHz                # how to set it up

install:
  include_dirs: [src, src/port]    # include folders, only when the guess is wrong:
                                   # the first is library.json's includeDir
  defines:                         # build_flags in platformio.ini, for every environment
    - EXAMPLE_FAST                 # NAME, or NAME=value

headers:                           # .h files; the first is the one to #include
  - src/example.h                  # every file keeps its path: lib/example/src/example.h
  - src/example_config.h           # its settings, in USER CODE lines kept on update
sources:                           # .c and .cpp files, the only ones PlatformIO builds
  - src/example.c
  - src/port/*.c                   # a wildcard, matched the way a shell would:
                                   # * inside one folder, ** across any number of them
  - from: extra/spi.c              # a file that goes somewhere of its own,
    to: src/port/spi.c             # in the library's folder

options:                           # parts the user chooses at install
  uptime:                          # the name typed after --with
    description: Uptime in hours, minutes and seconds  # the question asked
    libraries: []                  # libraries this part needs, installed first
    sources:                       # its files, written like headers and sources above
      - src/example_uptime.c

extras:                            # copied as they are, never compiled
  - LICENSE.md                     # LICENSE.md and NOTICE are the default,
  - NOTICE                         # so leave this out if that is all
  - README.md                      # in the library's folder
  - root: tools                    # 2.1.0: tools/ into the project's folder instead, as
                                   # the library's own, written again on every install

once:                              # the project's own files: made when missing,
                                   # then the user's, never replaced or removed
  - partitions.csv                 # 2.1.0: a path alone lands at that path: partitions.csv
  - from: templates/secrets.h      # to: another place in the project
    to: include/example_secrets.h

run:                               # steps run once the files are in, each asked about first
  - label: make-key                # the name typed after --run
    description: Make the device's key, device.key  # shown with the question
    script: tools/make_key.py      # Python, run with the installer's own Python, from the
                                   # project's folder, or {library}/... in the library's
    args: [device.key]             # or command: [program, arguments], with no shell
    unless: device.key             # skipped when this file is in the project already

pio:                               # read by lib-installer only
  project:                         # what it writes into the project's platformio.ini
    build_flags:                   # flags for every file of the build, after its defines
      - -Wl,-u,_printf_float       # as the compiler takes them: letters, digits and
                                   # _ . + - / = , : only
  library:                         # what it writes into its own library.json
    frameworks: [arduino, espidf]  # the frameworks it builds with, as platformio.ini
                                   # names them; any, "*", when left out
    platforms: [espressif32]       # the platforms it builds for; any, "*", when left out
    dependencies:                  # PlatformIO Registry libraries it needs, as
      - bblanchon/ArduinoJson@^7   # owner/name, with @version when one is needed.
                                   # PlatformIO installs them by itself
```

`pio.project.build_flags` can be given in groups, each under its title, and a flag with a note, as `- -Wl,-u,_printf_float: printf("%f") prints nothing without it`: see [Build flags](#build-flags). What is under `pio.library` goes into `library.json`, which is JSON and has no comments, so its lists are plain, with no title and no note.

Keys only the other platforms read, such as `zephyr`, `esp32` and `arduino`, can stay in the same file. A run on this platform skips them.

Leave `version` out. The installer reads the version from the `@version` tag in the file comment of the first header listed, so it is written in the code and nowhere else.

`requires.lib_installer` is the oldest lib-installer that reads the file correctly. It is checked before anything else in the file is read, so an older installer stops with a message saying to update, rather than read the file wrongly. A manifest asking for 3.0.0 names the platforms it works on under `platform`, as the [README](../README.md#which-platform) says. Write it as three numbers, `3.0.0`: unquoted, YAML reads `1.10` as the decimal number `1.1`, and that is refused.

In YAML, `*` alone starts something else, so write any as `"*"` or `["*"]`, or leave the key out.

What 2.0.0 brought needs a manifest asking for 2.0.0 or newer: `once` files in the project's folder, `run`, or a library it needs given with an `@` or a `manifest`. The version also decides where `once` files go. A manifest asking for 2.0.0 or newer puts them in the project's folder, and one asking for less keeps the meaning it was written for, the library's own folder, so a release tagged before 2.0.0 still installs and builds as it did.

### Where everything goes, from 4.0.0

4.0.0 gives the `pio` section a place for everything the library writes, by where it goes. What it writes into the project's `platformio.ini` is under `pio.project`: `build_flags`, new in 4.0.0, the flags every file of the build gets, written after the library's defines in its block. What it writes into its own `library.json` is under `pio.library`: `frameworks`, `platforms` and `dependencies`, which were right under `pio` before.

| Before 4.0.0 | From 4.0.0 | Written into |
|---|---|---|
| | `pio.project.build_flags` | the library's block of `build_flags` in `platformio.ini`, after its defines |
| `pio.frameworks` | `pio.library.frameworks` | `library.json` |
| `pio.platforms` | `pio.library.platforms` | `library.json` |
| `pio.dependencies` | `pio.library.dependencies` | `library.json` |

A manifest asking for 4.0.0 or newer has the new places. A key of the `pio` section from before is refused there, with the place to use, and so is any other key the section does not hold, such as `framework` for `frameworks`, which was passed by before, and what it said with it. One asking for less keeps the meanings it was written for, and the new keys are refused there: asking for 4.0.0 is what makes an older lib-installer stop and say to update, where it would otherwise pass them by. Any other key is named there in a warning, and the library installs as it did. A library given twice under `dependencies` is refused whatever the manifest asks for: `library.json` holds one version of each, and the second took the first one's place without a word.

A flag goes into `platformio.ini` as it stands, and PlatformIO hands it to the compiler and the linker of every file, so the installer takes one only as the compiler takes it: one or more words of letters, digits and `_ . + - / = , :`, the first an option, such as `-O2`, `-Wl,--gc-sections` or `-I include`. A flag holding anything else is refused when the manifest is read: `;` or `#`, which start a comment there, a quote, `$`, which SCons expands, or a `!` at the start, which has PlatformIO run a command. A flag given twice is refused too. A define with a value in quotes, such as a string, has no place here, as it has none under `install.defines`.

### Paths, from 2.1.0

A manifest asking for 2.1.0 or newer, as one asking for 3.0.0 does, has one rule for every path that names a place in the project's folder: it starts at the project's folder. `{library}` at its start names the library's own folder instead, wherever `--dir` put it. A path that names a file of the library, under `headers`, `sources`, `extras` or `once`, or as a `from`, is a path in the repository, as always.

And every file is copied to the path it has, unchanged, unless a `to` says otherwise, so a path alone is all an entry needs: `src/example.c` lands at `src/example.c` in the library's folder, so `install.layout` is gone, `flat` is refused and `mirror` says nothing new. A `once` file lands at its own path in the project's folder: `- config/partitions.csv` at `config/partitions.csv`, where before 2.1.0 it was written `- from: config/partitions.csv` and took only its name. And `headers` and `sources` need no `files` around them; `files` still reads, but not both at once.

A `to` gives a file another place, where its list puts files. Under `headers`, `sources` and `extras` that is the library's folder, so `- from: src/example.h, to: example.h` lands at the top of it, and the include path follows. Under `once` it is the project's folder, where every `once` file lands. A `root` puts an extra in the project's folder instead of the library's: `- root: tools` takes the library's `tools/` to the project's `tools/`. Code has no `root`, since it is built in the library's folder, and a `once` file needs none. Wherever a `from` would be the same path as its `to` or `root`, leave it out: `- root: tools` is `- from: tools, root: tools`.

| Key | Starts at |
|---|---|
| `headers`, `sources`, `extras`, `once`, `from` | the library's repository |
| `to` under `headers`, `sources` and `extras` | the library's folder |
| `once.to`, `extras.root` | the project's folder |
| `run.script`, `run.unless` | the project's folder, or the library's with `{library}/` |
| `{library}` in `run.args` and `run.command` | the library's folder, as the step names it from the project's folder |

An extra with a `root` lands in the project's folder, as the library's own: a file at `root` itself, the files of a folder under it with their path below it, those a wildcard matches under it with their names; an extra's `to` places them the same way in the library's folder. It is written again on every install, a file of it the new version no longer ships is removed, and an uninstall takes it out. A file already there that the installer did not put there is the user's, and is never written over: the install stops and says so.

In every manifest, a wildcard matches the whole path, the way a shell does, and the same whether the library comes from GitHub or a folder: `*` and `?` stay inside one folder, `**` crosses any number of them, none included, and `[ab]` is one of a set. So `*.c` is the `.c` files at the top, `src/*.c` those in `src`, and `src/**/*.c` every one below `src`, however deep. And two files of the code that would land in one place, such as two `util.c` that `flat` put side by side, are refused when the manifest is read, where the second used to replace the first without a word.

```yaml
extras:
  - root: tools                    # tools/keygen.py and tools/keygen.md, into the project's folder
run:
  - label: signing-key
    script: tools/keygen.py        # from the project's folder
    unless: sign_key.pem
```

A step's script has to be one the install puts in place, an extra with a `root` or a `once` file, or with `{library}`, a file of the library's folder; anything else is refused when the manifest is read. A manifest asking for less than 2.1.0 keeps the meaning it was written for: its script is found in the library as it was fetched, and `{library}` is left as it is written.

### Files of the project's own

A file that belongs to the project rather than to the library goes under `once`: a partition table, a file of secrets for the user to fill in. It is created in the project's folder when it is missing, and is the user's from then on: never replaced by an update, never removed by an uninstall.

```yaml
once:
  - partitions.csv                     # lands at partitions.csv, its own path
  - from: templates/secrets.h
    to: include/example_secrets.h      # a folder inside the project is fine
```

From 2.1.0 a path alone is a file of the library's repository, landing at the same path in the project. A file that goes somewhere else names it with `from`, the file in the repository, and `to`, its place from the project's folder. Before 2.1.0 each entry is a mapping with a `from`, and a `to` left out meant its own name, at the top. A `once` file has no `root`: it always lands in the project's folder. Each is checked before anything is written: `to` stays inside the project, is neither `platformio.ini` nor the record, and does not point into the library's own folder, which every install replaces. Two entries with one `to` are refused. And `from`, like every file a manifest names, stays inside the library: no `..`, no absolute path, no link leading out of it.

Settings belong in the configuration header's USER CODE lines, not in `once`, which is for files outside the library.

### Steps run after the install

Something no file can carry, such as a key made fresh for each device, is made by a step under `run`. It runs once the library's files are in, in the project's folder:

```yaml
extras:
  - root: tools                        # tools/make_key.py, into the project's folder
run:
  - label: make-key
    description: Make the device's key, device.key
    script: tools/make_key.py          # the project's tools/make_key.py
    args: [device.key]
    unless: device.key
```

- `label` names the step, typed after `--run`, in lower case letters, digits, `_` and `-`.
- `description` is shown with the question.
- `script` is a Python file, run with the installer's own Python, so it works on every computer the installer does. From 2.1.0 it is a path from the project's folder, where an extra with a `root` or a `once` file put it, or `{library}/...` in the library's folder, see [Paths, from 2.1.0](#paths-from-210); before, it is a file of the library's repository. Or `command`, a program and its arguments as a list, `[openssl, rand, -out, device.key, "32"]`, run as it is, with no shell. One of the two, never both.
- `args` are added after either.
- `unless` names a file the step makes, from the project's folder. When it is there, the step is skipped without a question.

The step sees where things are in its environment: `INSTALLER_PROJECT`, the project's folder, `INSTALLER_LIBRARY`, the library's folder in it, `INSTALLER_NAME` and `INSTALLER_VERSION`, the library's, `INSTALLER`, `lib-installer`, and `INSTALLER_PLATFORM`, `pio`.

The user is always asked, and is shown exactly what will run. Nothing in the manifest can turn that off, only the user, with `--run` or `--yes`. A step with no `unless` that ran before is not asked about again until what it runs changes, so make it safe to run twice anyway. A step that fails leaves the install as it is and ends the run with exit code 1.

### A library it needs

`requires.libraries` lists the libraries yours needs, each installed first into `lib` when it is missing or older than the version given:

```yaml
requires:
  libraries:
    - osal >= 1.0.0                    # no owner means nimaltd: github.com/nimaltd/osal
    - someone/lib                      # anyone else's, by owner and name
    - someone/lib@v1.2.0               # exactly this tag, branch or commit
    - source: someone/plain@v2.0.0
      manifest: manifests/plain.yml    # an installer.yml for a repository without one
      minimum: 2.0.0
```

Without an `@`, a library comes from its repository's default branch. The last form installs a library whose repository has no `installer.yml` of its own: yours carries one for it, at the path given, written as if it sat at the root of that repository. A library from the PlatformIO Registry is not one of these: name it under `pio.library.dependencies`.

### What PlatformIO needs of a library

- **The header to include first in `headers`.** `library.json` names one include folder, the one the first header listed is in, unless `install.include_dirs` names the folders. A header in any other folder is found too: the installer adds that folder to `library.json` as `-I`, which PlatformIO gives the library and your project alike.
- **`extern "C"` in every header of C code**, when a project in C++ may use it, as one with the Arduino framework does. Without it the linker cannot find a function of a `.c` file.
- **Settings in a configuration header**, between `USER CODE` lines the installer keeps.
- **A define in `install.defines` only when the whole build needs it.** It goes into every environment of the project. A setting that only the library reads belongs in its configuration header.
- **`frameworks` and `platforms` that are true.** Listing too few hides the library from a build that could use it, and the installer warns about it; listing too many lets a build try and fail.

A library made for PlatformIO that ships its own `library.json`, listed under `extras`, `headers` or `sources` so it is installed, keeps it: the installer writes one only for a library that has none.
