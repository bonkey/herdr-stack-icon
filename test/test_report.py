#!/usr/bin/env python3
"""Tests for what report_workspace publishes, with a stub herdr: it answers
`pane list` from a fixture and records every report-metadata call in a file.
Two folders stand in for two repositories, so a workspace whose panes sit in
different repositories must produce different icons. The icon set is pinned to
emoji, which also shows that the event path reads the setting.

    python3 -m unittest discover -s test
"""

import json
import os
import unittest

import support


def pane(pane_id, cwd, focused):
    return {
        "cwd": cwd,
        "focused": focused,
        "foreground_cwd": cwd,
        "pane_id": pane_id,
        "workspace_id": "w1",
    }


class ReportTest(unittest.TestCase):
    def setUp(self):
        self.work = support.workdir(self, "stack-icon-report-test.")
        self.config = os.path.join(self.work, "config")
        os.makedirs(self.config)
        support.choose_icons(self.config, "emoji")
        self.py = os.path.join(self.work, "py")
        self.go = os.path.join(self.work, "go")
        support.write(os.path.join(self.py, "pyproject.toml"))
        support.write(os.path.join(self.go, "go.mod"))
        self.calls_file = os.path.join(self.work, "calls")
        self.panes_file = os.path.join(self.work, "panes.json")
        self.environment = dict(
            os.environ,
            HERDR_PLUGIN_CONFIG_DIR=self.config,
            HERDR_BIN_PATH=support.make_stub(self.work),
            CALLS=self.calls_file,
            PANES=self.panes_file,
        )

    def run_case(self, *panes):
        support.write(self.calls_file)
        support.write(self.panes_file, json.dumps({"result": {"panes": list(panes)}}))
        environment = dict(self.environment, HERDR_PLUGIN_EVENT="pane.created", HERDR_WORKSPACE_ID="w1")
        support.run_script([], environment)

    def expect(self, wanted):
        matching = [line for line in support.calls(self.calls_file) if wanted in line]
        self.assertEqual(
            len(matching),
            1,
            "no single call matching: %s\ncalls were:\n  %s"
            % (wanted, "\n  ".join(support.calls(self.calls_file))),
        )

    def test_a_pane_keeps_the_icon_of_its_own_repository(self):
        """The workspace follows the focused pane; a pane that has moved into
        another repository keeps its own icon."""
        self.run_case(
            pane("w1:p1", self.py, False),
            pane("w1:p2", self.py, False),
            pane("w1:p3", self.go, True),
        )
        self.expect("pane report-metadata w1:p1 --source bonkey.stack-icon --token stack=🐍")
        self.expect("pane report-metadata w1:p2 --source bonkey.stack-icon --token stack=🐍")
        self.expect("pane report-metadata w1:p3 --source bonkey.stack-icon --token stack=🐹")
        self.expect("workspace report-metadata w1 --source bonkey.stack-icon --token stack=🐹")

    def test_without_a_focused_pane_the_workspace_takes_the_first_one(self):
        self.run_case(pane("w1:p1", self.py, False), pane("w1:p2", self.go, False))
        self.expect("workspace report-metadata w1 --source bonkey.stack-icon --token stack=🐍")
        self.expect("pane report-metadata w1:p2 --source bonkey.stack-icon --token stack=🐹")

    def test_a_pane_folder_containing_a_double_quote(self):
        """The shell version picked the cwd out of the JSON with `cut -d'"'`, which
        truncated the path at the quote and detected nothing."""
        quoted = os.path.join(self.work, 'say "hi"')
        support.write(os.path.join(quoted, "Cargo.toml"))
        self.run_case(pane("w1:p1", quoted, True))
        self.expect("pane report-metadata w1:p1 --source bonkey.stack-icon --token stack=🦀")
        self.expect("workspace report-metadata w1 --source bonkey.stack-icon --token stack=🦀")


if __name__ == "__main__":
    unittest.main()
