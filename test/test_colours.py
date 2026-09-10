#!/usr/bin/env python3
"""The colour recipe in README.md is herdr configuration, not code, so nothing
in the plugin can go wrong when it drifts: a glyph that gains a codepoint, or a
rule left behind, would simply stop matching and show up as an uncoloured icon
in somebody's sidebar. These cases read the rules out of README.md and hold them
against the icons `stack-icon.py --detect` really reports.

    python3 -m unittest discover -s test
"""

import os
import re
import unittest

import support

README = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "README.md")

# The marker that stands for each stack, as in test_detect.py.
MARKERS = {
    "ios": "Package.swift",
    "android": "settings.gradle.kts",
    "rust": "Cargo.toml",
    "go": "go.mod",
    "node": "package.json",
    "py": "pyproject.toml",
}

# One `$stack` token entry in a rows table, and the rules written on it. Each
# panel styles its own occurrence, so the recipe holds the token twice.
OCCURRENCE = re.compile(r'token = "\$stack", rules = \[(.*?)\]\s*\}', re.S)
RULE = re.compile(r'\{ equals = "([^"]*)", fg = "([^"]*)" \}')
ESCAPE = re.compile(r'\\u([0-9a-fA-F]{4})')

# What herdr accepts: a strict #RGB or #RRGGBB, and at most 16 rules per token.
COLOUR = re.compile(r'\A#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\Z')
RULE_LIMIT = 16


def unescape(value):
    """A TOML basic string that holds \\uXXXX escapes and no other escape."""
    return ESCAPE.sub(lambda found: chr(int(found.group(1), 16)), value)


def occurrences():
    """The rules of each `$stack` occurrence, as [(icon, colour), ...]."""
    with open(README, "r", encoding="utf-8") as handle:
        text = handle.read()
    return [
        [(unescape(icon), colour) for icon, colour in RULE.findall(block)]
        for block in OCCURRENCE.findall(text)
    ]


class ColourRulesTest(unittest.TestCase):
    def setUp(self):
        self.work = support.workdir(self, "stack-icon-colour.")
        self.config = os.path.join(self.work, "config")
        os.makedirs(self.config)
        self.cases = 0
        self.rules = occurrences()
        self.assertTrue(self.rules, "README.md holds no $stack rules")

    def icon_of(self, *entries):
        """The icon the plugin reports for a checkout holding `entries`. No
        config.toml is written, so the shipped default set decides."""
        self.cases += 1
        folder = support.make_repo(os.path.join(self.work, "case%d" % self.cases))
        for entry in entries:
            support.write(os.path.join(folder, entry))
        environment = dict(os.environ, HERDR_PLUGIN_CONFIG_DIR=self.config)
        code, out = support.run_script(["--detect", folder], environment)
        self.assertEqual(code, 0)
        return out.rstrip("\n")

    def reported(self):
        """Every icon the default set can put in the token."""
        icons = [self.icon_of(marker) for marker in sorted(MARKERS.values())]
        icons.append(self.icon_of(MARKERS["ios"], MARKERS["android"]))
        return icons

    def test_both_panels_carry_the_same_rules(self):
        self.assertEqual(len(self.rules), 2)
        self.assertEqual(self.rules[0], self.rules[1])

    def test_every_icon_the_plugin_reports_has_a_rule(self):
        coloured = dict(self.rules[0])
        for icon in self.reported():
            with self.subTest(icon=[icon]):
                self.assertTrue(icon, "the plugin reported nothing to colour")
                self.assertIn(icon, coloured)

    def test_no_rule_names_an_icon_the_plugin_cannot_report(self):
        reported = self.reported()
        for icon, _ in self.rules[0]:
            with self.subTest(icon=[icon]):
                self.assertIn(icon, reported)

    def test_every_rule_sets_a_colour_herdr_accepts(self):
        for icon, colour in self.rules[0]:
            with self.subTest(icon=[icon]):
                self.assertRegex(colour, COLOUR)

    def test_every_icon_gets_a_colour_of_its_own(self):
        colours = [colour for _, colour in self.rules[0]]
        self.assertEqual(len(colours), len(set(colours)))

    def test_no_token_holds_more_rules_than_herdr_allows(self):
        for block in self.rules:
            self.assertLessEqual(len(block), RULE_LIMIT)


if __name__ == "__main__":
    unittest.main()
