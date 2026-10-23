# lib-installer

Installs embedded C libraries into STM32, Zephyr, ESP-IDF, Arduino and PlatformIO projects.

Copying two files into a project is easy. Doing it so the build actually picks them up, without clobbering the settings you changed last month, is the part this handles. One command does it on every platform, from GitHub, from a downloaded zip, or from a folder.

It works with any library that has an `installer.yml` at the root of its repository. I wrote it for my own [NimaLTD](https://github.com/nimaltd) libraries, and they all have one, but nothing in it is tied to them: add an `installer.yml` to yours, as shown [below](#for-someone-writing-a-library), and it installs the same way. One `installer.yml` serves every platform, so one library can go into an STM32 project, a Zephyr application, an ESP-IDF project, an Arduino sketch and a PlatformIO project alike.

| Platform | Its name in `installer.yml` and `--platform` | What lib-installer does there |
|---|---|---|
| STM32, with CubeMX | `stm32` | Registers the library with CMake, STM32CubeIDE, Keil MDK, IAR or CubeMX's Makefile. [More](https://github.com/nimaltd/lib-installer/blob/main/docs/stm32.md) |
| Zephyr, and nRF Connect SDK | `zephyr` | Makes the library a Zephyr module, adds it to the build and switches it on in `prj.conf`. [More](https://github.com/nimaltd/lib-installer/blob/main/docs/zephyr.md) |
| ESP-IDF | `esp32` | Makes the library a component, with its settings in menuconfig. [More](https://github.com/nimaltd/lib-installer/blob/main/docs/esp32.md) |
| Arduino | `arduino` | Puts the library in the libraries folder, or in one sketch, with the `library.properties` Arduino needs. [More](https://github.com/nimaltd/lib-installer/blob/main/docs/arduino.md) |
| PlatformIO | `pio` | Puts the library in `lib/`, with a `library.json`, and its defines in `platformio.ini`. [More](https://github.com/nimaltd/lib-installer/blob/main/docs/pio.md) |

Before 3.0.0 these were five installers, stm32-installer, zephyr-installer, esp32-installer, arduino-installer and pio-installer. lib-installer is all of them in one, and a project one of them installed into moves over by itself, as [below](#moving-over-from-the-five-installers).

Every command below uses `owner/example`, the library's GitHub owner and name, such as `nimaltd/ee24`. Put the real ones in its place.

---

## Installing a library

Install the installer once. This needs internet:

```bash
pip install lib-installer
```

Then, from your project's folder, install a library by its GitHub owner and name:

```bash
lib-installer owner/example
```

The library's `installer.yml` says which platform it is for, so that is all it takes. To see it work first, take the example library of your platform, made for trying the installer on. Each one's README walks through an install, an update that keeps a setting you changed, an option, and an uninstall:

| Platform | Run it from | Try it with |
|---|---|---|
| STM32 | the project's root, the folder CubeMX made | `lib-installer nimaltd/lib-installer-example-stm32` |
| Zephyr | the application's folder, the one holding `prj.conf` | `lib-installer nimaltd/lib-installer-example-zephyr` |
| ESP-IDF | the project's folder, the one holding `main/` | `lib-installer nimaltd/lib-installer-example-esp32` |
| Arduino | anywhere, or a sketch's folder | `lib-installer nimaltd/lib-installer-example-arduino` |
| PlatformIO | the project's folder, the one holding `platformio.ini` | `lib-installer nimaltd/lib-installer-example-pio` |

Then build as you always do. Any other library goes in the same way, as `lib-installer owner/example`.

To update the installer later, `pip install --upgrade lib-installer`. To remove it, `pip uninstall lib-installer`.

On Windows, if `lib-installer` is not found after installing, pip put it in a folder that is not on your PATH. `python -m lib_installer owner/example` runs the same thing.

On Linux or macOS, if pip refuses with `externally-managed-environment`, use `pipx install lib-installer` instead, and `pipx upgrade lib-installer` to update.

When a newer lib-installer is out, the last line of a run says so, with the command that updates it. It asks PyPI at most once a day, waits no more than two seconds for an answer, and says nothing when there is none. `--no-update-check` turns it off, and so does `INSTALLER_NO_UPDATE_CHECK` set to anything. On a build server, where `CI` is set, it is off already.

A library can need a newer installer than the one you have. It then says so and changes nothing:

```
Error: This library needs lib-installer 4.1.0 or newer, and this one is 4.0.0. Nothing was changed.
Update it with:
    pip install --upgrade lib-installer
```

### Which platform

The platform comes from the library. Its `installer.yml` names it under `platform`, one word, or a list for a library that works on several:

```yaml
platform: zephyr
```

```yaml
platform: [stm32, zephyr, esp32]
```

A library for one platform goes in with nothing more to say. A library for several asks which one your project is, once:

```
example works on more than one platform. Which is this project?
  1  stm32
  2  zephyr
  3  esp32
Platform:
```

After that, your project's record, `.lib-installer.json`, remembers it, so a library for several platforms installs into it without the question, and an uninstall needs nothing more than the library's name.

`--platform` says it on the command line. It is there for a library whose `installer.yml` names no platform, as every one written before 3.0.0, and for a library that names several when nobody is there to answer, as in a script:

```bash
lib-installer owner/example --platform zephyr
```

The installer never guesses from your project's files. A library that names no platform, given no `--platform`, stops before anything is written, and says how to go on:

```
Error: owner/example names no platform in its installer.yml. Say which it goes into with --platform, one of stm32, zephyr, esp32, arduino, pio.
```

And what does not fit is refused, rather than installed into a build it cannot work in: `--platform` the library does not name, a library for one platform given together with one for another, a platform other than the one your project's record says, and an option of another platform, such as `--ide` in a Zephyr application. A library one of yours needs is checked the same way, before anything is written.

### Every command

Each command with `owner/example` standing for the library. An update is the install again. Every option is explained under [Options](#options).

| To | Run |
|---|---|
| Install the installer | `pip install lib-installer` |
| Update the installer | `pip install --upgrade lib-installer` |
| Remove the installer | `pip uninstall lib-installer` |
| See which version you have | `lib-installer --version` |
| See every option | `lib-installer --help` |
| Install a library from GitHub | `lib-installer owner/example` |
| Install one release of it, a branch or a commit | `lib-installer owner/example@v2.0.0` |
| Install it by its GitHub address | `lib-installer https://github.com/owner/example` |
| Install it from a downloaded zip | `lib-installer D:/Downloads/example-main.zip` |
| Install it from a folder on disk | `lib-installer D:/Downloads/example-main` |
| Install several at once, such as a library and the zip of one it needs | `lib-installer D:/Downloads/example-main.zip D:/Downloads/osal-main.zip` |
| Say the platform, for a library that names none, or several | `lib-installer owner/example --platform zephyr` |
| Install into a folder you choose, without the question | `lib-installer owner/example --dir Libs/example` |
| Install into a project you are not running from | `lib-installer owner/example --project D:/Work/MyBoard` |
| Take an option of the library without the question | `lib-installer owner/example --with littlefs` |
| Leave an option out, or take it out of a library already installed | `lib-installer owner/example --without littlefs` |
| Run a step of the library without the question | `lib-installer owner/example --run make-key` |
| Leave a step unrun, without the question | `lib-installer owner/example --no-run make-key` |
| Answer every question with the answer offered, and run every step, for a script | `lib-installer owner/example --yes` |
| Install from a private repository | `lib-installer owner/example --key github_pat_...` |
| Give the token once, for every run after | `GITHUB_TOKEN` set to it, see [A private repository](#a-private-repository) |
| Leave out the check for a newer installer | `lib-installer owner/example --no-update-check` |
| STM32: register with one IDE only, of `cmake`, `cubeide`, `keil`, `iar` and `makefile` | `lib-installer owner/example --ide cubeide` |
| Zephyr: choose the Kconfig file the libraries are switched on in | `lib-installer owner/example --conf boards/x.conf` |
| Arduino: into the libraries folder, for every sketch | `lib-installer owner/example --into libraries` |
| Arduino: into the `src` folder of the sketch this is run from | `lib-installer owner/example --into sketch` |
| Arduino: give the sketchbook folder, when it should not be looked for | `lib-installer owner/example --sketchbook D:/Arduino` |
| Update a library | `lib-installer owner/example` |
| Uninstall a library | `lib-installer --uninstall example` |
| Uninstall several, in any order | `lib-installer --uninstall osal example` |
| Run it when `lib-installer` is not found | `python -m lib_installer owner/example` |

### Every feature

What lib-installer does, and how. The version is the oldest a library's `installer.yml` has to ask for, under `requires.lib_installer`, to use it; with none given, every version does it. The keys of `installer.yml` are under [For someone writing a library](#for-someone-writing-a-library), and those of one platform on its page.

| Feature | How | Since |
|---|---|---|
| A library from GitHub, by owner and name, or one release, branch or commit of it | `lib-installer owner/example`, `owner/example@v2.0.0` or `--ref`, see [What to install](#what-to-install) | |
| A library from a downloaded zip or a folder, without internet | `lib-installer D:/Downloads/example-main.zip`, see [Without internet](#without-internet) | |
| Several libraries in one run | `lib-installer owner/example owner/other` | |
| A library in a private repository | `--key`, or `GITHUB_TOKEN`, see [A private repository](#a-private-repository) | |
| Through a proxy, every file tried again on a bad connection | `HTTPS_PROXY`, see [On a bad connection](#on-a-bad-connection) | |
| One `installer.yml` for every platform | `platform: [stm32, zephyr, esp32, arduino, pio]`, `--platform`, see [Which platform](#which-platform) | 3.0.0 |
| A library that does not fit refused before anything is written: another platform, a newer installer, an option of another platform | | |
| The libraries it needs, installed first, each at a version that will do | `requires.libraries`, with `>=`; with `@` a release of its own, and with `manifest` one for a repository with no `installer.yml`, see [A library that needs another](#a-library-that-needs-another) | `@` and `manifest`: 2.0.0 |
| Parts of a library the user chooses | `options`, `--with`, `--without`, see [Parts you choose](#parts-you-choose) | |
| An update that keeps the user's settings | `USER CODE BEGIN` and `END` in the library's files; anything else of the user's saved as a `.bak`, see [Updating a library](#updating-a-library) | |
| Files that become the project's own, made once and never written over | `once`, see [Files that become yours](#files-that-become-yours) | 2.0.0 |
| Steps run once the files are in, each asked about first | `run`, `--run`, `--no-run`, `--yes`, see [Steps a library runs](#steps-a-library-runs) | 2.0.0 |
| Every file at the path it has in the repository; wildcards; paths from the project's folder, `{library}` for the library's | `src/**/*.c`, `to`, `{library}` | 2.1.0 |
| The library's own files in the project's folder, such as its tools | `extras` with `root` | 2.1.0 |
| An uninstall that gives the project's files back to the byte | `--uninstall`, see [Uninstalling a library](#uninstalling-a-library) | |
| A record of what is installed, from where, down to the commit | `.lib-installer.json`, kept with the project | |
| A project of one of the five installers moved over | by itself, on the first run, see [Moving over](#moving-over-from-the-five-installers) | 3.0.0 |
| A key given twice in one place refused, where YAML would keep the last without a word | | 4.0.0 |
| A key a platform's section does not have, such as a misspelt one, refused, with the keys it holds; a manifest asking for less is told about it, and installs as it did | | 4.0.0 |
| The folders of the include path checked before any project file gets them: inside the library, and nothing an IDE's file would read as more than a path | `install.include_dirs` | |
| STM32: registered with CMake, STM32CubeIDE, Keil MDK, IAR or CubeMX's Makefile; HAL modules, peripherals and RTOS checked against the project | `--ide`, `requires.hal_modules`, `requires.peripherals`, `requires.rtos`, see [STM32](https://github.com/nimaltd/lib-installer/blob/main/docs/stm32.md) | |
| Zephyr: a module of the application, switched on in `prj.conf`, its settings in Kconfig and menuconfig | `zephyr.symbol`, `zephyr.settings`, `--conf`, see [Zephyr](https://github.com/nimaltd/lib-installer/blob/main/docs/zephyr.md) | |
| Zephyr: every line it writes under where it goes, the application's own files or its own folder | `zephyr.project`: `conf`, `sysbuild`, `cmake`; `zephyr.library`: `kconfig`, `conf`, `cmake` | 4.0.0 |
| Zephyr: lists in groups under their titles, a setting with a note, written into the files as comments | see [Titles and notes](https://github.com/nimaltd/lib-installer/blob/main/docs/zephyr.md#titles-and-notes-from-400) | 4.0.0 |
| ESP-IDF: a component, its settings in menuconfig, its lines in `sdkconfig.defaults` and in CMake | `esp32.settings`, `esp32.project`, `esp32.library`, see [ESP-IDF](https://github.com/nimaltd/lib-installer/blob/main/docs/esp32.md) | |
| ESP-IDF: every line it writes under where it goes, the project's own files or its component | `esp32.project`: `conf`, `cmake`; `esp32.library`: `requires`, `cmake`; before, `requires.kconfig`, `esp32.requires` and `esp32.cmake` | 4.0.0 |
| ESP-IDF: lists in groups under their titles, a symbol with a note, written into the files as comments | see [Titles and notes](https://github.com/nimaltd/lib-installer/blob/main/docs/esp32.md#titles-and-notes-from-400) | 4.0.0 |
| Arduino: into the libraries folder, for every sketch, or into one sketch, with its `library.properties` | `--into`, `--sketchbook`, `arduino`, see [Arduino](https://github.com/nimaltd/lib-installer/blob/main/docs/arduino.md) | |
| PlatformIO: into `lib/`, with its `library.json`, and its defines in `platformio.ini` | `pio.library`, `install.defines`, see [PlatformIO](https://github.com/nimaltd/lib-installer/blob/main/docs/pio.md) | |
| PlatformIO: flags for every file of the build, in groups under their titles and with notes, as comments of `platformio.ini` | `pio.project.build_flags`, see [Build flags](https://github.com/nimaltd/lib-installer/blob/main/docs/pio.md#build-flags) | 4.0.0 |
| PlatformIO: what goes into `library.json` under `library` | `pio.library`: `frameworks`, `platforms`, `dependencies`; before, right under `pio` | 4.0.0 |

### On a bad connection

A file that does not arrive is tried again, five times in all, 1, 2, 4 and 8 seconds apart. The tries take turns between `raw.githubusercontent.com` and `api.github.com`, two hosts on different addresses, so one that is filtered or failing does not stop the install. Every file of every library is fetched before anything is installed, so a run that fails part way leaves your project as it was: run it again.

Behind a proxy, or a VPN client that offers one, point the installer at it. In Command Prompt:

```bash
set HTTPS_PROXY=http://127.0.0.1:10809
```

In PowerShell:

```bash
$env:HTTPS_PROXY = "http://127.0.0.1:10809"
```

On Linux and macOS, `export HTTPS_PROXY=http://127.0.0.1:10809`. Use your proxy's own address and port. On Windows, a proxy set in the system settings is used without this.

pip has its own retries, and on a slow link it helps to give it more time: `pip install --retries 10 --timeout 60 lib-installer`. When nothing gets through, install from zips, as below.

### Without internet

On a machine that has internet, save the installer as a file:

```bash
pip download lib-installer
```

That saves one file, such as `lib_installer-4.0.0-py3-none-any.whl`, where the number is the installer's version. Download the library too, from the green **Code** button, **Download ZIP**. Copy both to the machine that has no internet, then from your project:

```bash
pip install lib_installer-4.0.0-py3-none-any.whl
lib-installer D:/Downloads/example-main.zip
```

Neither line needs the internet. The installer needs nothing but itself, and the library comes from the zip, which the installer reads for its platform without unpacking it.

If the library needs another one, such as `osal`, download that zip as well and give both on one line:

```bash
lib-installer D:/Downloads/example-main.zip D:/Downloads/osal-main.zip
```

Forget it, and the installer stops before writing anything, naming the zip it is missing.

### A private repository

A library in a private repository installs the same way, given a GitHub token that can read it. Make one once:

1. Open [github.com/settings/personal-access-tokens](https://github.com/settings/personal-access-tokens) and click **Generate new token**.
2. Give it a name and an expiry. Under **Resource owner**, pick the account or the organisation that owns the repository.
3. Under **Repository access**, choose **Only select repositories** and pick the library's repository.
4. Under **Permissions**, set **Contents** to **Read-only**:
   - Older layout: open **Repository permissions** and change **Contents** from **No access** to **Read-only**.
   - Newer layout: click **+ Add permissions**, tick **Contents**, then set its access to **Read-only**.

   **Metadata** comes with it by itself. Contents is the one that matters: without it the token can see the repository but not read a file of it.
5. Click **Generate token**, and copy it. GitHub shows it only once.

Then give it with `--key`:

```bash
lib-installer owner/example --key github_pat_...
```

Or put it in `GITHUB_TOKEN` once, and install by name as usual. That keeps it out of your shell's history, where `--key` leaves it:

**Windows, PowerShell:**

```powershell
$env:GITHUB_TOKEN = "github_pat_..."
lib-installer owner/example
```

**Windows, Command Prompt:**

```bat
set GITHUB_TOKEN=github_pat_...
lib-installer owner/example
```

**Linux and macOS:**

```bash
export GITHUB_TOKEN=github_pat_...
lib-installer owner/example
```

`--key` comes first when both are there. `GH_TOKEN` works as well, and if you use the `gh` command, `gh auth token` prints the token you are signed in with. Whichever way it comes, the token is sent to GitHub and nowhere else.

When the token cannot read the library, the installer says which of these it is:

- **It can see the repository, but cannot read its files.** The token has no Contents permission, only Metadata. Edit the token, and its value stays the same, so the command you ran keeps working: open the tokens page, click the token's name, click **Edit**, set Contents to **Read-only** as in step 4, and click **Update** at the bottom of the page. Then run the same command again.
- **It cannot see the repository.** The repository is not in the token's Repository access. Edit the token as above and add it.
- **GitHub did not accept the token.** It has expired, been revoked, or was copied with a character missing. Make a new one.

A repository of an organisation can need one more step: an organisation that asks for fine-grained tokens to be approved shows the token nothing of its repositories until an owner of the organisation approves it, under its settings, **Personal access tokens**, **Pending requests**.

### What to install

The argument can be any of these, and you can give several at once:

| You have | You type |
|---|---|
| Nothing yet, and internet | `lib-installer owner/example` |
| One release of it, a branch, or a commit | `lib-installer owner/example@v2.0.0` |
| The library's GitHub address | `lib-installer https://github.com/owner/example` |
| The zip from GitHub's **Download ZIP** | `lib-installer D:/Downloads/example-main.zip` |
| That zip unpacked, anywhere on disk | `lib-installer D:/Downloads/example-main` |
| The library's folder, already inside your project | `lib-installer example` |

A bare name with no owner, like `example`, is a NimaLTD library, `nimaltd/example` on GitHub, unless a folder of that name exists where you run it, in which case the folder is used. A path that does not exist is reported as missing rather than looked up on GitHub, so a typo in `D:/Downloads/...` gets a straight answer.

The zip does not need unpacking first. If you did unpack it with Windows' **Extract All**, which puts `example-main` inside another `example-main`, either folder works. A repository still on `master` gives `example-master`, which works the same.

From GitHub, a library comes from its repository's default branch, the one GitHub shows first, whatever the repository calls it. After an `@`, a tag, a branch or a commit takes exactly that instead, and so does a GitHub address ending in `/tree/v2.0.0`. Every file comes from one commit, even when the branch moves on while they download, and the record keeps that commit, so you can always tell what you built with. Its `installer.yml` is read first, for the platform, and is not asked for a second time when the files follow.

### Options

| Option | What it does |
|---|---|
| `--platform zephyr` | The platform to install into: `stm32`, `zephyr`, `esp32`, `arduino` or `pio`. Only for a library whose `installer.yml` names none, or names several. See [Which platform](#which-platform) |
| `--ref v2.0.0` | A tag, a branch or a commit to take from GitHub, the same as `owner/example@v2.0.0`. When not given, the repository's default branch. It applies to the libraries you name, and a library one of them needs comes from the release its `installer.yml` names, or from its default branch |
| `--dir Libs/example` | The folder of your project to install into, for one library. Asked for when not given, as [below](#the-folder-question) |
| `--project D:/Work/MyBoard` | Your project's folder, when you are not running from it |
| `--with littlefs` | Take this part of the library without being asked. Give it once for each part. See [Parts you choose](#parts-you-choose) |
| `--without littlefs` | Leave this part out, or take it out of a library already installed |
| `--run make-key` | Run this step of the library without being asked. Give it once for each step. See [Steps a library runs](#steps-a-library-runs) |
| `--no-run make-key` | Leave this step unrun, without being asked |
| `--yes` | Take the answer each question offers, without asking, and run every step. For a script or a build server |
| `--no-update-check` | Do not ask PyPI whether a newer lib-installer is out |
| `--key github_pat_...` | A GitHub token, for a library in a private repository. See [A private repository](#a-private-repository) |
| `--uninstall example` | Take the library out of the project. See [Uninstalling a library](#uninstalling-a-library) |
| `--version` | Show which version of the installer you have, and do nothing else |
| `--ide cubeide` | STM32 only. Register with this IDE only: `cmake`, `cubeide`, `keil`, `iar` or `makefile`. Every one found, when not given |
| `--conf boards/x.conf` | Zephyr only. The Kconfig file that switches the libraries on. Asked when the application has more than one, `prj.conf` otherwise |
| `--into libraries` | Arduino only. Into the libraries folder, for every sketch, or with `sketch`, into the `src` folder of the sketch this is run from. Asked when run from a sketch |
| `--sketchbook D:/Arduino` | Arduino only. The sketchbook folder, the one holding `libraries`, when the installer should not look for it |

An option of one platform, given in a project of another, is refused rather than ignored, so a script that says `--ide cubeide` never installs into a Zephyr application without a word.

`--ref` holds a project on one release, which is useful when you need exactly what you built with last time:

```bash
lib-installer owner/example --ref v2.0.0         # a tag
lib-installer owner/example --ref develop        # a branch
lib-installer owner/example --ref 00949e695e16   # an exact commit
lib-installer owner/example@v2.0.0               # the same, for this library alone
```

### The folder question

Without `--dir`, you are asked where the library should go:

```
Folder to install example into [modules/example]:
```

Press Enter for the default, or the folder it is already in when this is an update. In a script or on a build server, where nobody is there to answer, the default is taken without asking, rather than waiting for ever. The default is where the platform finds a library by itself:

| Platform | The default folder |
|---|---|
| STM32 | `example`, at the project's root |
| Zephyr | `modules/example` |
| ESP-IDF | `components/example` |
| Arduino | `example` in the libraries folder, or `src/example` in a sketch |
| PlatformIO | `lib/example` |

**From GitHub, from a zip, or from a folder outside your project**, the files the library's `installer.yml` lists are copied into that folder. Nothing else comes with them, so the library's tests never reach your build. The zip or folder you gave is left exactly as it was.

**A folder already inside your project** becomes the library where it stands. The files its `installer.yml` lists stay at their paths, your config file is created, and everything that belongs to the repository rather than your firmware is removed from it, the test folder above all. `--dir` does not apply here, since the folder is already where it is going.

### Parts you choose

Some libraries have a part not every project wants, such as LittleFS support in a flash driver. The first install asks about each one:

```
Options
  littlefs   LittleFS file system on the flash. Add it? [y/N]:
```

Anything but `y` or `yes` leaves it out. A yes brings the part's files, and any library it needs, which goes in first like any other. In a script, where nobody can answer, it is left out, and `--with littlefs` takes it without a question.

The answer is kept in `.lib-installer.json` in your project, so an update does not ask again. It says what it kept, and how to change it:

```
Options
  littlefs   yes, as before. Change it with --without littlefs
```

Change your mind with `--with` or `--without` on any later run. `--without littlefs` takes the part's files out of the library's folder and out of the build. A library the part brought stays, since something else may use it by then. A part that a new version adds is asked about on that update. Keep `.lib-installer.json` with your project, in version control: without it the installer remembers nothing, and asks again.

### Files that become yours

A library can bring files that belong to your project rather than to the library: a template of a port layer for you to fill in, a `VERSION`, an overlay for each chip. Each is a start, made for you to change, so it is created in your project's folder only when it is not there:

```
Files
  written example/src/example.h
  created Core/Src/example_port.c  yours from now on
```

From then on it is yours. An update never writes over it, and says so with `kept Core/Src/example_port.c  yours`. An uninstall leaves it where it is, with `kept Core/Src/example_port.c  yours, not removed`. A library can never put such a file over one the installer manages, such as `CMakeLists.txt`, `prj.conf` or `platformio.ini`, nor outside your project's folder. In an Arduino libraries folder, which is no sketch's own, there is no place for such a file, so a library that brings one goes into a sketch.

### Steps a library runs

A library can need something made that no file can carry, such as a key made fresh for each product. It names a step for that, and once its files are in, the installer shows you exactly what will run, and asks:

```
Run
  make-key     Make the product's key, product.key
               python tools/make_key.py product.key
               Run it? [Y/n]:
```

Enter runs it, in your project's folder. A Python script runs with the same Python as the installer, so it works the same on every computer. `n` leaves it, and the output says how to run it later. In a script, where nobody can answer, it is not run.

Nothing in a library's `installer.yml` can skip the question. Only you can: `--run make-key` runs that step without asking, `--no-run make-key` leaves it, and `--yes` runs every step and takes the offered answer to every other question, for a script or a build server.

A step that makes a file can name it, and when that file is already in your project the step is skipped without a question, so a second install never makes a second key. A step that names no file and ran before is not asked about again either, until the library changes what it runs. When a step fails, what was installed stays installed, and the installer ends with exit code 1, so a script notices.

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

When a new version keeps its files somewhere else, say in `src/`, the update moves your project along with it. Your `example_config.h` goes where the new version looks for it, with your settings between its `USER CODE` lines still in it, rather than a fresh default turning up next to the header. Files the old version installed and the new one no longer has are removed, so an old `example.c` cannot end up compiled beside the new one. Anything you put in the library's folder yourself is left alone.

### Uninstalling a library

```bash
lib-installer --uninstall example
```

From your project's folder, or with `--project`. The platform comes from your project's record, so the name is all it takes. It takes the library out of the build first, every block it wrote into your project's files and every place it was registered, and then its files go:

```
Files
  removed example/example.h
  removed example/example.c
  saved   example/example_config.h.20261014-163211.bak  it was yours to edit

Done. example is out of the project.
```

What was yours is saved before it goes, as a `.bak` beside it: a configuration file the library created, and any file of the library you wrote in between its `USER CODE` lines or changed by hand. A file you put in the library's folder yourself is left where it is, and the folder with it, and so are the [files that became yours](#files-that-become-yours).

A library another one needs stays, and the installer says which needs it:

```
Error: spif needs osal, so it stays. Uninstall spif first, or name them all on one line.
```

Name them all, in any order, and each goes after what needs it: `lib-installer --uninstall osal spif`. When the library you took out brought another with it that nothing left in the project needs, the last line names it, with the command that takes it out too.

Uninstall works from `.lib-installer.json`, the record of what was installed and where. For each library it also keeps where it came from, down to the commit, the blocks written into your files, and the steps that ran. A library put in by hand, or a record that was deleted, leaves it nothing to go on.

### A library that needs another

Some libraries build on another one, such as `osal` for the RTOS. You install only the one you want, and what it needs goes in first:

```
example 2.0.0 needs osal >= 1.0.0, which is not in this project. Installing osal first.
...
Done. #include "osal.h" and you are away.
...
Done. #include "example.h" and you are away.
```

Install a second library that needs `osal`, and the one already in your project is used:

```
spif 3.0.0 needs osal >= 1.0.0. osal 1.0.0 is already in this project, kept.
```

A library that goes in this way comes from the release the library needing it names, or else from its default branch. If a library needs a newer `osal` than the one you have, it is updated where it is, and your setting in `osal_config.h`, between its `USER CODE` lines, is kept as always. Everything is fetched before anything is installed, so when a library cannot be had, your project is left as it was.

---

## Moving over from the five installers

stm32-installer, zephyr-installer, esp32-installer, arduino-installer and pio-installer stopped at 2.1.0. lib-installer 3.0.0 does what each of them did, with one command:

```bash
pip uninstall stm32-installer
pip install lib-installer
```

**A project one of them installed into moves over by itself**, the first time lib-installer installs into it or uninstalls from it. Its record, such as `.zephyr-installer.json`, becomes `.lib-installer.json`, with the platform in it, and the lines that mark the installer's blocks in your files, such as `# >>> zephyr-installer: example >>>`, name lib-installer from then on. Nothing between those lines changes, so an update finds every block where it was and writes no second one. Each file is saved first, as a `.bak`, and keeps its line endings. The run says what moved:

```
Moved over from zephyr-installer to lib-installer: CMakeLists.txt, prj.conf, .lib-installer.json. Each was saved first as a .bak.
```

**A library written for one of them installs as it did.** lib-installer reads `requires.stm32_installer`, `requires.zephyr_installer` and the others, and every meaning a manifest from before 3.0.0 has. Such a manifest names no platform, so an install of it says which with `--platform`, and in a project whose record knows the platform, the error says which one to give. An uninstall takes it from the record.

**The commands are the same**, with `lib-installer` in front: `zephyr-installer owner/example --conf boards/x.conf` is `lib-installer owner/example --conf boards/x.conf`.

---

## For someone writing a library

Put an `installer.yml` at the root of the repository. Any library can have one, whoever wrote it, and the one file serves every platform: each reads its own section and leaves the others' alone. Releases before 1.9.0 called it `library.yml`, and the installer still reads that name when there is no `installer.yml`.

The keys every platform reads are below, as a manifest asking for 4.0.0 writes them. Only `name`, `platform` and its `headers` or `sources` are required; leave out what your library does not need. The keys of one platform, such as `zephyr:` or `requires.hal_modules`, are on that platform's page, with what it does with the rest: [STM32](https://github.com/nimaltd/lib-installer/blob/main/docs/stm32.md#for-someone-writing-a-library), [Zephyr](https://github.com/nimaltd/lib-installer/blob/main/docs/zephyr.md#for-someone-writing-a-library), [ESP-IDF](https://github.com/nimaltd/lib-installer/blob/main/docs/esp32.md#for-someone-writing-a-library), [Arduino](https://github.com/nimaltd/lib-installer/blob/main/docs/arduino.md#for-someone-writing-a-library) and [PlatformIO](https://github.com/nimaltd/lib-installer/blob/main/docs/pio.md#for-someone-writing-a-library).

```yaml
name: example                      # the library's name, and its folder in the project
description: Driver for the X chip # one line, shown while installing
repository: https://github.com/owner/example  # where it comes from
license: Apache-2.0                # the licence's SPDX name
platform: [stm32, zephyr]          # the platforms it works on: one name, or a list of
                                   # stm32, zephyr, esp32, arduino and pio
version: 1.0.0                     # only when the first header has no @version tag

requires:
  lib_installer: 4.0.0             # the oldest lib-installer that reads this file
  libraries:                       # other libraries, installed first when missing
    - osal >= 1.0.0                # no owner means nimaltd; >= the oldest that will do
    - owner/lib@v1.2.0             # a tag, branch or commit, not its default branch

install:
  defines:                         # given to the whole build, NAME or NAME=value
    - EXAMPLE_FAST

headers:                           # .h files; the first is the one to #include
  - src/example.h                  # every file keeps its path: example/src/example.h
  - src/example_config.h           # settings in USER CODE sections, kept on update
sources:                           # .c files, added to the build
  - src/example.c

options:                           # parts the user chooses at install
  littlefs:                        # the name typed after --with
    description: LittleFS file system on the flash  # the question asked
    sources:
      - src/example_lfs.c

once:                              # the project's own files: made when missing,
  - VERSION                        # then the user's, never replaced or removed

run:                               # steps run once the files are in, each asked about first
  - label: make-key                # the name typed after --run
    script: tools/make_key.py      # Python, run with the installer's own Python
    unless: product.key            # skipped when this file is in the project already

extras:                            # copied as they are, never compiled
  - LICENSE.md                     # LICENSE.md and NOTICE are the default
  - NOTICE
  - root: tools                    # tools/ into the project's folder, as the library's own
```

`platform` says which projects the library is for, by the names `--platform` takes. A library for one platform installs with no question; one for several asks once, then the project's record remembers. A library is refused in a project of a platform it does not name, before anything is written, rather than going in and failing on a missing HAL. It is required in a manifest asking for 3.0.0, and a manifest from before, which has none, still installs, given `--platform`. A library for every platform can list all five.

`requires.lib_installer` is the oldest lib-installer that reads the file correctly. It is checked before anything else in the file is read, so when a manifest starts using something only a newer installer understands, raising this makes an older one stop with a message saying to update, rather than read the file wrongly without a word. Write it as three numbers, `3.0.0`: unquoted, YAML reads `1.10` as the decimal number `1.1`, and that is refused.

The keys of the five installers before 3.0.0, `requires.stm32_installer`, `requires.zephyr_installer`, `requires.esp32_installer`, `requires.arduino_installer`, `requires.pio_installer`, and `requires.installer` from before 2.0.0, are still read, so a manifest written for one of them installs as it did. The version a manifest asks for decides how it reads: what 2.0.0 brought, such as `once` files in the project's folder and `run`, needs 2.0.0 or newer, and what 2.1.0 brought, every path starting at the project's folder, needs 2.1.0 or newer. A manifest asking for 3.0.0 reads as one asking for 2.1.0 does, and names its `platform`. 4.0.0 gives the `zephyr` section a place for everything a Zephyr library writes, by where it goes: the library's switch is `zephyr.symbol`, what it writes into the application's own files, `prj.conf`, `sysbuild.conf` and `CMakeLists.txt`, is under `zephyr.project`, and what it writes into its own folder, its Kconfig, a Kconfig fragment read after `prj.conf` and its `CMakeLists.txt`, under `zephyr.library`. Each list can be given in groups under their titles, and a setting with a note, which the files written carry as comments. The `esp32` and `pio` sections get the same two parts: `esp32.project` for the project's `sdkconfig.defaults` and `CMakeLists.txt`, `esp32.library` for its component, `pio.project` for `platformio.ini` and `pio.library` for `library.json`, and `requires.kconfig` gives way to each platform's own `project.conf`. Arduino and STM32 keep their sections as they are: what they write lands in files that hold no comments, or in different files for each IDE. A manifest asking for 4.0.0 has the new places, and one asking for less keeps the old keys, as the [Zephyr](https://github.com/nimaltd/lib-installer/blob/main/docs/zephyr.md#titles-and-notes-from-400), [ESP-IDF](https://github.com/nimaltd/lib-installer/blob/main/docs/esp32.md#where-each-line-goes-from-400) and [PlatformIO](https://github.com/nimaltd/lib-installer/blob/main/docs/pio.md#where-everything-goes-from-400) pages say. A key given twice in one place is refused from 4.0.0, by every platform: YAML would keep only the last without a word.

Leave `version` out. The installer reads the version from the `@version` tag in the file comment of the first header listed, so it is written in the code and nowhere else:

```c
/**
 * @file        example.h
 * @version     2.0.0
 */
```

A step a library runs sees where things are in its environment: `INSTALLER_PROJECT`, the project's folder, `INSTALLER_LIBRARY`, the library's folder in it, `INSTALLER_NAME` and `INSTALLER_VERSION`, the library's, `INSTALLER`, `lib-installer`, and `INSTALLER_PLATFORM`, the platform the run is for, such as `zephyr`, so one script can serve every platform.

There is no installer script to copy into the repository: put the install line from the top of this page in your README, with your library's name in it.

### Examples

**The smallest one.** A library of one header and one source, for one platform, needs no more than this:

```yaml
name: example
platform: zephyr
requires:
  lib_installer: 4.0.0
headers:
  - src/example.h
sources:
  - src/example.c
```

**A driver that needs another library**, with a part the user chooses, a file that becomes the project's, and a step run once the files are in, here for an STM32 project:

```yaml
name: example
description: Driver for the X chip
platform: stm32
requires:
  lib_installer: 4.0.0
  libraries:
    - osal >= 1.0.0                # installed first, when the project has none that new
headers:
  - src/example.h
  - src/example_config.h           # the user's settings, between USER CODE lines
sources:
  - src/example.c
options:
  littlefs:                        # lib-installer owner/example --with littlefs
    description: LittleFS file system on the flash
    libraries:
      - littlefs >= 2.11.0
    sources:
      - src/example_lfs.c
once:
  - from: templates/example_port.c # made once, then the project's
    to: Core/Src/example_port.c
extras:
  - root: tools                    # tools/make_key.py, in the project's folder
run:
  - label: make-key                # lib-installer owner/example --run make-key
    description: Make the product's key, product.key
    script: tools/make_key.py
    unless: product.key            # skipped once the key is there
```

**A Zephyr library that says where each line goes**, the application's files under `project`, its own folder under `library`, each list in groups under their titles, and a setting with a note:

```yaml
name: example
platform: zephyr
requires:
  lib_installer: 4.0.0
headers:
  - src/example.h
sources:
  - src/example.c
zephyr:
  symbol:                          # CONFIG_EXAMPLE=y, last in its block in prj.conf,
    EXAMPLE: the driver, and its defaults while it is on  # with its note
  project:
    conf:                          # prj.conf, beside the switch, the user's to change
      What the release build leaves out:
        - LOG=n: no messages, and nowhere to send them
        - ASSERT=n
  library:
    kconfig:                       # defaults in its Kconfig, while CONFIG_EXAMPLE is on
      Bluetooth, as a peripheral:
        - BT
        - BT_PERIPHERAL
    conf:                          # its Kconfig fragment, read after prj.conf
      Bluetooth as fast as it goes:
        - BT_AUTO_PHY_PERIPHERAL_2M: the 2M PHY as soon as a phone connects
```

Its block in the application's `prj.conf` then reads:

```
# >>> lib-installer: example >>>
# Added by lib-installer, and written again on every install, so set
# example's settings below this block rather than in it.

# ******************************************************************************
# What the release build leaves out
# ******************************************************************************
# no messages, and nowhere to send them
CONFIG_LOG=n
CONFIG_ASSERT=n

# ******************************************************************************
# example
# ******************************************************************************
# the driver, and its defaults while it is on
CONFIG_EXAMPLE=y
# <<< lib-installer: example <<<
```

The [Zephyr page](https://github.com/nimaltd/lib-installer/blob/main/docs/zephyr.md#for-someone-writing-a-library) has every key of its section, and what each writes where.

**An ESP-IDF library that says where each line goes**, the project's files under `project`, its component under `library`, a list in groups under their titles, and a symbol with a note:

```yaml
name: example
platform: esp32
requires:
  lib_installer: 4.0.0
headers:
  - src/example.h
sources:
  - src/example.c
esp32:
  project:
    conf:                          # its block in the project's sdkconfig.defaults
      A faster tick:
        - FREERTOS_HZ=1000: one tick a millisecond
    cmake:                         # the project's CMakeLists.txt, by place
      after-project:
        - idf_component_get_property(main_lib main COMPONENT_LIB)
        - target_compile_definitions(${main_lib} PRIVATE EXAMPLE_IN_MAIN)
  library:
    requires: [esp_timer]          # REQUIRES of its component
    cmake:                         # its component's CMakeLists.txt
      Math:
        - target_link_libraries(${COMPONENT_LIB} PRIVATE m)
```

Its block in the project's `sdkconfig.defaults` then reads:

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

**A PlatformIO library with a flag for the whole build**, in `platformio.ini` under `project`, and what goes into its `library.json` under `library`:

```yaml
name: example
platform: pio
requires:
  lib_installer: 4.0.0
install:
  defines:
    - EXAMPLE_FAST
headers:
  - src/example.h
sources:
  - src/example.c
pio:
  project:
    build_flags:                   # platformio.ini, after its defines, for every file
      Printing:
        - -Wl,-u,_printf_float: printf("%f") prints nothing without it
  library:                         # its library.json, which has no comments
    frameworks: [arduino]
    dependencies:
      - bblanchon/ArduinoJson@^7
```

Its block in `build_flags` of `platformio.ini`, a title and a note as comments of the file's:

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

The [ESP-IDF](https://github.com/nimaltd/lib-installer/blob/main/docs/esp32.md#for-someone-writing-a-library) and [PlatformIO](https://github.com/nimaltd/lib-installer/blob/main/docs/pio.md#for-someone-writing-a-library) pages have every key of their sections.

---

## Running the tests

```bash
git clone https://github.com/nimaltd/lib-installer.git
python test/run_tests.py
```

Each folder of `test` is a run of its own: `core` for what every platform shares, `package` for the command as a whole, the platform choice and the move from the installers before 3.0.0, and one for each platform. CI also installs the example libraries of `test/<platform>/e2e` into real projects, and builds them with Zephyr, ESP-IDF, arduino-cli and PlatformIO.

---

## Support

I write these tools and libraries in my own time and give them away, because good tools should be easy to get. If this one saved you an afternoon, there are two things that genuinely help:

**Star the repo.** It costs you one click, it helps other engineers find the tool, and it is the main reason I keep going.

**[Buy me a coffee on Ko-fi](https://ko-fi.com/nimaltd).** Any amount is a real motivation to keep writing, documenting and maintaining this work.

[![GitHub](https://img.shields.io/badge/GitHub-Follow-black?style=for-the-badge&logo=github)](https://github.com/NimaLTD)
[![YouTube](https://img.shields.io/badge/YouTube-Subscribe-red?style=for-the-badge&logo=youtube)](https://youtube.com/@nimaltd)
[![Instagram](https://img.shields.io/badge/Instagram-Follow-purple?style=for-the-badge&logo=instagram)](https://instagram.com/github.nimaltd)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-blue?style=for-the-badge&logo=linkedin)](https://linkedin.com/in/nimaltd)
[![Email](https://img.shields.io/badge/Email-Contact-red?style=for-the-badge&logo=gmail)](mailto:nima.askari@gmail.com)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-Support-orange?style=for-the-badge&logo=ko-fi)](https://ko-fi.com/nimaltd)

---

## License

Apache License 2.0. See [LICENSE](https://github.com/nimaltd/lib-installer/blob/main/LICENSE).
