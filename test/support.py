"""Shared fixtures: the plugin entry point, a stub herdr, the call log it writes,
and the plugin config file that selects an icon set.

The stub answers `workspace list` and `pane list` from files named by the
WORKSPACES and PANES environment variables, and appends every report-metadata
call to CALLS, one call per line, so a test can assert on what was published.
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
if argv[:2] == ["workspace", "list"]:
    sys.stdout.write(open(os.environ["WORKSPACES"], encoding="utf-8").read())
elif argv[:2] == ["pane", "list"]:
    sys.stdout.write(open(os.environ["PANES"], encoding="utf-8").read())
elif len(argv) > 1 and argv[1] == "report-metadata":
    with open(os.environ["CALLS"], "a", encoding="utf-8") as handle:
        handle.write(" ".join(argv) + "\\n")
'''


def make_stub(directory):
    """Write the stub herdr into `directory` and return its path."""
    path = os.path.join(directory, "herdr")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(STUB)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def write(path, text=""):
    """Create a file, and the folders leading to it."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def choose_icons(config_dir, name):
    """Write the plugin config.toml that selects an icon set."""
    return write(os.path.join(config_dir, "config.toml"), 'icons = "%s"\n' % name)


def calls(path):
    """Every report-metadata call the stub recorded."""
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as handle:
        return [line for line in handle.read().split("\n") if line]


def run_script(args, environment, timeout=60):
    """Run the plugin entry point and return (returncode, stdout)."""
    done = subprocess.run(
        [sys.executable, SCRIPT] + args,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=environment,
        timeout=timeout,
    )
    return done.returncode, done.stdout.decode("utf-8")


def workdir(case, prefix):
    """A temporary folder removed when the test ends."""
    directory = tempfile.mkdtemp(prefix=prefix)
    case.addCleanup(_remove, directory)
    return directory


def _remove(directory):
    import shutil

    shutil.rmtree(directory, ignore_errors=True)
