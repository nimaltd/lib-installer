"""
Getting a library ready to install: fetched from GitHub, or unpacked from
the zip GitHub offers for download.

Only the files the manifest actually lists are downloaded. GitHub can only hand
out a zip of an entire repository, so the zip is avoided: the manifest is read
first, then each listed file is fetched on its own. For a library whose repo
carries a vendored test framework, that is the difference between a few hundred
kilobytes and a few.

A private repository needs a GitHub token that can read it: given with --key,
or in GITHUB_TOKEN or GH_TOKEN. With one, every file comes from the API rather
than from raw.githubusercontent, which cannot see a private repository at all.
"""

import http.client
import json
import os
import re
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from . import manifest, target, yamlreader

RAW_URL = "https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"
CONTENTS_URL = "https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={ref}"
TREE_URL = "https://api.github.com/repos/{owner}/{repo}/git/trees/{ref}?recursive=1"
COMMIT_URL = "https://api.github.com/repos/{owner}/{repo}/commits/{ref}"
DEFAULT_OWNER = "nimaltd"

# What git calls the repository's default branch, whatever its name: main,
# master, develop, the one GitHub marks "default". raw.githubusercontent.com
# and the API both take it as a ref.
DEFAULT_REF = "HEAD"
TIMEOUT_SECONDS = 30

# Asking which commit a ref is now is worth a few seconds, not thirty: without
# the answer the files still come from the same ref, only not pinned to it.
RESOLVE_TIMEOUT_SECONDS = 10

# A full commit SHA, which is what the API answers with.
_SHA = re.compile(r"^[0-9a-f]{40}$")

# What each fetch of this run fetched, by the folder it fetched into: owner/name,
# the ref asked for, and the commit that was. Kept here rather than in a file
# beside the manifest, where a wildcard under extras could sweep it up.
_ORIGINS = {}


def _key(root):
    """A folder as the key of _ORIGINS, the same however it is spelt."""
    return str(Path(root).resolve())


def origin(root):
    """Where the library fetched into root came from, or {} when it was not fetched."""
    return dict(_ORIGINS.get(_key(root), {}))


# What this run asked GitHub already, the commit a ref was and a manifest's
# bytes, while remember() is on. lib-installer reads a library's manifest
# first, for the platform it names, and the fetch that follows then asks
# nothing twice. Off, the default, every call asks.
_RUN = None


def remember():
    """Keep what GitHub answers until forget(): one run's worth."""
    global _RUN
    _RUN = {}


def forget():
    """Stop keeping what GitHub answers, and drop what was kept."""
    global _RUN
    _RUN = None


# Tries in all for one file, when the connection drops, resets, times out or
# is cut off part way, or GitHub answers 5xx. 1, 2, 4 and 8 seconds between
# them, so a link that is down for a few seconds, or throttled, gets through.
# Without a token they take turns between raw.githubusercontent.com and
# api.github.com, two hosts on different addresses, so one that is filtered
# or failing does not decide alone. Tested from a user's machine where GitHub
# kept closing the connection part way through an install.
ATTEMPTS = 5

# Where a token is looked for, after --key, in this order. GitHub Actions sets
# the first and the gh command reads the second, so a machine set up for either
# works as it is.
TOKEN_VARIABLES = ("GITHUB_TOKEN", "GH_TOKEN")

# Where the user makes and edits a fine-grained token, named in every message
# about one that cannot read.
TOKENS_PAGE = "https://github.com/settings/personal-access-tokens"

# The token given with --key for this run, which comes before the environment.
_given = None

# The file as it is, not wrapped in JSON and base64 the way the API hands a file
# out by default.
RAW_MEDIA = "application/vnd.github.raw"




def _offline_hint():
    """What to do when GitHub cannot be reached, said once wherever that happens."""
    return (
        "Run it again, as a bad connection often passes. Behind a proxy or a VPN, set HTTPS_PROXY "
        "to it, or use the system proxy on Windows. Or download each library with Code, Download "
        "ZIP, from wherever GitHub opens, and give the zips on the command line: "
        f"{target.current.command} spif-main.zip osal-main.zip"
    )


class DownloadError(Exception):
    """A library could not be fetched, with a reason worth showing the user."""


