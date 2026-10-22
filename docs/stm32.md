# lib-installer for STM32

Installs embedded C libraries into an STM32 project.

Copying two files into a project is easy. Doing it so the build actually picks them up, without clobbering the settings you changed last month, is the part this handles.

This page is what lib-installer does in an STM32 project, and what a library's `installer.yml` can say for STM32. How to install lib-installer, every command, and what is the same on every platform are in the [README](../README.md).

## Installing a library

From the root of your STM32 project, the folder CubeMX made, install a library by its GitHub owner and name:

```bash
lib-installer owner/example
```

To see it work first, take [lib-installer-example-stm32](https://github.com/nimaltd/lib-installer-example-stm32), a library made for trying the installer on. It builds in any STM32 project CubeMX made, with nothing to set up, and blinks an LED without `HAL_Delay()`. Its README walks through an install, an update that keeps a setting you changed, an option, and an uninstall.

### Files that become yours

A library can bring files that belong to your project rather than to the library: a template of a port layer for you to fill in, a linker script section, a note for your own documentation. Each is a start, made for you to change, so it is created in your project's folder only when it is not there:

```
Files
  written example/src/example.h
  created Core/Src/example_port.c  yours from now on
```

From then on it is yours. An update never writes over it, and says so with `kept Core/Src/example_port.c  yours`. An uninstall leaves it where it is, with `kept Core/Src/example_port.c  yours, not removed`. It is not added to any IDE project either: it is your project's own file. STM32CubeIDE builds every file in its source folders, `Core/Src` among them, so there it is built with the rest. In a CMake, Keil or IAR project, which list their files one by one, add it the way you add a file of your own. A library can never put such a file over one the installer manages or CubeMX writes, such as `CMakeLists.txt`, `.cproject`, the `.ioc`, the Makefile or `stm32xxxx_hal_conf.h`, nor outside your project's folder.

### Updating a library

Run the same command again. Every file of the library is replaced, so an update updates, and a library you broke by accident is put right. What you wrote between `USER CODE BEGIN` and `USER CODE END` is kept, the way STM32CubeMX keeps your code when it generates again:

```c
/* USER CODE BEGIN EXAMPLE_CONFIGURATION */
#define EXAMPLE_SIZE  32
/* USER CODE END EXAMPLE_CONFIGURATION */
```

```
Files
  written example/example.h
  written example/example_config.h
  written example/example.c
  kept    example/example_config.h  your USER CODE EXAMPLE_CONFIGURATION

This was an update. The library replaced, what was yours kept.
```

Put your settings, and anything else you add to a library file, inside those sections. Outside them, the next install replaces it. When that would lose something of yours, the file as it was is saved beside it first, and the report says why:

```
  saved   example/example.c.20261006-165940.bak  it was changed outside its USER CODE sections
```

That happens when you edited the library outside a section, when its markers no longer pair, or when the new version no longer has a section you had written in. Take what you need from the `.bak` file, then delete it. A file nobody touched is left as it is, so your build does not compile it again for nothing.

When a new version keeps its files somewhere else, say in `src/`, the update moves your project along with it. Your `example_config.h` goes where the new version looks for it, with your settings between its `USER CODE` lines still in it, rather than a fresh default turning up next to the header. Files the old version installed and the new one no longer has are removed, so an old `example.c` cannot end up compiled beside the new one. Keil, IAR and the Makefile are pointed at the new places, and a file the library gained joins its group there. Anything you put in the library's folder yourself is left alone.

```
Files
  written example/src/example.h
  written example/src/example_config.h
  written example/src/example.c
  moved   example/example_config.h -> example/src/example_config.h  your USER CODE EXAMPLE_CONFIGURATION went with it
  removed example/example.h  no longer part of the library
  removed example/example.c  no longer part of the library
```

### Uninstalling a library

```bash
lib-installer --uninstall example
```

From your project's root, or with `--project`. It takes the library out of every IDE project the installer put it in: its block in `CMakeLists.txt` and the `CMakeLists.txt` in its folder, its include path, source folder and defines in STM32CubeIDE's `.cproject`, its group, include path and defines in Keil and IAR, and its lines in the Makefile. Then its files go:

```
example 2.0.0
out of example

Project
  updated CMake  Removed example from CMakeLists.txt.
  updated STM32CubeIDE  Removed example from the include path, source folders and defines in .cproject.

Files
  removed example/example.h
  removed example/example.c
  saved   example/example_config.h.20261014-163211.bak  it was yours to edit

Done. example is out of the project.
```

What was yours is saved before it goes, as a `.bak` beside it: a configuration file the library created, and any file of the library you wrote in between its `USER CODE` lines or changed by hand. A file you put in the library's folder yourself is left where it is, and the folder with it, and so are the [files that became yours](#files-that-become-yours). A define another installed library also asks for stays.

A library another one needs stays, and the installer says which needs it:

```
Error: spif needs osal, so it stays. Uninstall spif first, or name them all on one line.
```

Name them all, in any order, and each goes after what needs it: `lib-installer --uninstall osal spif`. When the library you took out brought another with it that nothing left in the project needs, the last line names it, with the command that takes it out too.

Uninstall works from `.lib-installer.json`, the record of what was installed and where. For each library it also keeps where it came from, down to the commit, the blocks written into your files, and the steps that ran. A library put in by hand, or a record that was deleted, leaves it nothing to go on. A library installed by a version before 1.11.0 comes out the same way, but its record does not say what it needed, so nothing is named at the end.

### A library that needs another

Some libraries build on another one, such as `osal` for the RTOS. You install only the one you want, and what it needs goes in first:

```
example 2.0.0 needs osal >= 1.0.0, which is not in this project. Installing osal first.
...
Done. #include "osal.h" and you are away.
...
Done. #include "example.h" and you are away.
```

You are asked for its folder like any library. Install a second library that needs `osal`, and the one already in your project is used:

```
spif 3.0.0 needs osal >= 1.0.0. osal 1.0.0 is already in this project, kept.
```

Nothing is asked about it then. A library that goes in this way comes from the release the library needing it names, or else from its default branch. If a library needs a newer `osal` than the one you have, it is updated where it is, and your setting in `osal_config.h`, between its `USER CODE` lines, is kept as always. Everything is fetched before anything is installed, so when a library cannot be had, your project is left as it was.

### What you see

A first install from a downloaded zip, into a CubeMX project that builds with both CMake and STM32CubeIDE:

```
Reading example-main.zip ...

example 2.0.0
What this library does, in one line
middleware / system

Files
  written example/example.h
  written example/example.c
  written example/LICENSE.md
  written example/NOTICE
  written example/README.md
  created example/example_config.h  yours to edit

Project
  updated CMake  Added example to CMakeLists.txt, linked to ${CMAKE_PROJECT_NAME}.
          backup: CMakeLists.txt.20260923-193649.bak
  updated STM32CubeIDE  Added example to the include path and source folders in .cproject.
          Refresh the project in CubeIDE (F5) so it picks up the new files.
          backup: .cproject.20260923-193649.bak

Done. #include "example.h" and you are away.
```

The first line says where the library came from: `Fetching owner/example ...` from GitHub, `Reading ...` from a zip or a folder.

---

## What it does for you

**Finds your IDE and wires the library in.** CMake, STM32CubeIDE, Keil MDK, IAR and CubeMX's Makefile are all handled, and a project can be more than one of them at once.

| IDE | What gets changed |
|---|---|
| CMake | The library gets its own `CMakeLists.txt`, and two lines are appended to yours |
| STM32CubeIDE | The include path, and the source folders where the project lists them, in every build configuration of `.cproject` |
| Keil MDK 5 and 6 | A file group and the include path in `.uvprojx` |
| IAR EWARM | A file group and the include path in `.ewp` |
| Makefile from CubeMX | The sources at the end of `C_SOURCES`, the include folder at the end of `C_INCLUDES` |

CubeMX can write its Makefile again when it generates code, and the library's lines go with it. Run the installer again after that and they are back.

**Never loses your settings.** What you write inside `USER CODE BEGIN` and `USER CODE END` survives every install. Reinstall as often as you like: the library is replaced, your sections are not, and anything else of yours that would be lost is saved to a `.bak` file first.

**Leaves the file looking like you wrote it.** An added line copies the indentation, the line ending and the path separator of the lines around it. These files go into version control, so a correct edit that shows up as a whole file diff is still a bad edit.

**Keeps your CMakeLists.txt short.** Your project gets two lines that never change, and the library's file list lives with the library:

```cmake
# >>> lib-installer: example >>>
add_subdirectory(example)
target_link_libraries(${CMAKE_PROJECT_NAME} PRIVATE example_lib)
# <<< lib-installer: example <<<
```

The target is called `example_lib` rather than `example`, because a project is often named after the library being tried out in it and CMake allows only one target per name. The `PRIVATE` keyword is dropped when your project links its libraries without one, since CMake refuses to mix the two forms.

The generated `example/CMakeLists.txt` declares an INTERFACE target, not a STATIC one. That matters: an INTERFACE target hands its sources to whoever links it, so they are compiled as part of your application and inherit its defines and include paths. That is what lets a driver's `.c` file find `main.h` and the HAL headers. A STATIC library would not see them and would fail to compile.

**Backs up before editing.** Every project file is copied to a timestamped `.bak` first. If the file is not one it recognises, it changes nothing and prints what to click instead.

**Edits the project, not a copy of it.** IAR leaves a `Backup of <name>.ewp` beside the real project when it upgrades one, and that copy is a valid project file whose name sorts first. The workspace file is asked which project is the real one, and backups are skipped.

**Keeps the repository out of your build.** CubeIDE compiles every `.c` under your project, and a library repository ships a test suite with its own `main()`. Left in place, that breaks your build with an error that points nowhere useful. So only the listed files are copied, and a repository that sits inside your project has everything else removed from it.

**Tells you what the library needs.** It reads your `stm32xxxx_hal_conf.h` and `.ioc` and warns before you hit a confusing compile error:

```
Requirements
  check   HAL SPI module is not enabled
          Uncomment HAL_SPI_MODULE_ENABLED in stm32f4xx_hal_conf.h
  ok      GPIO is configured
  check   This library needs an RTOS and none was found
          It expects freertos. Enable it in CubeMX under Middleware.
```

It cannot switch a peripheral on for you. The `.ioc` belongs to CubeMX, and editing it behind CubeMX's back goes wrong quietly.

---

## For someone writing a library

Put an `installer.yml` at the root of the repository. Any library can have one, whoever wrote it, and the one file serves every platform: each reads its own section and leaves the others' alone. Releases before 1.9.0 called it `library.yml`, and the installer still reads that name when there is no `installer.yml`, so a version pinned with `--ref` from before the rename installs as it always did.

Every key the installer reads is below, each with what it does, as a manifest asking for 3.0.0 writes it. Only `name` and its `headers` or `sources` are required; leave out what your library does not need. What changed in 2.1.0, and how a manifest from before reads, is under [Paths, from 2.1.0](#paths-from-210). For a working one to copy, see [lib-installer-example-stm32](https://github.com/nimaltd/lib-installer-example-stm32).

```yaml
name: example                      # the library's name, and its folder in the project
description: Driver for the X chip # one line, shown while installing
repository: https://github.com/owner/example  # where it comes from
license: Apache-2.0                # the licence's SPDX name
platform: stm32                    # the platform it works on, or several: [stm32, zephyr]
version: 1.0.0                     # only when the first header has no @version tag

kind: driver                       # driver, middleware, rtos, protocol, filesystem,
                                   # utility or bsp
category: sensor                   # sensor, storage, display, communication, wireless,
                                   # rtos, timing, power, input, math or system
provides: []                       # what it gives other libraries: [rtos] for an RTOS

requires:
  lib_installer: 3.0.0           # the oldest lib-installer that reads this file
  libraries:                       # other libraries, installed first when missing
    - osal >= 1.0.0                # no owner means nimaltd; >= the oldest that will do
    - owner/lib                    # anyone else's, as owner/name
    - owner/lib@v1.2.0             # a tag, branch or commit, not its default branch
    - source: owner/other@v2.9.3   # a repository with no installer.yml of its own,
      manifest: manifests/other.yml  # with one this library carries for it
      minimum: 2.9.0               # the oldest version that will do
  hal: true                        # uses the STM32 HAL
  cmsis: false                     # uses CMSIS directly
  rtos: optional                   # none, optional, any, freertos, cmsis-os2 or threadx
  hal_modules: [spi]               # must be enabled in stm32xxxx_hal_conf.h, checked
  peripherals:                     # must be set up in CubeMX, checked in the .ioc
    - type: spi                    # the peripheral, as CubeMX names it
      count: 1                     # how many the library needs
      note: Master mode, 8 bit     # how to set it up, shown when it is missing
  c_standard: c11                  # the C standard the code is written for

install:
  include_dirs: [src]              # include folders, only when the guess is wrong
  defines:                         # given to the whole project, beside USE_HAL_DRIVER
    - EXAMPLE_FAST                 # NAME, or NAME=value

headers:                           # .h files; the first is the one to #include
  - src/example.h                  # every file keeps its path: example/src/example.h
  - src/example_config.h           # settings in USER CODE sections, kept on update
  - src/port/*.h                   # a wildcard, matched the way a shell would:
                                   # * inside one folder, ** across any number of them
sources:                           # .c files, added to the build
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

once:                              # the project's own files: made when missing,
                                   # then the user's, never replaced or removed
  - Core/Inc/example_conf.h        # 2.1.0: a path alone lands at that path in the project
  - from: templates/example_port.c # the file in the repository, to the project's folder
    to: Core/Src/example_port.c    # to: another place in the project

run:                               # steps run once the files are in, each asked about first
  - label: make-key                # the name typed after --run
    description: Make the product's key, product.key  # shown with the question
    script: tools/make_key.py      # Python, run with the installer's own Python, from the
                                   # project's folder, or {library}/... in the library's
    args: [product.key]            # or command: [program, arguments], with no shell
    unless: product.key            # skipped when this file is in the project already

extras:                            # copied as they are, never compiled
  - LICENSE.md                     # LICENSE.md and NOTICE are the default,
  - NOTICE                         # so leave this out if that is all
  - README.md                      # in the library's folder
  - docs                           # a folder is copied whole
  - root: tools                    # 2.1.0: tools/ into the project's folder instead, as
                                   # the library's own, written again on every install
```

The sections below say more about the keys that need it.

Leave `version` out. The installer reads the version from the `@version` tag in the file comment of the first header listed, so it is written in the code and nowhere else:

```c
/**
 * @file        example.h
 * @version     2.0.0
 */
```

`requires.lib_installer` is the oldest lib-installer that reads the file correctly. It is checked before anything else in the file is read, so when a manifest starts using something only a newer installer understands, raising this makes an older one stop with a message saying to update, rather than read the file wrongly without a word. A manifest asking for 3.0.0 names the platforms it works on under `platform`, as the [README](../README.md#which-platform) says. Write it as three numbers, `3.0.0`: unquoted, YAML reads `1.10` as the decimal number `1.1`, and that is refused.

Before 3.0.0 the key was `requires.stm32_installer`, and before 2.0.0 `requires.installer`. Both still work, so a manifest written for stm32-installer installs as it did.

What 2.0.0 brought needs a manifest asking for 2.0.0 or newer: `once` files in the project's folder, `run`, or a library it needs given with an `@` or a `manifest`. The version also decides where `once` files go, as [below](#once).

### Paths, from 2.1.0

A manifest asking for 2.1.0 or newer, as one asking for 3.0.0 does, has one rule for every path that names a place in the project's folder: it starts at the project's folder. `{library}` at its start names the library's own folder instead, wherever `--dir` put it. A path that names a file of the library, under `headers`, `sources`, `extras` or `once`, or as a `from`, is a path in the repository, as always.

And every file is copied to the path it has, unchanged, unless a `to` says otherwise, so a path alone is all an entry needs: `src/example.c` lands at `src/example.c` in the library's folder, so `install.layout` is gone, `flat` is refused and `mirror` says nothing new. A `once` file lands at its own path in the project's folder: `- Core/Inc/example_conf.h` at `Core/Inc/example_conf.h`, where before 2.1.0 it was written `- from: Core/Inc/example_conf.h` and took only its name. And `headers` and `sources` need no `files` around them; `files` still reads, but not both at once.

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

`requires.libraries` lists the libraries yours needs, each as its name, or its name with the oldest version that will do:

```yaml
requires:
  lib_installer: 3.0.0
  libraries:
    - osal >= 1.0.0                    # no owner means nimaltd: github.com/nimaltd/osal
    - someone/lib                      # anyone else's, by owner and name
    - someone/lib@v1.2.0               # exactly this tag, branch or commit
    - source: littlefs-project/littlefs@v2.11.0
      manifest: manifests/littlefs.yml # an installer.yml for a repository without one
      minimum: 2.11.0
```

What is missing or older than that goes in first, from its repository's default branch, or from the tag, branch or commit after its `@`. What is already in the project at a version that will do is left alone.

The last form installs a library whose repository has no `installer.yml` of its own: yours carries one for it, at the path given, written as if it sat at the root of that repository.

### defines

Some code reads its settings from a define the compiler is given, not from a file. littlefs is one: it reads a settings header only when built with `-DLFS_DEFINES=lfs_defines.h`. List such a define under `install.defines`, and the installer puts it where the project keeps `USE_HAL_DRIVER`: the generated CMakeLists.txt, every configuration in `.cproject`, every target in Keil, every configuration in IAR, and `C_DEFS` in a CubeMX Makefile.

It goes to the whole project, not only to the library's files, because a define can change what the library's header declares. littlefs built with `LFS_THREADSAFE` has two more members in `struct lfs_config`, and a file of yours that did not see the define would put every member after them in the wrong place, with no error from the compiler.

Write each as `NAME` or `NAME=value`, with letters, digits and `_ . + - /` only. A space or a quote is refused, since each define is written as it stands into XML, a Makefile and a Keil list. An update takes out a define the library no longer lists and changes one whose value it changed. A define the project already sets to another value is left alone and reported, because it may be the user's own choice.

### options

A part of your library that not every project wants, such as spif's port for LittleFS, goes under `options`. Each is asked about at the first install, and its files and the libraries it needs come only with a yes:

```yaml
options:
  littlefs:                         # the name typed after --with
    description: LittleFS file system on the flash
    libraries:
      - littlefs >= 2.11.0          # installed first, like requires.libraries
    headers:                        # under files: before 2.1.0
      - src/spif_lfs.h
    sources:
      - src/spif_lfs.c
```

The `description` is the question, so write it as what the part is. The name is lower case letters, digits, `_` and `-`, since people type it.

An option's files are your library's files like any other. They land in the same folder, are replaced on every install with their USER CODE sections kept, and are removed by the update that turns the option off. So a file belongs to the library or to one option, never both, and a manifest that lists one twice is refused. Every option's files are downloaded whichever are taken, so an answer never needs a second download. Installed in place, the files of an option not taken are deleted from the folder, since STM32CubeIDE would otherwise compile them.

`--with` and `--without` apply to the libraries named on the command line. A library that comes in because another needs it keeps the answer it had, and an option of it that was never chosen stays out.

### USER CODE sections

Mark what the user is meant to change, the way STM32CubeMX marks its generated files. A configuration header, for instance, lists like any other header and carries its settings in a section:

```c
/* USER CODE BEGIN EXAMPLE_CONFIGURATION */
#define EXAMPLE_SIZE  8
/* USER CODE END EXAMPLE_CONFIGURATION */
```

Every install copies all the library's files again and carries each section's text from the user's copy into the section of the same name. So keep a section's name from one version to the next. A section a new version adds starts with what you ship in it, and what is inside a section is never changed by an update, defaults included. Each name is one word, used once per file. Markers that do not pair, a `BEGIN` with no `END` or one inside another, stop the install before anything is written.

### once

A file that belongs to the project rather than to the library goes under `once`: a port layer someone fills in, a template of their own code, anything that is the library's to start and theirs from then on. It is created in the project's folder when it is missing, and is the user's from then on: never replaced by an update, never removed by an uninstall.

```yaml
once:
  - from: templates/example_port.c     # the file in the repository
    to: Core/Src/example_port.c        # its place from the project's folder
```

`from` is a file of the library's repository, and `to` its place from the project's folder. From 2.1.0 a path alone will do, `- Core/Src/example_port.c`, landing at that same path, and a `to` is only needed for another place; before, each entry is a mapping with a `from`, and a `to` left out meant its own name, at the top. A `once` file has no `root`: it always lands in the project's folder. The file is the project's own, so the installer adds it to no IDE project. STM32CubeIDE builds every file in its source folders, such as CubeMX's `Core/Src`, and has `Core/Inc` on its include path; a CMake, Keil or IAR project lists its files one by one, and the user adds it there. Say so in your README.

Each is checked before anything is written. `to` stays inside the project, names none of the files the installer manages or CubeMX writes, `CMakeLists.txt`, `.cproject`, `.project`, the Keil and IAR projects, the Makefile, the `.ioc`, `stm32xxxx_hal_conf.h` and the record, and does not point into the library's own folder, which every install replaces. Two entries with one `to` are refused. And `from`, like every file a manifest names, stays inside the library: no `..`, no absolute path, no link leading out of it.

Settings the user changes belong in USER CODE sections of the library's own files, not in `once`.

**Libraries written for an installer before 2.0.0** keep the meaning `once` had then, so a release tagged before still installs and builds as it did: the file lands in the library's own folder, at its top whatever the layout, and is added to the build. The version `requires` asks for decides which meaning a manifest gets. The rest of this section is about that older meaning.

With `mirror`, give a configuration header a `to` that puts it beside the header including it. At the top, the include path the layout gives would not reach it.

One catch worth knowing: `#include "x.h"` searches the including file's own folder before any include path, so a config sitting beside the header that includes it will always win. That is fine when the library's tests use the same config, and it is why the NimaLTD libraries test against a setting such as `EXAMPLE_MAX_TASKS` rather than a fixed number.

The include path follows the layout on its own: `flat` gives the library folder, `mirror` gives wherever the headers landed. Add `install.include_dirs` only when that guess is wrong.

### run

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

The step sees where things are in its environment: `INSTALLER_PROJECT`, the project's folder, `INSTALLER_LIBRARY`, the library's folder in it, `INSTALLER_NAME` and `INSTALLER_VERSION`, the library's, `INSTALLER`, `lib-installer`, and `INSTALLER_PLATFORM`, `stm32`.

The user is always asked, and is shown exactly what will run. Nothing in the manifest can turn that off, only the user, with `--run` or `--yes`. A step with no `unless` that ran before is not asked about again until what it runs changes, so make it safe to run twice anyway. A step that fails leaves the install as it is and ends the run with exit code 1.

### Easy to get wrong

**A `.c` file is built only when it is listed.** A port layer under `sources` is built like any other source. One under `once`, for a manifest asking for 2.0.0, is the project's and is added to no IDE project, so a port layer every user needs belongs in `files`, with its settings in USER CODE sections. Getting this wrong fails at link time with undefined references and no clue why.

**`kind: rtos` implies `provides: [rtos]`.** A library that is an operating system satisfies another library's RTOS requirement, whether or not you remembered to write it down.

**`LICENSE.md` and `NOTICE` travel with the code.** The Apache licence requires it, and the NOTICE file is what carries your attribution into someone else's product. They are never removed during cleanup.

That is everything the repository needs. There is no installer script to copy in: put the install lines from the top of this page in your README, with your library's name in them.
