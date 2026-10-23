# lib-installer for ESP-IDF

Installs embedded C libraries into an ESP-IDF project, for any ESP32 chip.

A library written for any project has no idea what an ESP-IDF component is. This copies it into your project's `components` folder and makes it a component: its own `CMakeLists.txt`, the ESP-IDF components it uses, its settings in menuconfig, and the symbols it needs in `sdkconfig.defaults`. Then `idf.py build` picks it up like any other component.

This page is what lib-installer does in an ESP-IDF project, and what a library's `installer.yml` can say for ESP-IDF. How to install lib-installer, every command, and what is the same on every platform are in the [README](../README.md).

## Installing a library

From your project's folder, the one holding `CMakeLists.txt` and `main/`, install a library by its GitHub owner and name, then build as always:

```bash
lib-installer owner/example
idf.py build
```

To see it work first, take [lib-installer-example-esp32](https://github.com/nimaltd/lib-installer-example-esp32), a library made for trying the installer on. It builds for any ESP32 chip, with its settings in menuconfig. Its README walks through an install, a setting changed, an option, and an uninstall.

It runs from any shell, ESP-IDF's own included: it needs Python and nothing of ESP-IDF's.

### What happens

Take `example`, installed into a project called `app`:

```
app/
  CMakeLists.txt           not touched, for a library in components/ that
                           adds no lines of its own here
  sdkconfig.defaults       one block added, with the symbols the library needs
  main/
    CMakeLists.txt         example added to PRIV_REQUIRES, when main lists its own
                           or the project builds only what main names
  components/example/
    src/example.h          the library's files, at the paths they have in its repository
    src/example.c
    CMakeLists.txt         written by the installer: idf_component_register()
    Kconfig                written by the installer: the library's settings
```

ESP-IDF builds every folder of `components/` that has a `CMakeLists.txt` calling `idf_component_register()`, so the installer writes one, from the library's `installer.yml`:

```cmake
idf_component_register(
    SRCS
        "src/example.c"
    INCLUDE_DIRS
        "src"
    REQUIRES
        esp_timer
)
```

`REQUIRES` names the ESP-IDF components the library uses, and the libraries it needs, so their headers are on its include path.

The component is named after its folder, `example`. A component of the project takes the place of one of ESP-IDF's with the same name, so a library called `log` would replace ESP-IDF's own logging. When ESP-IDF is set up in the shell you run from, so `IDF_PATH` is set, the installer checks for that before anything is written, and says to install it into a folder of another name:

```
Requirements
  check   ESP-IDF has a component called log, and this one would take its place
          Install it into a folder of another name, such as --dir components/log_lib.
```

### main

`main` is special in ESP-IDF: as long as its `idf_component_register()` lists no `REQUIRES` or `PRIV_REQUIRES` of its own, it uses every component of the project by itself, and nothing in it changes. Once it lists its own, it sees only those, so the installer adds the library to them:

```cmake
idf_component_register(SRCS "main.c"
                       PRIV_REQUIRES example esp_timer)
```

Into `PRIV_REQUIRES` when main has one, otherwise `REQUIRES`.

A project that builds only what `main` names leaves out every other component, so there `main` gets a list even when it had none. ESP-IDF's own examples are built that way, `hello_world` and `blink` among them, with `idf_build_set_property(MINIMAL_BUILD ON)` in the project's `CMakeLists.txt`, and `set(COMPONENTS ...)` does the same:

```cmake
idf_component_register(SRCS "main.c"
                    INCLUDE_DIRS "." PRIV_REQUIRES example)
```

Without it, `#include "example.h"` in main would not be found. A component of your own that uses the library lists it the same way, by its folder's name.

### sdkconfig.defaults

The Kconfig symbols the library needs go into a block at the end of `sdkconfig.defaults`, created when the project has none:

```
# >>> lib-installer: example >>>
# Added by lib-installer, and written again on every install, so set
# example's symbols below this block rather than in it.
CONFIG_FREERTOS_HZ=1000
# <<< lib-installer: example <<<
```

A library that needs no symbol gets no block. A symbol you already set yourself, on or off, is not set again, since the line read last would quietly undo your choice. It is still written in the block, commented out, with the line that set it:

```
# CONFIG_FREERTOS_HZ=1000  (left out: sdkconfig.defaults sets CONFIG_FREERTOS_HZ=100)
```

A library can give its symbols in groups, each under a title, and a symbol with a note, from 4.0.0. The block carries both as comments, so you see why each line is there:

```
# >>> lib-installer: example >>>
# Added by lib-installer, and written again on every install, so set
# example's symbols below this block rather than in it.

# ******************************************************************************
# A faster tick
# ******************************************************************************
# one tick a millisecond
CONFIG_FREERTOS_HZ=1000
# <<< lib-installer: example <<<
```

ESP-IDF reads `sdkconfig.defaults` only for a symbol your `sdkconfig` does not have yet, and `sdkconfig` is what it builds with. So the installer also reads your `sdkconfig`, and names every symbol it holds at another value:

```
Requirements
  check   sdkconfig has CONFIG_FREERTOS_HZ=100, and example needs 1000
          sdkconfig is what ESP-IDF builds with. Set it in idf.py menuconfig.
```

Set it in `idf.py menuconfig`, or delete `sdkconfig` to start again from `sdkconfig.defaults`. The installer never edits `sdkconfig` itself: ESP-IDF writes that file, and it is yours.

Every file is copied aside before it changes, as `sdkconfig.defaults.20261016-190827.bak` and the like, and the files keep their own line endings. Installing twice changes nothing the second time.

### Settings

A library's settings are Kconfig symbols, in `idf.py menuconfig` under the library's name, from the `Kconfig` the installer wrote into its component. Set one there, or in `sdkconfig.defaults` for a fresh `sdkconfig`:

```
CONFIG_EXAMPLE_PERIOD_MS=250
```

The C code reads it as `CONFIG_EXAMPLE_PERIOD_MS`, from `sdkconfig.h`.

### A folder outside components

Pressed Enter at the folder question, a library goes into `components/<name>`, where ESP-IDF finds it by itself. Anywhere else, given with `--dir` or typed as the answer, ESP-IDF has to be told, so a block goes into your project's `CMakeLists.txt`, above `include(project.cmake)`, which is when ESP-IDF looks:

```cmake
cmake_minimum_required(VERSION 3.16)

# >>> lib-installer: example >>>
# Added by lib-installer, since example is not in the components folder,
# where ESP-IDF looks by itself. Delete this block to drop it from the build.
list(APPEND EXTRA_COMPONENT_DIRS "${CMAKE_CURRENT_SOURCE_DIR}/libs/example")
# <<< lib-installer: example <<<

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(app)
```

### Lines a library adds to your CMakeLists.txt

A library can need lines of CMake in your project's `CMakeLists.txt`, and then it says so in its `installer.yml`: above `include(project.cmake)`, for what ESP-IDF reads as the project starts, or at the end of the file, for what needs the project's own targets. The lines of each place go between two lines that name it:

```cmake
# >>> lib-installer: example/before-project >>>
# From example's installer.yml, and written again on every install.
list(APPEND SDKCONFIG_DEFAULTS "${CMAKE_CURRENT_SOURCE_DIR}/example.defaults")
# <<< lib-installer: example/before-project <<<
```

Every block is written again on every install, so put your own lines outside them. An edit made inside one is noticed on the next install, and the file as it was is in the `.bak`. A title the library gives a group of its lines is written among them, between two lines of stars, as in `sdkconfig.defaults`.

### Files that become yours

A library can bring files that belong to your project rather than to the library, such as a `version.txt`, which ESP-IDF reads the project's version from, or a file of settings: a start, made for you to change. Each is created in your project's folder only when it is not there:

```
Files
  written components/example/src/example.h
  created version.txt  yours from now on
```

From then on it is yours. An update never writes over it, and says so with `kept version.txt  yours`. An uninstall leaves it where it is, with `kept version.txt  yours, not removed`. A library can never put such a file over one the installer manages or reads, `CMakeLists.txt`, `main/CMakeLists.txt`, `sdkconfig` and `sdkconfig.defaults`, nor outside your project's folder.

### What you see

A first install from GitHub, into a project whose `main` lists its own components:

```
Fetching owner/example ...

example 1.2.0
Driver for the X chip
driver / storage

Requirements
  note    CONFIG_FREERTOS_HZ=1000 goes into sdkconfig.defaults
  note    Needs I2C, 400 kHz
          Set it up in your code, or in idf.py menuconfig.

Folder to install example into [components/example]:

Files
  written components/example/src/example.h
  written components/example/src/example.c

Project
  updated ESP-IDF component  The component example: wrote CMakeLists.txt, Kconfig.
  updated sdkconfig.defaults  Added example to sdkconfig.defaults.
          backup: sdkconfig.defaults.20261016-190827.bak
  updated main/CMakeLists.txt  Added example to PRIV_REQUIRES in main/CMakeLists.txt, since main lists the components it uses.
          backup: CMakeLists.txt.20261016-190827.bak

Done. #include "example.h" and you are away.
```

The hardware a library uses is yours to set up, which the installer names but does not do.

### Updating a library

Run the same command again. Every file of the library is replaced, so an update updates, and the component's `CMakeLists.txt` and `Kconfig` are written again from the new `installer.yml`, so a source file the new version adds is built without you editing anything. A file that did not change is left alone, so the build does not configure again for nothing.

What you wrote between `USER CODE BEGIN` and `USER CODE END` in a library's file is kept. Outside those lines, the next install replaces it, and when that would lose something of yours the file is saved beside it first, as a `.bak`.

The record of what is installed, and where, is `.lib-installer.json` in your project's folder. For each library it also keeps where it came from, down to the commit, the blocks written into your files, and the steps that ran. Keep it in version control with the rest.

### Uninstalling a library

```bash
lib-installer --uninstall example
```

From your project's folder, or with `--project`. Its block goes from `sdkconfig.defaults`, and its blocks from `CMakeLists.txt` when it has any, its name goes from main's `REQUIRES` and `PRIV_REQUIRES`, and a list left with nothing in it goes too, the files the installer wrote go from its component, and then the library's own files. Installed and then uninstalled, your project's files are back to the byte they were, except the [files that became yours](#files-that-become-yours), which stay.

What was yours is saved before it goes, as a `.bak` beside it: any file of the library you wrote in between its `USER CODE` lines or changed by hand. A file you put in the library's folder yourself is left where it is, and the folder with it.

A setting you set yourself in `sdkconfig.defaults` is your line, and it stays. The symbol it sets went with the library, though, so the installer names every such line, for you to take out:

```
  manual  sdkconfig.defaults  sdkconfig.defaults still sets what came with example, which ESP-IDF no longer knows. Take these lines out:
          CONFIG_EXAMPLE_PERIOD_MS=250
```

Your `sdkconfig` still has the library's settings too. ESP-IDF drops a symbol it no longer knows the next time it writes `sdkconfig`, so there is nothing to do there.

A library another one needs stays, and the installer says which needs it. Name them all, in any order, and each goes after what needs it: `lib-installer --uninstall osal ee24`. When the library you took out brought another with it that nothing left needs, the last line names it, with the command that takes it out too.

### A library that needs another

You install only the one you want, and what it needs goes in first, each as a component of its own, and the one that needs it lists it in its `REQUIRES`. It comes from the release the library names for it, or else from its default branch. One already in the project at a version that will do is left alone. Everything is fetched before anything is installed, so when a library cannot be had, your project is left as it was.

## For someone writing a library

Put an `installer.yml` at the root of the repository. Any library can have one, whoever wrote it, and the one file serves every platform: each reads its own section and leaves the others' alone.

Every key lib-installer reads is below, each with what it does, as a manifest asking for 4.0.0 writes it. Only `name` and its `headers` or `sources` are required; leave out what your library does not need. What changed in 4.0.0, and how a manifest from before reads, is under [Where each line goes, from 4.0.0](#where-each-line-goes-from-400), and what changed in 2.1.0 under [Paths, from 2.1.0](#paths-from-210). For a working one to copy, see [lib-installer-example-esp32](https://github.com/nimaltd/lib-installer-example-esp32).

```yaml
name: example                      # the library's name, its component and its folder
description: Driver for the X chip # one line, shown while installing and in menuconfig
repository: https://github.com/owner/example  # where it comes from
license: Apache-2.0                # the licence's SPDX name
platform: esp32                    # the platform it works on, or several: [esp32, zephyr]
version: 1.0.0                     # only when the first header has no @version tag

kind: driver                       # driver, middleware, rtos, protocol, filesystem,
                                   # utility or bsp
category: storage                  # sensor, storage, display, communication, wireless,
                                   # rtos, timing, power, input, math or system
provides: []                       # what it gives other libraries: [rtos] for an RTOS

requires:
  lib_installer: 4.0.0             # the oldest lib-installer that reads this file
  libraries:                       # other libraries, installed first when missing
    - osal >= 1.0.0                # no owner means nimaltd; >= the oldest that will do
    - owner/lib                    # anyone else's, as owner/name
    - owner/lib@v1.2.0             # a tag, branch or commit, not its default branch
    - source: owner/other@v2.9.3   # a repository with no installer.yml of its own,
      manifest: manifests/other.yml  # with one this library carries for it
      minimum: 2.9.0               # the oldest version that will do
  peripherals:                     # hardware it uses, named to the user
    - type: i2c                    # what it is
      count: 1                     # how many
      note: 400 kHz                # how to set it up

install:
  include_dirs: [src]              # include folders, only when the guess is wrong
  defines:                         # given to the library and every component using it,
    - EXAMPLE_FAST                 # NAME or NAME=value

headers:                           # .h files; the first is the one to #include
  - src/example.h                  # every file keeps its path: components/example/src/example.h
  - src/port/*.h                   # a wildcard, matched the way a shell would:
                                   # * inside one folder, ** across any number of them
sources:                           # .c files, the component's SRCS
  - src/example.c
  - from: src/port/spi.c           # a file that goes somewhere of its own,
    to: port/spi.c                 # in the library's folder

options:                           # parts the user chooses at install
  littlefs:                        # the name typed after --with
    description: LittleFS file system on the flash  # the question asked
    libraries:                     # libraries this part needs, installed first
      - littlefs >= 2.11.0
    sources:                       # its files, written like headers and sources above
      - src/example_lfs.c

extras:                            # copied as they are, never compiled
  - LICENSE.md                     # LICENSE.md and NOTICE are the default,
  - NOTICE                         # so leave this out if that is all
  - README.md                      # in the library's folder: components/example/README.md
  - root: tools                    # 2.1.0: tools/ into the project's folder instead, as
                                   # the library's own, written again on every install

once:                              # the project's own files: made when missing,
                                   # then the user's, never replaced or removed
  - version.txt                    # 2.1.0: a path alone lands at that path: version.txt
  - from: config/example.defaults  # to: another place in the project
    to: example.defaults

run:                               # steps run once the files are in, each asked about first
  - label: make-key                # the name typed after --run
    description: Make the product's key, product.key  # shown with the question
    script: tools/make_key.py      # Python, run with the installer's own Python, from the
                                   # project's folder, or {library}/... in the library's
    args: [product.key]            # or command: [program, arguments], with no shell
    unless: product.key            # skipped when this file is in the project already

esp32:                             # read by lib-installer only
  settings:                        # Kconfig symbols for menuconfig, CONFIG_<name> in the code
    - name: EXAMPLE_POLL_CHUNK     # the symbol, best started with the library's name
      type: int                    # bool, int, hex or string
      default: 32                  # required: true or false, a number, 0x.. or text
      range: [1, 32768]            # int and hex only: [smallest, largest]
      prompt: Bytes read per call  # one line, shown in menuconfig
      help: |                      # as many lines as it takes, shown in menuconfig
        A read by polling moves at most this many bytes per call.
  project:                         # what it writes into the project's own files
    conf:                          # symbols it needs, in its block of sdkconfig.defaults
      - FREERTOS_HZ=1000           # SYMBOL=value: y, n, a number, 0x.. or "text"
      - SPI_MASTER_IN_IRAM         # a symbol alone is set to y
    cmake:                         # lines of the project's CMakeLists.txt, by their place:
      before-project:              # above include(project.cmake)
        - list(APPEND EXTRA_COMPONENT_DIRS "{library}/extra")
      after-project: []            # at its end
  library:                         # what it writes into its own component
    requires:                      # ESP-IDF components the code uses: its REQUIRES
      - esp_timer
      - esp_driver_i2c
    cmake:                         # lines of the component's CMakeLists.txt
      - target_link_libraries(${COMPONENT_LIB} PRIVATE m)
```

Every list under `esp32.project` and `esp32.library` but `requires` can be given in groups, each under its title, and a symbol with a note: see [Titles and notes, from 4.0.0](#titles-and-notes-from-400).

Keys only the other platforms read, such as `requires.hal_modules` and `zephyr`, can stay in the same file. A run on this platform skips them.

Leave `version` out. The installer reads the version from the `@version` tag in the file comment of the first header listed, so it is written in the code and nowhere else.

`requires.lib_installer` is the oldest lib-installer that reads the file correctly. It is checked before anything else in the file is read, so an older installer stops with a message saying to update, rather than read the file wrongly. A manifest asking for 3.0.0 names the platforms it works on under `platform`, as the [README](../README.md#which-platform) says. Write it as three numbers, `3.0.0`: unquoted, YAML reads `1.10` as the decimal number `1.1`, and that is refused.

What 2.0.0 brought needs a manifest asking for 2.0.0 or newer: `once` files in the project's folder, `run`, groups under `esp32.cmake`, or a library it needs given with an `@` or a `manifest`. The version also decides where `once` files go. A manifest asking for 2.0.0 or newer puts them in the project's folder, and one asking for less keeps the meaning it was written for, the library's own folder, so a release tagged before 2.0.0 still installs and builds as it did.

### Where each line goes, from 4.0.0

4.0.0 gives the `esp32` section a place for everything the library writes, by where it goes. What it writes into the project's own files is under `esp32.project`: `conf`, its block in `sdkconfig.defaults`, which `requires.kconfig` listed, and `cmake`, its lines of the project's `CMakeLists.txt`, under `before-project` and `after-project`. What it writes into its own component is under `esp32.library`: `requires`, the components its code uses, which `esp32.requires` listed, and `cmake`, the lines of the component's `CMakeLists.txt`, which `esp32.cmake` had under `component`. `esp32.settings` stays where it was.

| Before 4.0.0 | From 4.0.0 | Written into |
|---|---|---|
| `requires.kconfig` | `esp32.project.conf` | the library's block in the project's `sdkconfig.defaults` |
| `esp32.cmake`, `before-project` | `esp32.project.cmake`, `before-project` | the project's `CMakeLists.txt`, above `include(project.cmake)` |
| `esp32.cmake`, `after-project` | `esp32.project.cmake`, `after-project` | the project's `CMakeLists.txt`, at its end |
| `esp32.cmake`, `component` | `esp32.library.cmake` | the component's `CMakeLists.txt`, after `idf_component_register()` |
| `esp32.requires` | `esp32.library.requires` | `REQUIRES` of the component |
| `esp32.settings` | `esp32.settings` | the component's `Kconfig`, for menuconfig |

The blocks keep their names, `example/before-project` and the rest, so a library that moves its lines to where 4.0.0 has them writes the same files, and a project sees nothing move.

A manifest asking for 4.0.0 or newer has the new places. A key of the `esp32` section from before is refused there, with the place to use, and so is `requires.kconfig`: from 4.0.0 each platform's settings are in its own section, Zephyr's in `zephyr.project.conf`, so a manifest for both keeps each in its place. Any other key the section does not hold, such as `setting` for `settings`, is refused with the keys it does, where before it was passed by, and what it said with it. One asking for less keeps the meanings it was written for, and the new keys are refused there: asking for 4.0.0 is what makes an older lib-installer stop and say to update, where it would otherwise install the library without what they say. Any other key is named there in a warning, and the library installs as it did.

### Paths, from 2.1.0

A manifest asking for 2.1.0 or newer, as one asking for 3.0.0 does, has one rule for every path that names a place in the project's folder: it starts at the project's folder. `{library}` at its start names the library's own folder instead, wherever `--dir` put it. A path that names a file of the library, under `headers`, `sources`, `extras` or `once`, or as a `from`, is a path in the repository, as always.

And every file is copied to the path it has, unchanged, unless a `to` says otherwise, so a path alone is all an entry needs: `src/example.c` lands at `src/example.c` in the library's folder, so `install.layout` is gone, `flat` is refused and `mirror` says nothing new. A `once` file lands at its own path in the project's folder: `- config/partitions.csv` at `config/partitions.csv`, where before 2.1.0 it was written `- from: config/partitions.csv` and took only its name. And `headers` and `sources` need no `files` around them; `files` still reads, but not both at once.

A `to` gives a file another place, where its list puts files. Under `headers`, `sources` and `extras` that is the library's folder, so `- from: src/example.h, to: example.h` lands at the top of it, and the include path follows. Under `once` it is the project's folder, where every `once` file lands. A `root` puts an extra in the project's folder instead of the library's: `- root: tools` takes the library's `tools/` to the project's `tools/`. Code has no `root`, since it is built in the library's folder, and a `once` file needs none. Wherever a `from` would be the same path as its `to` or `root`, leave it out: `- root: tools` is `- from: tools, root: tools`.

And `esp32.cmake` gives its lines under the places they go, with no `label`, `where` or `lines`, the places 4.0.0 shares between `esp32.project.cmake` and `esp32.library.cmake`: see [More CMake for a library](#more-cmake-for-a-library).

| Key | Starts at |
|---|---|
| `headers`, `sources`, `extras`, `once`, `from` | the library's repository |
| `to` under `headers`, `sources` and `extras` | the library's folder |
| `once.to`, `extras.root` | the project's folder |
| `run.script`, `run.unless` | the project's folder, or the library's with `{library}/` |
| `{library}` in `run.args` and `run.command` | the library's folder, as the step names it from the project's folder |
| `{library}` in lines of CMake | `${CMAKE_CURRENT_SOURCE_DIR}/<the library's folder>` in the project's `CMakeLists.txt`, `${COMPONENT_DIR}` in the component's |

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

### Titles and notes, from 4.0.0

Every list under `esp32.project` and `esp32.library` but `requires` can be given in groups, each under its title, and a symbol with a note. The installer writes both into the file the list goes into, as comments, so whoever reads the project's `sdkconfig.defaults`, or the component's `CMakeLists.txt`, sees why each line is there:

```yaml
esp32:
  project:
    conf:
      A faster tick:
        - FREERTOS_HZ=1000: one tick a millisecond
      Quiet logs:
        - LOG_DEFAULT_LEVEL_WARN
        - LOG_COLORS=n: plain text, for a file
  library:
    cmake:
      Math:
        - target_link_libraries(${COMPONENT_LIB} PRIVATE m)
```

The block in `sdkconfig.defaults`:

```
# >>> lib-installer: example >>>
# Added by lib-installer, and written again on every install, so set
# example's symbols below this block rather than in it.

# ******************************************************************************
# A faster tick
# ******************************************************************************
# one tick a millisecond
CONFIG_FREERTOS_HZ=1000

# ******************************************************************************
# Quiet logs
# ******************************************************************************
CONFIG_LOG_DEFAULT_LEVEL_WARN=y
# plain text, for a file
CONFIG_LOG_COLORS=n
# <<< lib-installer: example <<<
```

And the component's `CMakeLists.txt`:

```cmake
# >>> lib-installer: example/component >>>
# From example's installer.yml, and written again on every install.
# ******************************************************************************
# Math
# ******************************************************************************
target_link_libraries(${COMPONENT_LIB} PRIVATE m)
# <<< lib-installer: example/component <<<
```

- A list is either plain, as it always was, or a mapping of titles to their lists. A plain list is written as it always was, with no title.
- A title is one line, written between two lines of stars, 80 columns wide, above its group, and a group after the first starts after a blank line. The same holds in the lines of CMake, in the project's file and the component's.
- A note follows its symbol after a colon, `LOG_COLORS=n: plain text`, and is written as a comment of its own above the symbol's line. A symbol the project sets itself keeps its note, above the line left out.
- A line of CMake takes a title but no note: a line holding `: ` is CMake's own, and goes in quotes, so that YAML reads it as a line. A title or a note holding `: ` goes in quotes too, as any YAML text does.
- `esp32.library.requires` is a plain list of names, with no title and no note.
- A title or a note is one line, and none may hold what the installer marks its blocks with, `>>>`, `<<<` or `USER CODE`, nor read as a setting, as `CONFIG_X is not set` does. Such a manifest is refused when it is read.
- Two groups with one title are refused, as is any key given twice, and so is one symbol given twice: the line read last would quietly undo the first.

### More CMake for a library

A library that needs more than its files and its defines, a library linked in, an option for its compiler, or a line in the project's own `CMakeLists.txt`, lists the lines by the file each goes into: the project's under `esp32.project.cmake`, by their place, and the component's own under `esp32.library.cmake`:

```yaml
esp32:
  project:
    cmake:
      before-project:
        - list(APPEND SDKCONFIG_DEFAULTS "${CMAKE_CURRENT_SOURCE_DIR}/example.defaults")
      after-project:
        - idf_component_get_property(main_lib main COMPONENT_LIB)
        - target_compile_definitions(${main_lib} PRIVATE EXAMPLE_IN_MAIN)
  library:
    cmake:
      - target_link_libraries(${COMPONENT_LIB} PRIVATE m)
      - target_compile_options(${COMPONENT_LIB} PRIVATE -O2)
```

| Key | Written into | For |
|---|---|---|
| `esp32.library.cmake` | the component's `CMakeLists.txt`, after `idf_component_register()`, where `${COMPONENT_LIB}` is its own library | the component itself |
| `esp32.project.cmake`, `before-project` | the project's `CMakeLists.txt`, above `include($ENV{IDF_PATH}/tools/cmake/project.cmake)` | what ESP-IDF reads as the project starts, such as `EXTRA_COMPONENT_DIRS` or `SDKCONFIG_DEFAULTS` |
| `esp32.project.cmake`, `after-project` | the project's `CMakeLists.txt`, at its end | what needs the project's own targets, every component's library among them |

The lines of each place are written as one block, between two lines that name the library and the place, `# >>> lib-installer: example/before-project >>>` and its pair, and `example/component` for the component's own, in the manifest's order. Every install writes them again: a place whose lines changed is updated, and one the manifest no longer has is taken out. A line keeps the spaces it starts with, so the body of an `if()` can be indented. `{library}` in a line names the library's folder, as `${CMAKE_CURRENT_SOURCE_DIR}/components/example` in the project's file and `${COMPONENT_DIR}` in the component's, wherever `--dir` put it; anything else in a line is CMake's own, written as it stands. A line holding a colon, as `message()` often does, goes in quotes, or YAML reads it as a mapping.

An option brings lines of its own under `options.<name>.esp32.project.cmake` and `options.<name>.esp32.library.cmake`, the same way, written while it is chosen and taken out by the update that turns it off. Its blocks are named after it and the place, `example/littlefs-component`, so they never meet the library's.

One thing about `SDKCONFIG_DEFAULTS`: once it is set, ESP-IDF reads only the files it lists, and no longer `sdkconfig.defaults` by itself. A group that adds a file to it names `sdkconfig.defaults` first, when the project has one and nothing set the list yet:

```cmake
if(NOT SDKCONFIG_DEFAULTS AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/sdkconfig.defaults")
    set(SDKCONFIG_DEFAULTS "${CMAKE_CURRENT_SOURCE_DIR}/sdkconfig.defaults")
endif()
list(APPEND SDKCONFIG_DEFAULTS "${CMAKE_CURRENT_SOURCE_DIR}/example.defaults")
```

A component of headers alone is an interface library, so its lines use `INTERFACE` where one with sources uses `PRIVATE` or `PUBLIC`. The lines run when the user configures the build, the same as a `CMakeLists.txt` the library ships itself would, so they are the library's to answer for.

The forms from before 4.0.0 still install. A manifest asking for 2.1.0 or 3.0.0 gives every line under `esp32.cmake`, under its place, `component`, `before-project` or `after-project`, and an option's under `options.<name>.esp32.cmake`; the blocks have the same names as 4.0.0's. Before 2.1.0, a list of groups, each with a `label`, a `where`, `component` when left out, and its `lines`, writes each group as a block named after its label, `example/<label>`; a manifest moving to places has its old blocks taken out on the next install, and the new ones written. The form from before 2.0.0, a plain list of lines, is one group in `component`, written as it always was.

The user has a place in the component's file too. Its last lines are a `USER CODE` section, empty to start with, and every install keeps what is written in it, the way a configuration header keeps settings:

```cmake
# USER CODE BEGIN EXAMPLE_CMAKE
target_compile_definitions(${COMPONENT_LIB} PRIVATE EXAMPLE_DEBUG=1)
# USER CODE END EXAMPLE_CMAKE
```

On an uninstall, a section with something in it is saved as a `.bak` before the file goes.

### Files of the project's own

A file that belongs to the project rather than to the library goes under `once`: a `version.txt`, which ESP-IDF reads the project's version from, a file of settings for `SDKCONFIG_DEFAULTS`, a partition table. It is created in the project's folder when it is missing, and is the user's from then on: never replaced by an update, never removed by an uninstall.

```yaml
once:
  - version.txt                        # lands at version.txt, its own path
  - from: config/partitions.csv
    to: partitions.csv                 # a place of its own
```

From 2.1.0 a path alone is a file of the library's repository, landing at the same path in the project, so a repository that keeps these files where the project keeps them needs nothing more. A file that goes somewhere else names it with `from`, the file in the repository, and `to`, its place from the project's folder. Before 2.1.0 each entry is a mapping with a `from`, and a `to` left out meant the file's name alone, at the top. A `once` file has no `root`: it always lands in the project's folder. A folder inside the project is fine.

Each is checked before anything is written. `to` stays inside the project, names none of the files the installer manages or reads, `CMakeLists.txt`, `main/CMakeLists.txt`, `sdkconfig`, `sdkconfig.defaults` and the record, and does not point into the library's own folder, which every install replaces. Two entries with one `to` are refused. And `from`, like every file a manifest names, stays inside the library: no `..`, no absolute path, no link leading out of it.

What the user changes in their settings belongs in USER CODE sections of the library's own files, or in menuconfig, not in `once`, which is for files outside the library.

### Steps run after the install

Something no file can carry, such as a key made fresh for each product, is made by a step under `run`. It runs once the library's files are in, in the project's folder:

```yaml
extras:
  - root: tools                        # tools/make_key.py, into the project's folder
run:
  - label: make-key
    description: Make the product's key, product.key
    script: tools/make_key.py          # the project's tools/make_key.py
    args: [product.key]
    unless: product.key
```

- `label` names the step, typed after `--run`, in lower case letters, digits, `_` and `-`.
- `description` is shown with the question.
- `script` is a Python file, run with the installer's own Python, so it works on every computer the installer does. From 2.1.0 it is a path from the project's folder, where an extra with a `root` or a `once` file put it, or `{library}/...` in the library's folder, see [Paths, from 2.1.0](#paths-from-210); before, it is a file of the library's repository. Or `command`, a program and its arguments as a list, `[openssl, rand, -out, product.key, "32"]`, run as it is, with no shell. One of the two, never both.
- `args` are added after either.
- `unless` names a file the step makes, from the project's folder. When it is there, the step is skipped without a question.

The step sees where things are in its environment: `INSTALLER_PROJECT`, the project's folder, `INSTALLER_LIBRARY`, the library's folder in it, `INSTALLER_NAME` and `INSTALLER_VERSION`, the library's, `INSTALLER`, `lib-installer`, and `INSTALLER_PLATFORM`, `esp32`.

The user is always asked, and is shown exactly what will run. Nothing in the manifest can turn that off, only the user, with `--run` or `--yes`. A step with no `unless` that ran before is not asked about again until what it runs changes, so make it safe to run twice anyway. A step that fails leaves the install as it is and ends the run with exit code 1.

### A library it needs

`requires.libraries` lists the libraries yours needs, each installed first when it is missing or older than the version given:

```yaml
requires:
  libraries:
    - osal >= 1.0.0                    # no owner means nimaltd: github.com/nimaltd/osal
    - someone/lib                      # anyone else's, by owner and name
    - someone/lib@v1.2.0               # exactly this tag, branch or commit
    - source: littlefs-project/littlefs@v2.11.0
      manifest: manifests/littlefs.yml # an installer.yml for a repository without one
      minimum: 2.11.0
```

Without an `@`, a library comes from its repository's default branch. The last form installs a library whose repository has no `installer.yml` of its own: yours carries one for it, at the path given, written as if it sat at the root of that repository.

### Settings in the code

ESP-IDF writes every setting into `sdkconfig.h`, so the library's code reads it as a macro once it includes that. One header can serve ESP-IDF and any other project, taking the setting from Kconfig when it is there:

```c
#if __has_include("sdkconfig.h")
#include "sdkconfig.h"
#endif

#ifdef CONFIG_EXAMPLE_POLL_CHUNK
#define EXAMPLE_POLL_CHUNK          CONFIG_EXAMPLE_POLL_CHUNK
#endif

#ifndef EXAMPLE_POLL_CHUNK
#define EXAMPLE_POLL_CHUNK          32U
#endif
```

A `bool` setting that is off is not defined at all, which is how Kconfig does it, so test it with `#ifdef`. A `string` arrives in quotes, ready for C.

Each setting is checked at install, since all of it is written into a Kconfig file: a default of the wrong type, one outside its range, or a name Kconfig would refuse stops the install with the reason, before anything is written.

### A library with its own component

A library that ships a `CMakeLists.txt` of its own, listed under `extras` or `files` so it is installed, knows its build better than the installer does. It is used as it is: nothing is written into its folder, and only the project's own files get what they need.