class NotFoundError(DownloadError):
    """GitHub answered 404: no such file, branch or repository, or a private one."""


class _SameHostRedirect(urllib.request.HTTPRedirectHandler):
    """
    Follow a redirect, but take the token only as far as the host it was for.

    urllib copies every header over to wherever a redirect points, the
    Authorization header included, and GitHub does redirect, for a renamed
    repository to start with. A token must not travel anywhere but back to the
    host it was sent to.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)

        if new is not None:
            before = urllib.parse.urlsplit(req.full_url).hostname
            after = urllib.parse.urlsplit(newurl).hostname

            if before != after:
                new.remove_header("Authorization")

        return new


_OPENER = urllib.request.build_opener(_SameHostRedirect)


def use_token(token):
    """Use this token for the rest of the run, before any in the environment. None for none."""
    global _given
    _given = token.strip() if token and token.strip() else None


def _token():
    """(where, token) for the token to use, from --key or the environment, or (None, None)."""
    if _given:
        return "--key", _given

    for name in TOKEN_VARIABLES:
        value = os.environ.get(name, "").strip()

        if value:
            return name, value

    return None, None


def _open(url, token=None, accept=None, timeout=TIMEOUT_SECONDS):
    """Open a URL, sending the token when there is one."""
    request = urllib.request.Request(url)

    if token:
        request.add_header("Authorization", f"Bearer {token}")

    if accept:
        request.add_header("Accept", accept)

    return _OPENER.open(request, timeout=timeout)


def resolve(owner, repo, ref=None):
    """
    The commit a ref names now, as a full SHA, or None when the API cannot say.

    Every file is then fetched from that commit, so a push that lands half way
    through a download cannot mix two versions, and the record says exactly
    what was installed. Without an answer, from a limit on requests or a
    filtered host, the files still come from the ref itself, as they always did.
    """
    key = ("resolve", owner, repo, ref)

    if _RUN is not None and key in _RUN:
        return _RUN[key]

    url = COMMIT_URL.format(owner=owner, repo=repo, ref=urllib.parse.quote(ref or DEFAULT_REF, safe=""))

    try:
        with _open(url, _token()[1], "application/vnd.github.sha", RESOLVE_TIMEOUT_SECONDS) as response:
            sha = response.read().decode("ascii", "replace").strip()
    except (urllib.error.URLError, OSError, http.client.HTTPException, ValueError):
        sha = ""

    found = sha if _SHA.match(sha) else None

    if _RUN is not None:
        _RUN[key] = found

    return found


def _fetch(owner, repo, ref, path):
    """Fetch one file's bytes. Raises DownloadError with a readable message."""
    variable, token = _token()
    api = CONTENTS_URL.format(
        owner=owner, repo=repo, path=urllib.parse.quote(path), ref=urllib.parse.quote(ref, safe="")
    )

    # A private repository is only reachable through the API, with the token.
    urls = [api] if token else [RAW_URL.format(owner=owner, repo=repo, ref=ref, path=path), api]

    for attempt in range(1, ATTEMPTS + 1):
        url = urls[(attempt - 1) % len(urls)]

        try:
            return _get(url, token, RAW_MEDIA if url == api else None)
        except (urllib.error.URLError, OSError, http.client.HTTPException) as error:
            if not _passing(error, token) or attempt == ATTEMPTS:
                _report(error, owner, repo, ref, path, variable, token)

            time.sleep(2 ** (attempt - 1))


def _passing(error, token):
    """
    Whether trying again could get a different answer.

    A dropped connection, a timeout or a 5xx could. A 404 is GitHub's answer
    and the same every time, which the manifest's own fallback relies on, and
    so is a 401 or a 403 to a token. Without a token, a 403 or a 429 is the API's
    limit on requests, and the other host may still answer.
    """
    if not isinstance(error, urllib.error.HTTPError):
        return True

    return error.code >= 500 or (not token and error.code in (403, 429))


def _get(url, token, accept):
    """One request for one file, its bytes read to the end."""
    with _open(url, token, accept) as response:
        return response.read()


def _named(where):
    """The token, as a message names it: the one given with --key, or the one in a variable."""
    return "the token given with --key" if where == "--key" else f"the token in {where}"


