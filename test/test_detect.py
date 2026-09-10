#!/usr/bin/env python3
"""Fixture tests for the detection rules and for the two icon sets. Each case
builds a folder tree, runs `stack-icon.py --detect` on it and compares the icon.
No herdr and no network: HERDR_PLUGIN_CONFIG_DIR points at a folder the case
owns, which also holds the config.toml that selects the set. A fixture is a git
checkout, because a folder outside one is detected as nothing.

    python3 -m unittest discover -s test
"""

import os
import unittest

import support

# The marker that stands for each stack, and the icon each set reports for it.
# Every stack appears in both tables, so a glyph that is empty or missing fails
# a case instead of quietly leaving the sidebar blank.
MARKERS = {
    "ios": "Package.swift",
    "android": "settings.gradle.kts",
    "rust": "Cargo.toml",
    "go": "go.mod",
    "node": "package.json",
    "py": "pyproject.toml",
}

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


class Fixtures(unittest.TestCase):
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
        support.make_repo(folder)
        for entry in entries:
            if entry.endswith("/"):
                os.makedirs(os.path.join(folder, entry), exist_ok=True)
            else:
                support.write(os.path.join(folder, entry))
        return self.icon_of(folder)


class DetectTest(Fixtures):
    """The rules that pick a stack. The icon set is pinned to emoji, so a rule
    is read against one fixed alphabet."""

    def setUp(self):
        Fixtures.setUp(self)
        support.choose_icons(self.config, "emoji")

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
        folder = support.make_repo(os.path.join(self.work, 'say "hi"'))
        support.write(os.path.join(folder, "go.mod"))
        self.assertEqual(self.icon_of(folder), "🐹")


class IconSetTest(Fixtures):
    """Which alphabet a decided stack is reported in. setUp writes no
    config.toml, so a case sees the shipped default until it asks for a set."""

    def each_stack(self, wanted):
        for kind in sorted(MARKERS):
            with self.subTest(kind=kind):
                self.assertTrue(wanted[kind], "the table has no icon for %s" % kind)
                self.assertEqual(self.fixture(MARKERS[kind]), wanted[kind])

    def test_nerd_font_glyphs_are_the_default(self):
        self.each_stack(NERD)

    def test_the_config_switches_to_emoji(self):
        support.choose_icons(self.config, "emoji")
        self.each_stack(EMOJI)

    def test_an_unknown_set_keeps_the_default(self):
        support.choose_icons(self.config, "runes")
        self.each_stack(NERD)

    def test_kmp_shows_both_technologies_in_both_sets(self):
        both = ("Package.swift", "settings.gradle.kts")
        self.assertEqual(self.fixture(*both), NERD["ios"] + NERD["android"])
        support.choose_icons(self.config, "emoji")
        self.assertEqual(self.fixture(*both), EMOJI["ios"] + EMOJI["android"])

    def test_an_override_beats_both_sets(self):
        """An overrides.toml icon is any string, so it wins over whichever set
        is in force. The key globs over the folder name every fixture gets."""
        support.write(os.path.join(self.config, "overrides.toml"), '"case*" = "🏒"\n')
        self.assertEqual(self.fixture("go.mod"), "🏒")
        support.choose_icons(self.config, "emoji")
        self.assertEqual(self.fixture("go.mod"), "🏒")


class OutsideACheckoutTest(Fixtures):
    """A folder that is not a git checkout is not a project. A home directory
    holds somebody's demo three folders down; that must not become its icon."""

    def setUp(self):
        Fixtures.setUp(self)
        support.choose_icons(self.config, "emoji")
        self.cases = 0

    def plain(self, *entries):
        """Like `fixture`, without making the folder a checkout."""
        self.cases += 1
        folder = os.path.join(self.work, "plain%d" % self.cases)
        os.makedirs(folder)
        for entry in entries:
            support.write(os.path.join(folder, entry))
        return folder

    def test_a_project_further_down_gives_no_icon(self):
        folder = self.plain("Documents/demo/package.json", "Documents/demo/package-lock.json")
        self.assertEqual(self.icon_of(folder), "")

    def test_even_a_marker_in_the_folder_itself_gives_no_icon(self):
        self.assertEqual(self.icon_of(self.plain("go.mod")), "")

    def test_an_override_still_decides(self):
        support.write(os.path.join(self.config, "overrides.toml"), '"plain*" = "🏒"\n')
        self.assertEqual(self.icon_of(self.plain("go.mod")), "🏒")

    def test_a_checkout_of_the_same_tree_is_detected(self):
        """The same folders inside a checkout keep their icon, so the rule above
        turns on being a repository and on nothing else."""
        folder = self.plain("Documents/demo/package.json", "Documents/demo/package-lock.json")
        support.make_repo(folder)
        self.assertEqual(self.icon_of(folder), EMOJI["node"])


if __name__ == "__main__":
    unittest.main()
