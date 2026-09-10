"""Shared fixtures: the plugin entry point, a stub herdr, the call log it writes,
and the plugin config file that selects an icon set.

The stub answers `workspace list` and `pane list` from files named by the
WORKSPACES and PANES environment variables, and appends every report-metadata
call to CALLS, one call per line, so a test can assert on what was published.

It also stands in for `config check`, which accepts whatever it is given unless
CHECK_EXIT says otherwise, and for `server reload-config`. Both are recorded in
CALLS as well; `config check` records the file it was pointed at, so a test can
show that the live config was never the one under examination.
"""

import os
import stat
import subprocess
import sys
import tempfile

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "stack-icon.py")

STUB = '''#!/usr/bin/env python3
import os
import sys

argv = sys.argv[1:]


def record(line):
    path = os.environ.get("CALLS")
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line + "\\n")


if argv[:2] == ["workspace", "list"]:
    sys.stdout.write(open(os.environ["WORKSPACES"], encoding="utf-8").read())
elif argv[:2] == ["pane", "list"]:
    sys.stdout.write(open(os.environ["PANES"], encoding="utf-8").read())
elif argv[:2] == ["config", "check"]:
    record("config check " + os.environ.get("HERDR_CONFIG_PATH", ""))
    code = int(os.environ.get("CHECK_EXIT", "0"))
    sys.stdout.write("config: issues found\\nrejected by the stub\\n" if code else "config: ok\\n")
    sys.exit(code)
elif argv[:2] == ["server", "reload-config"]:
    record("server reload-config")
elif len(argv) > 1 and argv[1] == "report-metadata":
    record(" ".join(argv))
'''


def make_stub(directory):
    """Write the stub herdr into `directory` and return its path."""
    path = os.path.join(directory, "herdr")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(STUB)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def make_repo(folder):
    """Make `folder` a git checkout, which every real herdr workspace is. A folder
    outside a checkout is detected as nothing, so a fixture that tests the rules
    has to be one."""
    os.makedirs(folder, exist_ok=True)
    subprocess.run(
        ["git", "init", "-q", folder],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    return folder


def write(path, text=""):
    """Create a file, and the folders leading to it."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def plugin_config(config_dir, **settings):
    """Write the plugin's own config.toml, one `key = "value"` per setting."""
    lines = ['%s = "%s"\n' % (key, value) for key, value in sorted(settings.items())]
    return write(os.path.join(config_dir, "config.toml"), "".join(lines))


def choose_icons(config_dir, name):
    """Write the plugin config.toml that selects an icon set."""
    return plugin_config(config_dir, icons=name)


def calls(path):
    """Every report-metadata call the stub recorded."""
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as handle:
        return [line for line in handle.read().split("\n") if line]


def run_logged(args, environment, timeout=60):
    """Run the plugin entry point and return (returncode, stdout, log). The
    plugin's log is what it writes to stderr."""
    done = subprocess.run(
        [sys.executable, SCRIPT] + args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        timeout=timeout,
    )
    return done.returncode, done.stdout.decode("utf-8"), done.stderr.decode("utf-8")


def run_script(args, environment, timeout=60):
    """Run the plugin entry point and return (returncode, stdout)."""
    code, out, _ = run_logged(args, environment, timeout)
    return code, out


def workdir(case, prefix):
    """A temporary folder removed when the test ends."""
    directory = tempfile.mkdtemp(prefix=prefix)
    case.addCleanup(_remove, directory)
    return directory


def _remove(directory):
    import shutil

    shutil.rmtree(directory, ignore_errors=True)