def _wants(error):
    """The permissions GitHub said the request needs, such as contents=read, or ""."""
    headers = getattr(error, "headers", None)

    return (headers.get("X-Accepted-GitHub-Permissions", "") if headers is not None else "") or ""


def _report(error, owner, repo, ref, path, variable, token):
    """Raise the DownloadError that says, in words, what went wrong with one file."""
    if isinstance(error, urllib.error.HTTPError):
        if error.code == 401 and token:
            raise DownloadError(
                f"GitHub did not accept {_named(variable)}. It may have expired, been revoked, "
                f"or been copied with a character missing. Make a new one at {TOKENS_PAGE}."
            ) from error

        # The usual mistake with a fine-grained token: the repository is chosen,
        # so the token can see it, but its files need a permission of their own,
        # and GitHub says which in a header.
        if error.code == 403 and token and "contents=read" in _wants(error):
            raise DownloadError(
                f"{_named(variable)[0].upper()}{_named(variable)[1:]} can see {owner}/{repo}, but cannot "
                f"read its files: GitHub wants the Contents permission, and the token has only Metadata.\n"
                f"Edit the token, and its value stays the same, so nothing else changes:\n"
                f"  1. Open {TOKENS_PAGE} and click the token's name.\n"
                f"  2. Click Edit.\n"
                f"  3. In Permissions, set Contents to Read-only. In the older layout that is under\n"
                f"     Repository permissions; in the newer one, click + Add permissions and tick Contents.\n"
                f"  4. Click Update at the bottom of the page.\n"
                f"Then run this again as it was."
            ) from error

        if error.code == 403:
            raise DownloadError(
                f"GitHub refused access to {owner}/{repo} (HTTP 403)"
                + (
                    f" with {_named(variable)}. It may not be allowed to read this repository: "
                    f"check its Repository access and its Contents permission at {TOKENS_PAGE}."
                    if token else
                    ". That is usually its limit on requests without a token: wait, or give one with --key."
                )
            ) from error

        if error.code == 404:
            # GitHub answers a private repository it will not show you with 404,
            # the same as one that does not exist. Only the manifest is asked for
            # first, so that is where a missing token shows up.
            hint = _private_hint(variable, token) if path in manifest.MANIFEST_NAMES else ""

            raise NotFoundError(f"{path} does not exist in {owner}/{repo} at {ref}.{hint}") from error

        raise DownloadError(f"Could not download {path} from {owner}/{repo}: HTTP {error.code}.") from error

    # Not reached, or the connection dropped, reset, timed out or was cut short.
    # urllib leaves the last ones as they are, not wrapped in a URLError, so
    # before they were caught here they ended the run with a traceback.
    reason = error.reason if isinstance(error, urllib.error.URLError) else (error or type(error).__name__)

    raise DownloadError(
        f"Could not fetch {path} from {owner}/{repo}, after {ATTEMPTS} tries: {reason}.\n"
        f"{_offline_hint()}"
    ) from error


def _code_of(data):
    """
    The headers and the sources of a manifest or an option: under files, or
    from 2.1.0 on their own. Both are read here; which is allowed is the
    manifest's to say, once it is on disk.
    """
    files = data.get("files") if isinstance(data.get("files"), dict) else {}
    found = []

    for part in (files, data):
        for key in ("headers", "sources"):
            value = part.get(key)
            found += list(value) if isinstance(value, list) else []

    return found


def _listed_entries(data):
    """
    Every repository path or pattern a parsed manifest refers to.

    A files entry is either a plain path, a folder, a wildcard, or a
    {from, to} pair, and only the "from" side names something to download.
    """
    listed = _code_of(data)

    # Every option's files, chosen or not. Which are taken is asked once the
    # library is on disk, and the answer must not need a second download.
    options = data.get("options")

    for option in (options.values() if isinstance(options, dict) else []):
        if isinstance(option, dict):
            listed += _code_of(option)

    listed += data.get("once") or []
    listed += data.get("extras") or ["LICENSE.md", "NOTICE"]

    # The scripts the run steps start, and the installer.yml carried for a
    # library that has none, the library's own options' included. From 2.1.0 a
    # script names a place in the project, which an extra or a once file above
    # fills, so it is no file of the repository's to fetch.
    rooted = manifest.asks_for(data, manifest.ROOTED)

    for step in data.get("run") or []:
        if isinstance(step, dict) and step.get("script") and not rooted:
            listed.append(str(step["script"]))

    requires = data.get("requires") if isinstance(data.get("requires"), dict) else {}
    needed = list(requires.get("libraries") or [])

    for option in (options.values() if isinstance(options, dict) else []):
        if isinstance(option, dict):
            needed += list(option.get("libraries") or [])

    for dependency in needed:
        if isinstance(dependency, dict) and dependency.get("manifest"):
            listed.append(str(dependency["manifest"]))

    # A {from, to} pair names the file by its from, or from 2.1.0 by its to or
    # its root alone, when the library's path is the same.
    entries = []
    for item in listed:
        if isinstance(item, dict):
            source = item.get("from") or item.get("to") or item.get("root")

            if source:
                entries.append(str(source))
        else:
            entries.append(str(item))

    return entries


