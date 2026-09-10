#!/usr/bin/env python3
"""Tests for the patcher that writes the $stack colour rules into herdr's
config.toml. That file is hand-maintained and a rule herdr rejects makes it fall
back to the default sidebar, dropping every custom row, so the cases below hold
the patcher to three promises: it edits the $stack elements and nothing else, it
never leaves a file behind that `herdr config check` did not accept, and a run
that has nothing to do does nothing at all.

The stub herdr answers `config check` (CHECK_EXIT makes it refuse) and records
what it was pointed at, so a rejected result can be told apart from an accepted
one without herdr itself.

`fixtures/user-config.toml` is a real config, rules and all, and the round trip
over it is the case that matters most: nerd, emoji, nerd again, byte for byte.

    python3 -m unittest discover -s test
"""

import os
import re
import unittest

import support

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

RULE = re.compile(r'\{ equals = "([^"]*)", fg = "([^"]*)" \},')
COLOUR = re.compile(r"\A#[0-9a-f]{6}\Z")
TOKEN_ENTRY = "{ token = \"$stack\""

# What herdr accepts on one token.
RULE_LIMIT = 16


def panel(name, element, tail='"workspace"'):
    return '[ui.sidebar.%s]\nrows = [\n  ["state_icon", %s, %s],\n  ["branch"],\n]\n' % (
        name,
        element,
        tail,
    )


def both(element):
    return panel("spaces", element) + "\n" + panel("agents", element)


def rules_of(text):
    """Every (icon, colour) rule in a config, in the order they are written."""
    return RULE.findall(text)


