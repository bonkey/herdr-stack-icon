#!/usr/bin/env python3
# Detect the technology stack of a herdr workspace's repository and report it as
# the `stack` sidebar token on the workspace (Space rows) and on each of its
# panes (Agent rows), every pane from its own folder. The workspace follows the
# focused pane. Display only: nothing is renamed.
#
#   python3 stack-icon.py                  run from a herdr event or action (reads HERDR_* env)
#   python3 stack-icon.py --detect <path>  print the icon for a path and exit; no herdr calls
#   python3 stack-icon.py --explain <path> show root, markers found and the resulting icon
#   python3 stack-icon.py --all            report every workspace, then exit
#   python3 stack-icon.py --watch          report every workspace, then follow pane.updated on
#                                          the herdr socket; started by herdr as the [[startup]]
#                                          hook, or by hand during dev
#
# The token lives only in the running server, so --watch reports every workspace
# before it subscribes, and again whenever the socket closes: otherwise a Space
# row stays empty until its workspace is focused.
#
# herdr emits pane.updated on every cd in a pane, but does not dispatch it to
# plugin event hooks, so --watch subscribes on the socket instead. Only the
# event's pane is checked, and nothing is reported when its token already
# matches: report-metadata itself emits pane.updated, so an unconditional
# report would loop.
#
# Markers are searched down to depth 3 from the workspace folder, then from the
# repository root. A marker in the folder itself decides alone; markers further
# down decide only when the folder holds none, and package.json then needs a
# lock file next to it. Within the deciding tier the first match wins:
#                                                     nerd             emoji
#   overrides.toml entry                              as configured (see override below)
#   iOS/macOS and Android both present, at any depth  apple + android  🍏🤖
#   *.xcodeproj *.xcworkspace Package.swift Podfile   apple            🍏
#   settings.gradle[.kts] build.gradle[.kts]          android          🤖
#   Cargo.toml                                        rust             🦀
#   go.mod                                            go               🐹
#   package.json                                      nodejs_small     🟩
#   pyproject.toml requirements.txt                   python           🐍
#   nothing matched: the token is cleared, never a placeholder.
#
# The nerd column is the default. It names a Devicons glyph, so `apple` is
# nf-dev-apple; NERD below holds the codepoints. `icons = "emoji"` in
# config.toml in the plugin config dir picks the emoji column instead.

import fnmatch
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time

SOURCE = "bonkey.stack-icon"
HERDR_TIMEOUT = 10
WATCH_LOG_LIMIT = 1000000

SUBSCRIBE = (
    '{"id":"stack-icon","method":"events.subscribe",'
    '"params":{"subscriptions":[{"type":"pane.updated"}]}}\n'
)

# Dependency and build folders, next to every dot-directory, are not descended.
PRUNED_DIRS = frozenset(
    ("node_modules", "Pods", "DerivedData", "Carthage", "vendor", "target", "build", "dist")
)

MARKER_NAMES = {
    "Package.swift": "ios",
    "Podfile": "ios",
    "settings.gradle": "android",
    "settings.gradle.kts": "android",
    "build.gradle": "android",
    "build.gradle.kts": "android",
    "Cargo.toml": "rust",
    "go.mod": "go",
    "package.json": "node",
    "pyproject.toml": "py",
    "requirements.txt": "py",
}
MARKER_SUFFIXES = (".xcodeproj", ".xcworkspace")

# The order the deciding tier is searched in.
KINDS = ("ios", "android", "rust", "go", "node", "py")

# Every glyph is a Devicon in the U+E700-U+E7C5 block, which Nerd Fonts v3 kept
# where v2 had it, so the set renders the same in both. A terminal without a
# Nerd Font shows a replacement box for each one.
NERD = {
    "ios": "\ue711",  # nf-dev-apple
    "android": "\ue70e",  # nf-dev-android
    "rust": "\ue7a8",  # nf-dev-rust
    "go": "\ue724",  # nf-dev-go
    "node": "\ue718",  # nf-dev-nodejs_small
    "py": "\ue73c",  # nf-dev-python
}