def _private_hint(variable, token):
    """What to say when a manifest is not found, in case the repository is private."""
    if token:
        return (
            f" If the repository is private, {_named(variable)} cannot see it: add it under the "
            f"token's Repository access at {TOKENS_PAGE}."
        )

    return " If the repository is private, give a token that can read it with --key, or in GITHUB_TOKEN."


def _manifest(owner, repo, ref, asked=None):
    """
    The bytes of the manifest, and its name.

    installer.yml is asked for first, then library.yml, its name before 1.9.0,
    which a release tagged before the rename still has. Only a 404 moves on. Any
    other failure, a refused token or no network, would fail the same way on the
    next try, and would then be reported as the wrong problem.

    asked is the ref as the user gave it, for the message: None for the
    default branch, which ref is then the commit of.
    """
    key = ("manifest", owner, repo, ref)

    if _RUN is not None and key in _RUN:
        return _RUN[key]

    for name in manifest.MANIFEST_NAMES:
        try:
            found = _fetch(owner, repo, ref, name), name
        except NotFoundError:
            continue

        if _RUN is not None:
            _RUN[key] = found

        return found

    where = f"at {asked}" if asked is not None else "on its default branch"

    raise NotFoundError(
        f"{manifest.MANIFEST_NAME} does not exist in {owner}/{repo} {where}.{_private_hint(*_token())}"
    )


def tree(owner, repo, ref):
    """
    Every file path in the repository, from the GitHub API.

    Needed because a folder or a wildcard cannot be resolved against
    raw.githubusercontent, which only serves one named file at a time. Returns
    None when the listing is unavailable, so the caller can fall back to
    treating each entry as a literal path.
    """
    url = TREE_URL.format(owner=owner, repo=repo, ref=urllib.parse.quote(ref, safe=""))

    try:
        with _open(url, _token()[1], "application/vnd.github+json") as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, http.client.HTTPException, ValueError):
        return None

    if data.get("truncated"):
        # Enormous repository. Literal paths still work, patterns would quietly
        # miss files, so it is better to admit to knowing nothing.
        return None

    return [item["path"] for item in data.get("tree", []) if item.get("type") == "blob"]


def peek(source, ref=None):
    """
    The bytes of a library's manifest on GitHub, and nothing else of it: what
    a run reads first, for the platform the library names. Asked the way
    _fill() asks, so with remember() on the fetch that follows reuses both
    answers. Raises DownloadError as fetch() would.
    """
    owner, repo, named = _split_ref(source)

    if named is not None and ref is not None and named != ref:
        raise DownloadError(f"{source} names {named}, and --ref gives {ref}. Give the ref once.")

    ref = named if named is not None else ref
    commit = resolve(owner, repo, ref)

    return _manifest(owner, repo, commit or (ref if ref is not None else DEFAULT_REF), ref)[0]


