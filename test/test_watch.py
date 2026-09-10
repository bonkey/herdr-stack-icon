#!/usr/bin/env python3
"""Tests for the --watch path against a herdr socket the test itself serves and a
stub herdr. They cover the loop guard: report-metadata on a pane emits
pane.updated, so a pane whose token already matches must not be reported again,
and the token that decides is the pane's own, not a workspace token the same
event happens to carry. The icon set is pinned to emoji, which also shows that
the watcher reads the setting.

    python3 -m unittest discover -s test
"""

import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
import unittest

import support

STAMPED = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} stack-icon: ")


def event(pane_id, cwd, focused, pane_token, workspace_token):
    """A pane.updated event that carries the workspace's token before the pane's."""
    return json.dumps(
        {
            "method": "event",
            "params": {
                "type": "pane_updated",
                "workspace": {"workspace_id": "w1", "tokens": {"stack": workspace_token}},
                "pane": {
                    "pane_id": pane_id,
                    "workspace_id": "w1",
                    "cwd": cwd,
                    "focused": focused,
                    "tokens": {"stack": pane_token},
                },
            },
        }
    )


class WatchTest(unittest.TestCase):
    def setUp(self):
        self.work = support.workdir(self, "si-watch.")
        self.config = os.path.join(self.work, "config")
        os.makedirs(self.config)
        support.choose_icons(self.config, "emoji")
        self.py = support.make_repo(os.path.join(self.work, "py"))
        self.go = support.make_repo(os.path.join(self.work, "go"))
        support.write(os.path.join(self.py, "pyproject.toml"))
        support.write(os.path.join(self.go, "go.mod"))

        self.calls_file = os.path.join(self.work, "calls")
        support.write(self.calls_file)
        workspaces = support.write(
            os.path.join(self.work, "workspaces.json"),
            json.dumps({"result": {"workspaces": [{"workspace_id": "wseed"}]}}),
        )
        panes = support.write(
            os.path.join(self.work, "panes.json"), json.dumps({"result": {"panes": []}})
        )

        self.socket_path = os.path.join(self.work, "herdr.sock")
        self.assertLess(len(self.socket_path), 100, "unix socket paths are length limited")
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(self.socket_path)
        self.server.listen(1)
        self.server.settimeout(30)
        self.addCleanup(self.server.close)

        self.state = os.path.join(self.work, "state")
        self.environment = dict(
            os.environ,
            HERDR_PLUGIN_CONFIG_DIR=self.config,
            HERDR_PLUGIN_STATE_DIR=self.state,
            HERDR_SOCKET_PATH=self.socket_path,
            HERDR_BIN_PATH=support.make_stub(self.work),
            CALLS=self.calls_file,
            PANES=panes,
            WORKSPACES=workspaces,
        )

    def start_watcher(self):
        watcher = subprocess.Popen(
            [sys.executable, support.SCRIPT, "--watch"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=self.environment,
        )
        self.addCleanup(self.stop_watcher, watcher)
        return watcher

    def stop_watcher(self, watcher):
        if watcher.poll() is not None:
            return
        watcher.send_signal(signal.SIGTERM)
        try:
            watcher.wait(timeout=10)
        except subprocess.TimeoutExpired:
            watcher.kill()
            watcher.wait(timeout=10)

    def wait_for_call(self, wanted, seconds=20):
        deadline = time.time() + seconds
        while time.time() < deadline:
            if any(wanted in line for line in support.calls(self.calls_file)):
                return
            time.sleep(0.05)
        self.fail(
            "no call matching %s within %ds\ncalls were:\n  %s\nlog:\n%s"
            % (wanted, seconds, "\n  ".join(support.calls(self.calls_file)), self.watch_log())
        )

    def watch_log(self):
        path = os.path.join(self.state, "watch.log")
        if not os.path.exists(path):
            return "(no watch.log)"
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()

    def test_pane_updated_uses_the_panes_own_token(self):
        self.start_watcher()
        connection, _ = self.server.accept()
        self.addCleanup(connection.close)
        connection.settimeout(30)
        stream = connection.makefile("rw", encoding="utf-8", errors="replace")

        request = json.loads(stream.readline())
        self.assertEqual(request["method"], "events.subscribe")
        self.assertEqual(request["params"]["subscriptions"], [{"type": "pane.updated"}])
        stream.write('{"id":"stack-icon","result":{"status":"subscription_started"}}\n')

        # The pane already holds the icon its folder gives; the workspace token in
        # the same event is a different one and must not decide.
        stream.write(event("w1:p1", self.py, False, "🐍", "🐹") + "\n")
        # A stale pane token, with a workspace token that happens to equal the new
        # icon: the pane must still be corrected, and the Space row follows it.
        stream.write(event("w1:p2", self.go, True, "🐍", "🐹") + "\n")
        stream.flush()

        self.wait_for_call("pane report-metadata w1:p2 --source bonkey.stack-icon --token stack=🐹")
        self.wait_for_call("workspace report-metadata w1 --source bonkey.stack-icon --token stack=🐹")
        # Events are handled in order, so the first one is done by now.
        self.assertEqual([line for line in support.calls(self.calls_file) if "w1:p1" in line], [])

    def test_the_watcher_owns_a_pid_file_and_a_stamped_log(self):
        watcher = self.start_watcher()
        connection, _ = self.server.accept()
        self.addCleanup(connection.close)
        connection.settimeout(30)
        connection.makefile("r", encoding="utf-8", errors="replace").readline()

        pidfile = os.path.join(self.state, "watch.pid")
        deadline = time.time() + 20
        while time.time() < deadline and not os.path.exists(pidfile):
            time.sleep(0.05)
        with open(pidfile, "r", encoding="utf-8") as handle:
            self.assertEqual(int(handle.read().strip()), watcher.pid)

        lines = [line for line in self.watch_log().split("\n") if line]
        self.assertTrue(lines, "watch.log is empty")
        for line in lines:
            self.assertRegex(line, STAMPED)

        self.stop_watcher(watcher)
        self.assertFalse(os.path.exists(pidfile), "the watcher left its pid file behind")


if __name__ == "__main__":
    unittest.main()