EMOJI = {
    "ios": "🍏",
    "android": "🤖",
    "rust": "🦀",
    "go": "🐹",
    "node": "🟩",
    "py": "🐍",
}

ICON_SETS = {"nerd": NERD, "emoji": EMOJI}
DEFAULT_ICON_SET = "nerd"

LOCK_FILES = (
    "package-lock.json",
    "npm-shrinkwrap.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lockb",
    "bun.lock",
)

# One `key = "icon"` per line, with an optional trailing comment.
OVERRIDE_LINE = re.compile(
    r'^[ \t\r\f\v]*("[^"]+"|[A-Za-z0-9_.~/*?-]+)[ \t\r\f\v]*=[ \t\r\f\v]*"[^"]*"[ \t\r\f\v]*(#.*)?$'
)

# A `name = "value"` setting in config.toml, with an optional trailing comment.
SETTING_LINE = re.compile(
    r'^[ \t\r\f\v]*([A-Za-z0-9_-]+)[ \t\r\f\v]*=[ \t\r\f\v]*"([^"]*)"[ \t\r\f\v]*(#.*)?$'
)

BLANK = " \t\r\f\v"

_STAMP = False
_MISSING = object()
_CONFIG_DIR = None


def log(message):
    if _STAMP:
        line = "%s stack-icon: %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), message)
    else:
        line = "stack-icon: %s" % message
    print(line, file=sys.stderr, flush=True)


def env(name, default=""):
    """Like ${NAME:-default}: an empty value falls back too."""
    return os.environ.get(name) or default


def herdr_bin():
    return env("HERDR_BIN_PATH", "herdr")


def state_dir():
    return env("HERDR_PLUGIN_STATE_DIR", os.path.join(env("TMPDIR", "/tmp"), "stack-icon"))


def socket_path():
    return env("HERDR_SOCKET_PATH", os.path.join(env("HOME"), ".config/herdr/herdr.sock"))


def basename(path):
    """basename(1): a trailing slash is not a component."""
    stripped = path.rstrip("/")
    if not stripped:
        return "/" if path else ""
    return stripped.rsplit("/", 1)[-1]


# --------------------------------------------------------------------------
# Running herdr and git
# --------------------------------------------------------------------------