def fetch(source, ref=None, destination=None, carried=None):
    """
    Download a library's manifest and the files it lists into a folder.

    The result mirrors the repository's own layout, so manifest.load() and
    install_to() work on it exactly as they do on a local clone. Beside the
    manifest, ORIGIN_NAME says where it came from: see origin().

    Args:
        source: library name, "owner/name", or a GitHub URL, with "@ref" after
            it for a tag, a branch or a commit.
        ref: branch, tag or commit, when the source names none. None is the
            repository's default branch, whatever its name.
        destination: where to write. A temporary folder when not given.
        carried: the bytes of an installer.yml for a repository that has none,
            which the library needing it carries. Used in place of the one the
            repository would hold.

    Returns:
        The Path the files were written to. The caller owns it and, when it is
        temporary, is responsible for removing it.
    """
    owner, repo, named = _split_ref(source)

    if named is not None and ref is not None and named != ref:
        raise DownloadError(f"{source} names {named}, and --ref gives {ref}. Give the ref once.")

    ref = named if named is not None else ref
    temporary = destination is None
    root = Path(destination) if destination else Path(tempfile.mkdtemp(prefix="installer-"))
    root.mkdir(parents=True, exist_ok=True)

    try:
        _fill(owner, repo, ref, root, carried)
    except DownloadError:
        # Half a library is of no use, and nobody else knows this folder
        # exists, since it was never returned. A folder the caller passed in
        # is theirs, and is left alone.
        if temporary:
            cleanup(root)
        raise

    return root


def _fill(owner, repo, ref, root, carried=None):
    """Download the manifest, then every file it lists, into root."""
    asked = ref
    commit = resolve(owner, repo, ref)

    # Every file then comes from the one commit the ref was when this began,
    # or, when nobody could say which that was, from the ref itself.
    ref = commit or (ref if ref is not None else DEFAULT_REF)

    if carried is not None:
        raw, name = carried, manifest.MANIFEST_NAME
    else:
        raw, name = _manifest(owner, repo, ref, asked)

    (root / name).write_bytes(raw)
    _ORIGINS[_key(root)] = {
        "kind": "github",
        "source": f"{owner}/{repo}",
        "ref": asked,
        "commit": commit,
        "manifest": "carried" if carried is not None else None,
    }

    try:
        data = yamlreader.parse(raw.decode("utf-8"))
    except (yamlreader.YamlError, UnicodeDecodeError) as error:
        raise DownloadError(f"{owner}/{repo} has a {name} that cannot be read: {error}")

    if not isinstance(data, dict):
        raise DownloadError(f"{owner}/{repo} has a {name} that is not a mapping.")

    # Before a single listed file is fetched. A manifest for a newer installer
    # may list its files in a way this one would get wrong.
    try:
        manifest.check_installer(data)
    except manifest.ManifestError as error:
        raise DownloadError(str(error)) from error

    entries = _listed_entries(data)

    # The extras the manifest names, or the two every library may carry when it
    # names none. All are optional: a repository may lack any of them. One
    # written as a mapping is named by its from, or its to or root alone.
    named = {str((item.get("from") or item.get("to") or item.get("root")) if isinstance(item, dict) else item)
             for item in (data.get("extras") or [])}
    optional = named or {"LICENSE.md", "NOTICE"}

    # Before a single one is fetched: each is written under root by its own
    # path, so one that climbs out with .. would land outside it.
    for entry in entries:
        reason = manifest.unsafe_path(entry)

        if reason:
            raise DownloadError(
                f"{owner}/{repo} lists {entry!r} in its {name}, a file outside the library, which is "
                f"never fetched: {reason}. Nothing was changed."
            )

    # One listing of the repository, and only when something actually needs it:
    # a wildcard, now, or a plain path that turns out to be a folder, below.
    known = tree(owner, repo, ref) if any(manifest.is_pattern(e) for e in entries) else None
    listed = known is not None

    wanted = []
    for entry in entries:
        if known is None:
            wanted.append((entry, entry))
            continue

        for path in manifest.expand(None, entry, known):
            wanted.append((path.as_posix(), entry))

    for path, entry in wanted:
        try:
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(_fetch(owner, repo, ref, path))
        except DownloadError:
            if entry in optional and not named:
                # LICENSE.md or NOTICE, which most libraries do not have. No
                # folder, and not worth a call to the API, which allows 60 an
                # hour without a token.
                continue

            # A plain path that is not a file may be a folder, which only the
            # repository listing can resolve. An extra may be one too, such as
            # doc, so it is looked for there before it is passed over. The
            # listing is asked for once, however many entries need it.
            if not listed:
                known = tree(owner, repo, ref)
                listed = True

            found = manifest.expand(None, entry, known) if known else []

            if not found:
                if entry in optional:
                    # Optional by nature, so a repository missing one is fine.
                    continue

                raise

            for extra in found:
                target = root / extra
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(_fetch(owner, repo, ref, extra.as_posix()))


