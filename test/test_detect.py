#!/usr/bin/env python3
"""Fixture tests for the detection rules. Each case builds a folder tree, runs
`stack-icon.py --detect` on it and compares the icon. No herdr and no network:
HERDR_PLUGIN_CONFIG_DIR points at an empty folder, so no override matches, and
a fixture is not a git checkout, so the folder is its own repository root.

    python3 -m unittest discover -s test
"""

import os
import unittest

import support


class DetectTest(unittest.TestCase):
    def setUp(self):
        self.work = support.workdir(self, "stack-icon-test.")
        self.config = os.path.join(self.work, "config")
        os.makedirs(self.config)
        self.cases = 0

    def icon_of(self, folder):
        environment = dict(os.environ, HERDR_PLUGIN_CONFIG_DIR=self.config)
        code, out = support.run_script(["--detect", folder], environment)
        self.assertEqual(code, 0)
        return out.rstrip("\n")

    def fixture(self, *entries):
        """Create each entry under a fresh folder and return its icon. An entry
        ending in / is created as a directory."""
        self.cases += 1
        folder = os.path.join(self.work, "case%d" % self.cases)
        os.makedirs(folder)
        for entry in entries:
            if entry.endswith("/"):
                os.makedirs(os.path.join(folder, entry), exist_ok=True)
            else:
                support.write(os.path.join(folder, entry))
        return self.icon_of(folder)

    # The folder's own marker decides.

    def test_own_pyproject_beats_a_sub_app_package_json(self):
        icon = self.fixture("pyproject.toml", "viewer/package.json", "viewer/package-lock.json")
        self.assertEqual(icon, "🐍")

    def test_own_package_json_beats_a_crate_further_down(self):
        icon = self.fixture("package.json", "package-lock.json", "utilities/parser/Cargo.toml")
        self.assertEqual(icon, "🟩")

    def test_own_go_mod(self):
        self.assertEqual(self.fixture("go.mod"), "🐹")

    def test_ios_and_android_in_the_folder_itself(self):
        self.assertEqual(self.fixture("Package.swift", "settings.gradle.kts"), "🍏🤖")

    # Markers further down decide when the folder itself holds none.

    def test_monorepo_ios_beats_a_backend_package_json(self):
        icon = self.fixture("ios/App/App.xcodeproj/", "backend/package.json", "backend/yarn.lock")
        self.assertEqual(icon, "🍏")

    def test_kmp_ios_and_android_at_different_depths(self):
        icon = self.fixture("settings.gradle.kts", "iosApp/iosApp.xcodeproj/")
        self.assertEqual(icon, "🍏🤖")

    # package.json only counts in the folder itself or next to a lock file.

    def test_npm_for_tooling_only_no_lock_file(self):
        self.assertEqual(self.fixture("docs/tools/package.json"), "")

    def test_sub_app_with_a_lock_file(self):
        icon = self.fixture("docs/tools/package.json", "docs/tools/yarn.lock")
        self.assertEqual(icon, "🟩")

    def test_no_marker_at_all(self):
        self.assertEqual(self.fixture("README.md"), "")

    # A path that the shell version's `cut -d'"'` string picking could not carry.

    def test_a_path_containing_a_double_quote(self):
        folder = os.path.join(self.work, 'say "hi"')
        os.makedirs(folder)
        support.write(os.path.join(folder, "go.mod"))
        self.assertEqual(self.icon_of(folder), "🐹")


if __name__ == "__main__":
    unittest.main()