def run_herdr(args, capture=True):
    """Return (ok, stdout). `ok` is False when herdr failed, timed out or is missing."""
    try:
        done = subprocess.run(
            [herdr_bin()] + args,
            stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=HERDR_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return False, ""
    out = done.stdout.decode("utf-8", "replace") if capture and done.stdout else ""
    return done.returncode == 0, out


def git_output(cwd, args):
    """stdout of a git command in `cwd`, empty when it cannot run."""
    if not cwd or not os.path.isdir(cwd):
        return ""
    try:
        done = subprocess.run(
            ["git", "-C", cwd] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=HERDR_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.decode("utf-8", "replace").rstrip("\n")


def repo_root(path):
    """Repository root for a directory; works inside linked worktrees. Falls back
    to the directory itself when it is not a git checkout."""
    return git_output(path, ["rev-parse", "--show-toplevel"]) or path


def repo_name(path):
    """Name of the repository a checkout belongs to: the main checkout's directory,
    also for linked worktrees (so "les-gardiens" for les-gardiens.feature-x)."""
    common = git_output(path, ["rev-parse", "--path-format=absolute", "--git-common-dir"])
    if not common:
        return basename(path)
    if common.endswith("/.git"):
        return basename(os.path.dirname(common))
    return basename(common)


# --------------------------------------------------------------------------
# JSON
# --------------------------------------------------------------------------


def load_json_docs(text):
    """The document in `text`, or one document per line when it is a line stream."""
    try:
        return [json.loads(text)]
    except ValueError:
        pass
    docs = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            docs.append(json.loads(line))
        except ValueError:
            continue
    return docs


def find_value(node, key):
    """First value for `key`, in document order. _MISSING when the key is absent."""
    if isinstance(node, dict):
        for name, value in node.items():
            if name == key:
                return value
            found = find_value(value, key)
            if found is not _MISSING:
                return found
    elif isinstance(node, list):
        for value in node:
            found = find_value(value, key)
            if found is not _MISSING:
                return found
    return _MISSING


def iter_objects(node):
    """Every object in the document, outermost first, in document order."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            for found in iter_objects(value):
                yield found
    elif isinstance(node, list):
        for value in node:
            for found in iter_objects(value):
                yield found


def as_str(value):
    return value if isinstance(value, str) else ""


def json_str(text, key):
    """First string value for `key` in a JSON blob."""
    for doc in load_json_docs(text):
        found = find_value(doc, key)
        if found is not _MISSING:
            return as_str(found)
    return ""


def scoped_value(scope, doc, key):
    """`key` inside `scope`, else anywhere in `doc`. The pane object of an event
    carries the pane's own cwd and tokens; an event that also carries the
    workspace's would otherwise be read as the pane's."""
    if scope is not None:
        found = find_value(scope, key)
        if found is not _MISSING:
            return found
    found = find_value(doc, key)
    return None if found is _MISSING else found


# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------


def marker_kind(name):
    """The stack a marker file name stands for, or None."""
    if name.endswith(MARKER_SUFFIXES):
        return "ios"
    return MARKER_NAMES.get(name)


def markers(root):
    """(path, depth) for every marker under `root`, down to depth 3. Dot-directories
    (.git, .opencode, .build, .venv, ...) and dependency or build folders are skipped."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        relative = os.path.relpath(dirpath, root)
        depth = 0 if relative == os.curdir else relative.count(os.sep) + 1
        dirnames[:] = [d for d in dirnames if d[:1] != "." and d not in PRUNED_DIRS]
        for name in filenames + dirnames:
            if marker_kind(name) is not None:
                found.append((os.path.join(dirpath, name), depth + 1))
        if depth >= 2:
            # Anything below would sit at depth 4.
            dirnames[:] = []
    return found


def has_lockfile(directory):
    """A JavaScript lock file next to a package.json."""
    return any(os.path.isfile(os.path.join(directory, name)) for name in LOCK_FILES)


def detect(root, icon_set):
    """Markers are searched down to depth 3, skipping dependency and build folders.
    A marker in the folder itself decides alone, so a repository with its own
    pyproject.toml is Python even when a sub-app one level down has package.json;
    markers further down decide only when the folder itself holds none (a monorepo
    with ios/App/Foo.xcodeproj and backend/). iOS and Android markers together are
    the KMP case at any depth, and show both icons. Further down, package.json
    counts only next to a lock file: a repository that uses npm for tooling keeps
    its own stack."""
    every = set()
    top = set()
    for path, depth in markers(root):
        kind = marker_kind(basename(path))
        if kind is None:
            continue
        if kind == "node" and depth > 1 and not has_lockfile(os.path.dirname(path)):
            continue
        every.add(kind)
        if depth == 1:
            top.add(kind)
    if "ios" in every and "android" in every:
        return icon_set["ios"] + icon_set["android"]
    deciding = top or every
    for kind in KINDS:
        if kind in deciding:
            return icon_set[kind]
    return ""


def config_dir():
    """The plugin config dir: `herdr plugin config-dir bonkey.stack-icon`, which
    herdr also passes in HERDR_PLUGIN_CONFIG_DIR. Asked once, because the fallback
    spawns herdr and every pane is detected on its own."""
    global _CONFIG_DIR
    if _CONFIG_DIR is None:
        directory = env("HERDR_PLUGIN_CONFIG_DIR")
        if not directory:
            _, directory = run_herdr(["plugin", "config-dir", SOURCE])
            directory = directory.rstrip("\n")
        _CONFIG_DIR = directory
    return _CONFIG_DIR


def setting(key):
    """`key = "value"` from config.toml in the plugin config dir, empty when the
    file or the key is absent. A line that does not parse is skipped, so a key
    added by a later version does not disable the ones this version knows."""
    path = os.path.join(config_dir(), "config.toml")
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError:
        return ""
    for line in text.split("\n"):
        found = SETTING_LINE.match(line)
        if found and found.group(1) == key:
            return found.group(2)
    return ""


def set_name():
    """Which icon set to report: `icons` in config.toml, else the default. An
    unknown name keeps the default and is logged."""
    name = setting("icons")
    if not name:
        return DEFAULT_ICON_SET
    if name not in ICON_SETS:
        log(
            'config.toml: icons = "%s" is not one of %s; using "%s"'
            % (name, ", ".join(sorted(ICON_SETS)), DEFAULT_ICON_SET)
        )
        return DEFAULT_ICON_SET
    return name


def icons():
    """The icons of the selected set, keyed by stack."""
    return ICON_SETS[set_name()]


def override(root):
    """overrides.toml in the plugin config dir (`herdr plugin config-dir bonkey.stack-icon`):
    one `key = "icon"` per line, key = repository name, checkout directory name,
    or a path glob (`~/` allowed). The icon is any string, so it wins over both
    icon sets. An empty icon hides the token. A file with an unparsable line is
    ignored whole.
    Returns the icon on a match, None otherwise."""
    path = os.path.join(config_dir(), "overrides.toml")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError:
        return None
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()

    entries = []
    for line in lines:
        if line == "" or line.startswith("#"):
            continue
        if not OVERRIDE_LINE.match(line):
            log("ignoring %s: cannot parse line: %s" % (path, line))
            return None
        key = line.split("=", 1)[0].strip(BLANK)
        if key.startswith('"'):
            key = key[1:]
        if key.endswith('"'):
            key = key[:-1]
        value = line.split("=", 1)[1].split('"', 1)[1].split('"', 1)[0]
        if key.startswith("~/"):
            key = os.path.join(env("HOME"), key[2:])
        entries.append((key, value))

    name = repo_name(root)
    checkout = basename(root)
    for key, value in entries:
        for candidate in (name, checkout, root):
            if fnmatch.fnmatchcase(candidate, key):
                return value
    return None


def icon_for(cwd):
    """The workspace's own folder is checked before the repository root, so a
    workspace opened in a package inside a larger repo shows that package's stack."""
    root = repo_root(cwd)
    configured = override(root)
    if configured is not None:
        return configured
    chosen = icons()
    icon = ""
    if cwd != root:
        icon = detect(cwd, chosen)
    if not icon:
        icon = detect(root, chosen)
    return icon


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def report(kind, ident, icon):
    """report <workspace|pane> <id> <icon>"""
    args = [kind, "report-metadata", ident, "--source", SOURCE]
    args += ["--token", "stack=" + icon] if icon else ["--clear-token", "stack"]
    ok, _ = run_herdr(args, capture=False)
    return ok


def pane_records(workspace):
    """(pane id, focused, folder) for every pane of the workspace."""
    _, out = run_herdr(["pane", "list", "--workspace", workspace])
    records = []
    for doc in load_json_docs(out):
        for obj in iter_objects(doc):
            if "pane_id" not in obj:
                continue
            pane_id = obj.get("pane_id")
            cwd = obj.get("cwd")
            focused = obj.get("focused")
            if isinstance(pane_id, str) and isinstance(cwd, str) and isinstance(focused, bool):
                records.append((pane_id, focused, cwd))
    return records


def report_workspace(label, workspace, cwd=""):
    """Publish an icon on every pane of the workspace (Agent rows), each one detected
    from that pane's own folder, and on the workspace itself (Space row), which
    follows the focused pane. A pane that sits in another repository therefore keeps
    its own icon instead of spreading it over its siblings. With no focused pane,
    `cwd` decides, or the first pane's folder.
    Logs one line per call in `herdr plugin log --plugin bonkey.stack-icon`."""
    ws_icon = ""
    ws_cwd = ""
    first = ""
    ok = True
    for pane_id, focused, pane_cwd in pane_records(workspace):
        icon = icon_for(pane_cwd) if os.path.isdir(pane_cwd) else ""
        if not report("pane", pane_id, icon):
            log("pane %s: report-metadata failed" % pane_id)
            ok = False
        if not first:
            first = pane_cwd
        if focused:
            ws_cwd = pane_cwd
            ws_icon = icon
    if not ws_cwd:
        ws_cwd = cwd or first
        ws_icon = icon_for(ws_cwd) if os.path.isdir(ws_cwd) else ""
    log(
        "%s %s cwd=%s root=%s icon=[%s] plugin=%s"
        % (label, workspace, ws_cwd, repo_root(ws_cwd), ws_icon, env("HERDR_PLUGIN_ROOT"))
    )
    if not report("workspace", workspace, ws_icon):
        log("workspace %s: report-metadata failed" % workspace)
        ok = False
    return ok


def seed_all():
    """Every workspace herdr currently holds. `workspace list` is answered from
    memory; it is retried because a server that is still starting answers nothing."""
    ids = []
    for attempt in range(1, 6):
        _, out = run_herdr(["workspace", "list"])
        ids = []
        for doc in load_json_docs(out):
            for obj in iter_objects(doc):
                value = obj.get("workspace_id")
                if isinstance(value, str) and value:
                    ids.append(value)
        if ids:
            break
        if attempt == 5:
            log("workspace list is empty; reported nothing")
            return False
        time.sleep(1)
    ok = True
    label = env("HERDR_PLUGIN_EVENT", "all")
    for workspace in ids:
        if not report_workspace(label, workspace):
            ok = False
    return ok


def pane_updated(line):
    """Re-detect for the event's pane only. The workspace follows the focused pane's
    cwd, so a focused pane also refreshes the Space row."""
    docs = load_json_docs(line)
    doc = docs[0] if docs else None
    pane_obj = None
    if doc is not None:
        for obj in iter_objects(doc):
            if "pane_id" in obj:
                pane_obj = obj
                break
    pane = as_str(pane_obj.get("pane_id")) if pane_obj is not None else ""
    if not pane:
        log("pane.updated without pane id")
        return False
    cwd = as_str(scoped_value(pane_obj, doc, "cwd"))
    current = as_str(scoped_value(pane_obj, doc, "stack"))
    icon = icon_for(cwd) if os.path.isdir(cwd) else ""
    if icon == current:
        return True
    workspace = as_str(scoped_value(pane_obj, doc, "workspace_id"))
    focused = scoped_value(pane_obj, doc, "focused")
    log(
        "pane.updated %s cwd=%s root=%s icon=[%s] was=[%s]"
        % (pane, cwd, repo_root(cwd), icon, current)
    )
    ok = True
    if not report("pane", pane, icon):
        log("pane %s: report-metadata failed" % pane)
        ok = False
    if workspace and focused is True:
        if not report("workspace", workspace, icon):
            log("workspace %s: report-metadata failed" % workspace)
            ok = False
    return ok


# --------------------------------------------------------------------------
# Watching
# --------------------------------------------------------------------------


def watch_once():
    """One subscription until the socket closes. True when herdr acknowledged the
    subscription, False when it did not (server down). herdr replays retained events
    first, so panes closed meanwhile fail to report; a stale replayed cwd is
    corrected by the pane's later events in the same replay."""
    path = socket_path()
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    except OSError as error:
        log("no unix socket: %s" % error)
        return False
    acked = False
    try:
        client.settimeout(HERDR_TIMEOUT)
        client.connect(path)
        client.sendall(SUBSCRIBE.encode("utf-8"))
        client.settimeout(None)
        with client.makefile("r", encoding="utf-8", errors="replace") as stream:
            for line in stream:
                line = line.rstrip("\n")
                if '"subscription_started"' in line:
                    acked = True
                elif '"pane_updated"' in line:
                    pane_updated(line)
    except OSError as error:
        log("socket %s: %s" % (path, error))
    finally:
        client.close()
    return acked


def read_pid(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return int(handle.read().strip())
    except (OSError, ValueError):
        return 0


def pid_alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def replace_previous_watcher(pidfile, me):
    """Single instance: a watcher launched by hand survives a server restart, so
    replace whatever holds the pidfile, waiting for it to actually go away."""
    old = read_pid(pidfile)
    if not old or old == me or not pid_alive(old):
        return
    log("stopping previous watcher %d" % old)
    try:
        os.kill(old, signal.SIGTERM)
    except OSError:
        pass
    for _ in range(10):
        if not pid_alive(old):
            break
        time.sleep(0.5)
    if pid_alive(old):
        log("previous watcher %d ignored TERM, killing it" % old)
        try:
            os.kill(old, signal.SIGKILL)
        except OSError:
            pass
        time.sleep(0.5)


def redirect_to_log(path):
    """herdr captures the startup hook's output until it exits; log to a file instead."""
    try:
        if os.path.getsize(path) > WATCH_LOG_LIMIT:
            open(path, "w").close()
    except OSError:
        pass
    sys.stdout.flush()
    sys.stderr.flush()
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(handle, 1)
    os.dup2(handle, 2)
    os.close(handle)


def watch():
    global _STAMP
    _STAMP = True
    state = state_dir()
    os.makedirs(state, exist_ok=True)
    redirect_to_log(os.path.join(state, "watch.log"))

    pidfile = os.path.join(state, "watch.pid")
    me = os.getpid()
    replace_previous_watcher(pidfile, me)
    with open(pidfile, "w", encoding="utf-8") as handle:
        handle.write("%d\n" % me)

    def stop(_signum, _frame):
        # Remove the pidfile only while it is still ours: a successor may already own it.
        if read_pid(pidfile) == me:
            try:
                os.remove(pidfile)
            except OSError:
                pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    log("watching %s, pid %d" % (socket_path(), me))

    failures = 0
    while True:
        seed_all()
        if watch_once():
            failures = 0
            log("socket closed, reconnecting")
        else:
            failures += 1
            log("could not subscribe (%d/3)" % failures)
            if failures >= 3:
                log("herdr is gone, exiting")
                try:
                    os.remove(pidfile)
                except OSError:
                    pass
                return True
        time.sleep(2)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def explain(cwd):
    root = repo_root(cwd)
    print("folder:    %s" % cwd)
    print("repo root: %s" % root)
    print("repo name: %s" % repo_name(root))
    configured = override(root)
    print("override:  %s" % ("(none)" if configured is None else configured))
    print("icon set:  %s" % set_name())
    print("markers under folder:")
    for path, _ in markers(cwd):
        print(strip_base(path, cwd))
    if cwd != root:
        print("markers under repo root:")
        for path, _ in markers(root):
            print(strip_base(path, root))
    print("icon:      [%s]" % icon_for(cwd))


def strip_base(path, base):
    prefix = base + "/"
    return "  " + path[len(prefix):] if path.startswith(prefix) else path


def usage(option):
    print("stack-icon.py: usage: stack-icon.py %s <path>" % option, file=sys.stderr)
    return 1


def main(argv):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    option = argv[0] if argv else ""
    path = argv[1] if len(argv) > 1 else ""

    if option == "--detect":
        if not path:
            return usage("--detect")
        print(icon_for(path))
        return 0

    if option == "--explain":
        if not path:
            return usage("--explain")
        explain(path)
        return 0

    if option == "--watch" or env("HERDR_PLUGIN_EVENT") == "startup":
        return 0 if watch() else 1

    if option == "--all":
        return 0 if seed_all() else 1

    context = env("HERDR_PLUGIN_CONTEXT_JSON")
    workspace = env("HERDR_WORKSPACE_ID") or json_str(context, "workspace_id")
    if not workspace:
        log("no workspace in context")
        return 1
    label = env("HERDR_PLUGIN_EVENT") or env("HERDR_PLUGIN_ACTION_ID", "run")
    return 0 if report_workspace(label, workspace, json_str(context, "workspace_cwd")) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