def _split_ref(source):
    """
    Owner, repository name and ref from a source: "owner/name@v1.2.0", "name",
    or a GitHub URL, a /tree/<ref> one included. The ref is None when none is
    named, which means the repository's default branch.
    """
    text = str(source).strip()
    ref = None

    if text.startswith(("http://", "https://")):
        parts = text.rstrip("/").split("/")

        # https://github.com/owner/repo/tree/v1.2.0, as a browser shows a tag.
        if len(parts) > 6 and parts[5] == "tree":
            ref = "/".join(parts[6:])
            text = "/".join(parts[:5])
    elif "@" in text:
        text, _, ref = text.partition("@")

        if not ref or ".." in ref or ref.startswith("-"):
            raise DownloadError(f"{source!r} names no usable tag, branch or commit after the @.")

    owner, repo = _split(text)

    return owner, repo, ref


def _split(source):
    """Owner and repository name from a bare name, an owner/name pair, or a URL."""
    text = str(source).strip().rstrip("/")

    if text.endswith(".git"):
        text = text[: -len(".git")]

    if text.startswith(("http://", "https://")):
        parts = [p for p in text.split("/") if p and p != "https:" and p != "http:"]
        if len(parts) < 3:
            raise DownloadError(f"{source} does not look like a GitHub repository URL.")
        return parts[1], parts[2]

    if "/" in text:
        owner, _, repo = text.partition("/")
        if owner and repo:
            return owner, repo
        raise DownloadError(f"Could not work out the repository from {source!r}.")

    if not text:
        raise DownloadError("No library name given.")

    return DEFAULT_OWNER, text


def find_root(folder):
    """
    The folder holding installer.yml: the one given, or the only one inside it.

    GitHub's zip holds a single top folder, example-main, and Windows' Extract
    All puts that inside another folder of the same name. Either is what a user
    will point at, so both have to work. None when neither holds a manifest, or
    when several subfolders do and picking one would be a guess.
    """
    folder = Path(folder)

    if manifest.manifest_path(folder) is not None:
        return folder

    try:
        found = [
            child
            for child in sorted(folder.iterdir())
            if child.is_dir() and manifest.manifest_path(child) is not None
        ]
    except OSError:
        return None

    return found[0] if len(found) == 1 else None


def peek_zip(archive):
    """
    The bytes of the manifest in a library zip, read without unpacking it, or
    None when it holds none: at its top, or in its one top folder, as GitHub's
    zip has it, the way find_root() finds it once unpacked.
    """
    try:
        with zipfile.ZipFile(archive) as bundle:
            names = set(bundle.namelist())
            tops = sorted({name.split("/", 1)[0] for name in names if "/" in name})
            found = [prefix for prefix in [""] + [top + "/" for top in tops]
                     if any(prefix + name in names for name in manifest.MANIFEST_NAMES)]

            if not found or (found[0] != "" and len(found) > 1):
                return None

            for name in manifest.MANIFEST_NAMES:
                if found[0] + name in names:
                    return bundle.read(found[0] + name)
    except (zipfile.BadZipFile, OSError, KeyError):
        return None

    return None


def unpack(archive):
    """
    Unpack a library zip into a temporary folder.

    Returns (staging, root): the folder to hand to cleanup() when done, and the
    library inside it. Raises DownloadError when the file is not a zip or holds
    no library, and leaves nothing behind either way.
    """
    staging = Path(tempfile.mkdtemp(prefix="installer-"))

    try:
        with zipfile.ZipFile(archive) as bundle:
            # extractall will not write outside the folder it is given: it
            # drops absolute paths and ".." from the names inside the zip.
            bundle.extractall(staging)
    except (zipfile.BadZipFile, OSError) as error:
        cleanup(staging)
        raise DownloadError(f"{Path(archive).name} is not a usable zip: {error}")

    root = find_root(staging)

    if root is None:
        cleanup(staging)
        raise DownloadError(
            f"{Path(archive).name} holds no installer.yml, so there is no library in it to install."
        )

    return staging, root


def cleanup(path):
    """Remove a folder created by fetch() or unpack(). Never raises."""
    shutil.rmtree(path, ignore_errors=True)