class ConfigRulesTest(unittest.TestCase):
    def setUp(self):
        self.work = support.workdir(self, "stack-icon-rules.")
        self.plugin = os.path.join(self.work, "plugin-config")
        os.makedirs(self.plugin)
        self.state = os.path.join(self.work, "state")
        self.calls = os.path.join(self.work, "calls")
        self.path = os.path.join(self.work, "config.toml")
        self.environment = dict(
            os.environ,
            HERDR_PLUGIN_CONFIG_DIR=self.plugin,
            HERDR_PLUGIN_STATE_DIR=self.state,
            HERDR_BIN_PATH=support.make_stub(self.work),
            HERDR_CONFIG_PATH=self.path,
            CALLS=self.calls,
        )
        self.environment.pop("CHECK_EXIT", None)

    # -- fixtures ---------------------------------------------------------

    def given(self, text, **settings):
        """Herdr's config, and the plugin's own settings when there are any."""
        if settings:
            support.plugin_config(self.plugin, **settings)
        support.write(self.path, text)
        return text

    def given_user_config(self, **settings):
        with open(os.path.join(FIXTURES, "user-config.toml"), "r", encoding="utf-8") as handle:
            return self.given(handle.read(), **settings)

    # -- running ----------------------------------------------------------

    def colours(self, **environment):
        """`--colours`, returning (returncode, the log it wrote)."""
        code, _, log = support.run_logged(["--colours"], dict(self.environment, **environment))
        return code, log

    def written(self):
        with open(self.path, "r", encoding="utf-8") as handle:
            return handle.read()

    def backups(self):
        if not os.path.isdir(self.state):
            return []
        return sorted(name for name in os.listdir(self.state) if name.startswith("config-"))

    # -- assertions -------------------------------------------------------

    def assert_untouched(self, original):
        self.assertEqual(self.written(), original)

    def assert_full_palette(self, text):
        """Every rule the plugin wrote, on every occurrence it found."""
        rules = rules_of(text)
        entries = text.count(TOKEN_ENTRY)
        self.assertTrue(entries, "no $stack entry in the result")
        self.assertEqual(len(rules) % entries, 0)
        per_entry = len(rules) // entries
        self.assertGreater(per_entry, 1)
        self.assertLessEqual(per_entry, RULE_LIMIT)
        for index in range(1, entries):
            self.assertEqual(
                rules[:per_entry],
                rules[index * per_entry:(index + 1) * per_entry],
                "the panels were given different rules",
            )
        icons = [icon for icon, _ in rules[:per_entry]]
        self.assertEqual(len(set(icons)), per_entry, "an icon has two rules")
        for icon, colour in rules[:per_entry]:
            self.assertRegex(colour, COLOUR)
            self.assertRegex(icon, r"\A(?:\\u[0-9a-f]{4})+\Z", "the glyph is not escaped")
        return rules[:per_entry]

    # -- the shapes a real config has -------------------------------------

    def test_an_entry_without_rules_gains_them(self):
        self.given(both('{ token = "$stack" }'))
        code, log = self.colours()
        self.assertEqual(code, 0)
        self.assertIn("wrote the $stack colour rules", log)
        self.assert_full_palette(self.written())

    def test_a_bare_string_becomes_an_entry_with_rules(self):
        """herdr accepts `"$stack"` as a row element; it cannot carry a style, so
        the patcher gives it the entry it needs."""
        self.given(both('"$stack"'))
        self.assertEqual(self.colours()[0], 0)
        self.assert_full_palette(self.written())
        self.assertEqual(self.written().count(TOKEN_ENTRY), 2)

    def test_rules_that_are_already_there_are_replaced(self):
        self.given(both('{ token = "$stack", rules = [ { equals = "x", fg = "#010203" } ] }'))
        self.assertEqual(self.colours()[0], 0)
        after = self.written()
        self.assertNotIn('equals = "x"', after)
        self.assert_full_palette(after)

    def test_a_style_on_the_entry_is_kept(self):
        """`fg`, `bold` and `dim` style every value that no rule matches, which is
        the reporter's own business, so they stay where they were."""
        self.given(
            both('{ token = "$stack", fg = "#888888", bold = true, dim = false }')
        )
        self.assertEqual(self.colours()[0], 0)
        after = self.written()
        self.assertIn(
            '{ token = "$stack", fg = "#888888", bold = true, dim = false, rules = [', after
        )
        self.assert_full_palette(after)

    def test_the_token_in_one_panel_only(self):
        original = self.given(panel("spaces", '{ token = "$stack" }') + panel("agents", '"agent"'))
        self.assertEqual(self.colours()[0], 0)
        after = self.written()
        self.assertEqual(after.count(TOKEN_ENTRY), 1)
        self.assertIn(panel("agents", '"agent"'), after)
        self.assertIn(original.split("[ui.sidebar.agents]")[1], after)

    def test_the_token_in_both_panels(self):
        self.given(both('{ token = "$stack" }'))
        self.assertEqual(self.colours()[0], 0)
        self.assertEqual(self.written().count(TOKEN_ENTRY), 2)

    # -- everything else stays where it was --------------------------------

    def test_no_line_outside_the_token_entry_moves(self):
        original = self.given(
            "# a comment nobody wants reformatted\n"
            "\n"
            "[theme]\n"
            'name = "rose-pine-dawn"   # trailing comment\n'
            "\n"
            + both('{ token = "$stack" }')
            + "\n[[keys.command]]\n"
            'command = "printf %s \\"$HOME\\" | pbcopy"\n'
        )
        self.assertEqual(self.colours()[0], 0)
        after = self.written()
        kept = [line for line in original.split("\n") if "$stack" not in line]
        remaining = after.split("\n")
        for line in kept:
            self.assertIn(line, remaining, "a line outside the $stack entry changed")
            remaining = remaining[remaining.index(line) + 1:]

    # -- idempotency -------------------------------------------------------

    def test_a_second_run_changes_nothing_and_says_nothing(self):
        self.given(both('{ token = "$stack" }'))
        self.assertEqual(self.colours()[0], 0)
        first = self.written()
        support.write(self.calls)
        code, log = self.colours()
        self.assertEqual(code, 0)
        self.assertEqual(log, "")
        self.assertEqual(self.written(), first)
        self.assertEqual(support.calls(self.calls), [], "a second run still called herdr")

    # -- the icon set decides ----------------------------------------------

    def test_emoji_removes_the_rules_the_plugin_wrote(self):
        original = self.given(both('{ token = "$stack" }'))
        self.assertEqual(self.colours()[0], 0)
        self.assertNotEqual(self.written(), original)
        support.plugin_config(self.plugin, icons="emoji")
        code, log = self.colours()
        self.assertEqual(code, 0)
        self.assertEqual(rules_of(self.written()), [])
        self.assertEqual(self.written(), original)
        self.assertIn("removed the $stack colour rules", log)

    def test_emoji_keeps_rules_the_plugin_did_not_write(self):
        original = self.given(
            both('{ token = "$stack", rules = [ { equals = "x", fg = "#010203" } ] }'),
            icons="emoji",
        )
        code, log = self.colours()
        self.assertEqual(code, 0)
        self.assert_untouched(original)
        self.assertIn("did not write", log)

    def test_emoji_on_a_config_that_never_had_rules_does_nothing(self):
        original = self.given(both('{ token = "$stack" }'), icons="emoji")
        code, log = self.colours()
        self.assertEqual(code, 0)
        self.assertEqual(log, "")
        self.assert_untouched(original)

    # -- nothing to colour --------------------------------------------------

    def test_a_config_without_the_token_is_left_alone(self):
        original = self.given(panel("spaces", '"workspace"') + panel("agents", '"agent"'))
        code, log = self.colours()
        self.assertEqual(code, 0)
        self.assert_untouched(original)
        self.assertIn("$stack", log)
        self.assertIn("ui.sidebar.spaces", log)
        self.assertEqual(len(log.strip().split("\n")), 1, "more than one line about it")
        self.assertEqual(support.calls(self.calls), [])

    def test_an_empty_config_is_left_alone(self):
        original = self.given("")
        self.assertEqual(self.colours()[0], 0)
        self.assert_untouched(original)

    # -- refusing to guess ---------------------------------------------------

    def test_a_config_the_patcher_cannot_read_is_left_alone(self):
        original = self.given('[ui.sidebar.spaces]\nrows = ["a\n')
        code, log = self.colours()
        self.assertEqual(code, 1)
        self.assert_untouched(original)
        self.assertIn("leaving the file alone", log)
        self.assertEqual(support.calls(self.calls), [])

    def test_a_rejected_result_leaves_the_original_untouched(self):
        original = self.given(both('{ token = "$stack" }'))
        code, log = self.colours(CHECK_EXIT="1")
        self.assertEqual(code, 1)
        self.assert_untouched(original)
        self.assertIn("rejected", log)
        self.assertIn("rejected by the stub", log)
        self.assertNotIn("server reload-config", support.calls(self.calls))

    def test_a_rejected_result_leaves_no_temporary_file_behind(self):
        self.given(both('{ token = "$stack" }'))
        self.colours(CHECK_EXIT="1")
        leftovers = [name for name in os.listdir(self.work) if "stack-icon" in name]
        self.assertEqual(leftovers, [])

    # -- how it is written ----------------------------------------------------

    def test_the_check_reads_a_copy_and_never_the_live_config(self):
        self.given(both('{ token = "$stack" }'))
        self.assertEqual(self.colours()[0], 0)
        checks = [line for line in support.calls(self.calls) if line.startswith("config check ")]
        self.assertEqual(len(checks), 1)
        checked = checks[0].split(" ", 2)[2]
        self.assertNotEqual(checked, self.path)
        self.assertEqual(os.path.dirname(checked), os.path.dirname(self.path))
        self.assertFalse(os.path.exists(checked), "the copy was left behind")

    def test_the_config_as_it_was_is_kept(self):
        original = self.given(both('{ token = "$stack" }'))
        self.assertEqual(self.colours()[0], 0)
        kept = self.backups()
        self.assertEqual(len(kept), 1)
        with open(os.path.join(self.state, kept[0]), "r", encoding="utf-8") as handle:
            self.assertEqual(handle.read(), original)

    def test_the_file_keeps_the_mode_it_had(self):
        """The copy is what ends up in place, so a config only its owner may read
        must not come back world readable."""
        self.given(both('{ token = "$stack" }'))
        os.chmod(self.path, 0o600)
        self.assertEqual(self.colours()[0], 0)
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)

    def test_a_write_reloads_the_server(self):
        self.given(both('{ token = "$stack" }'))
        self.assertEqual(self.colours()[0], 0)
        self.assertIn("server reload-config", support.calls(self.calls))

    # -- the opt-out ------------------------------------------------------------

    def test_off_never_touches_herdr_config(self):
        original = self.given(both('{ token = "$stack" }'), colours="off")
        code, log = self.colours()
        self.assertEqual(code, 0)
        self.assertEqual(log, "")
        self.assert_untouched(original)
        self.assertEqual(support.calls(self.calls), [])
        self.assertEqual(self.backups(), [])

    def test_an_unknown_colours_value_keeps_the_default(self):
        self.given(both('{ token = "$stack" }'), colours="maybe")
        code, log = self.colours()
        self.assertEqual(code, 0)
        self.assertIn('colours = "maybe"', log)
        self.assert_full_palette(self.written())

    # -- a real config ------------------------------------------------------------

    def test_the_user_config_holds_the_rules_the_plugin_writes(self):
        """The palette was written into this config by hand before the plugin
        could do it. The plugin has to recognise its own work and leave the file
        exactly as it is."""
        original = self.given_user_config()
        code, log = self.colours()
        self.assertEqual(code, 0)
        self.assertEqual(log, "")
        self.assert_untouched(original)
        self.assertEqual(support.calls(self.calls), [])

    def test_the_user_config_survives_a_round_trip_through_emoji(self):
        original = self.given_user_config()
        support.plugin_config(self.plugin, icons="emoji")
        self.assertEqual(self.colours()[0], 0)
        stripped = self.written()
        self.assertEqual(rules_of(stripped).count(("\\ue711", "#7c7c82")), 0)
        self.assertEqual(stripped.count(TOKEN_ENTRY), 2)
        self.assertIn('{ token = "$pr_emoji", rules = [', stripped, "another token lost its rules")
        support.plugin_config(self.plugin, icons="nerd")
        self.assertEqual(self.colours()[0], 0)
        self.assertEqual(self.written(), original, "the round trip did not come back")


if __name__ == "__main__":
    unittest.main()
