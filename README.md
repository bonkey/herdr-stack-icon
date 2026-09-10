# herdr-stack-icon

[Herdr](https://herdr.dev) plugin: a technology icon next to every workspace in the
sidebar, detected from the repository's files. Display only — nothing is renamed.

     les-gardiens          sundae-android          shared-kmp
     ripgrep               gcai-go                 sf-symbols-mcp          mobile-broom

Nerd Font glyphs are the default; [emoji](#icon-set) are one setting away, and
[each technology gets its own colour](#colour) without anything to copy.

    🍏 les-gardiens        🤖 sundae-android        🍏🤖 shared-kmp
    🦀 ripgrep             🐹 gcai-go               🟩 sf-symbols-mcp        🐍 mobile-broom

## Install

    herdr plugin install bonkey/herdr-stack-icon

Requires herdr ≥ 0.8, Python 3.9 or newer (macOS Command Line Tools include it) and git.
The standard library is enough; there is nothing to install. The default icons need a
Nerd Font in the terminal; [emoji](#icon-set) need none.

Then render the token in herdr's `config.toml` — the plugin only reports a value; add
`{ token = "$stack" }` where you want it in both sidebar panels:

    [ui.sidebar.spaces]
    rows = [
      ["state_icon", { token = "$stack" }, "workspace"],
      ["branch", "git_status"],
    ]

    [ui.sidebar.agents]
    rows = [
      ["state_icon", { token = "$stack" }, "workspace", "tab"],
      ["agent"],
    ]

and `herdr server reload-config`. Every workspace gets its icon the next time the herdr
server starts; before that, a workspace gets it the first time it is focused.

That is the whole of it. The [colour](#colour) of each glyph is the plugin's own
business: it writes the `rules` onto the `$stack` entries above the next time the herdr
server starts, and again whenever you change the icon set.

## Detection

Markers are searched down to depth 3, first from the workspace's own folder,
then from the repository root (`git rev-parse --show-toplevel`, so a linked worktree is
detected like its main checkout). A workspace opened in `packages/SwiftThing/` with its own
`Package.swift` is iOS/macOS even if the repository root says otherwise.

A folder outside a git checkout gets no icon at all. A home directory that holds somebody's
demo three folders down is not that demo, and a pane sitting in `~` should show nothing. An
`overrides.toml` entry still decides, there as everywhere.

A marker in the folder itself decides alone: a documentation repository with its own
`pyproject.toml` is Python even when a sub-app one level down has `package.json`. Markers
further down decide only when the folder itself holds none, so a monorepo opened at its
root with `ios/App/Foo.xcodeproj` and `backend/package.json` counts as iOS. Further down,
`package.json` needs a lock file next to it (`package-lock.json`, `npm-shrinkwrap.json`,
`yarn.lock`, `pnpm-lock.yaml`, `bun.lock[b]`), so a repository that uses npm for tooling
keeps the icon of its own stack.

Dot-directories (`.git`, `.build`, `.venv`,
`.opencode`, ...), `node_modules`, `Pods`, `DerivedData`, `Carthage`, `vendor`, `target`,
`build` and `dist` are skipped; the scan takes a few milliseconds. iOS and Android together
are the KMP case at any depth; otherwise the first match wins within the deciding tier:

| Marker | Nerd Font | Emoji |
|---|---|---|
| entry in `overrides.toml` (below) | as configured | as configured |
| iOS/macOS **and** Android markers both present (KMP etc.) |  `U+E711` + `U+E70E` | 🍏🤖 |
| `*.xcodeproj`, `*.xcworkspace`, `Package.swift`, `Podfile` |  `U+E711` `nf-dev-apple` | 🍏 |
| `settings.gradle[.kts]`, `build.gradle[.kts]` |  `U+E70E` `nf-dev-android` | 🤖 |
| `Cargo.toml` |  `U+E7A8` `nf-dev-rust` | 🦀 |
| `go.mod` |  `U+E724` `nf-dev-go` | 🐹 |
| `package.json` |  `U+E718` `nf-dev-nodejs_small` | 🟩 |
| `pyproject.toml`, `requirements.txt` |  `U+E73C` `nf-dev-python` | 🐍 |
| nothing | token cleared, no placeholder | token cleared, no placeholder |

## Icon set

Nerd Font glyphs are the default. They are Devicons in the private use area, so the
terminal needs a [Nerd Font](https://www.nerdfonts.com); with any other font every
one of them is a replacement box (`▯`). All six sit in `U+E700`–`U+E7C5`, which Nerd
Fonts v3 left where v2 had it, so a v2 font shows the same icons.

Emoji are the alternative. Pick the set in
`$(herdr plugin config-dir bonkey.stack-icon)/config.toml`:

    icons = "emoji"     # "nerd" (the default) or "emoji"

The file is read on every run, so the setting reaches the event hooks, the startup
watcher, the `refresh` action and `python3 stack-icon.py --detect` alike; no reload
and no restart. An unknown name keeps the default and writes a line to
`herdr plugin log --plugin bonkey.stack-icon`. The same file holds
[`colours`](#opting-out). See `config.example.toml`.

Emoji need no [colour rules](#colour), so choosing them also removes the ones the plugin
wrote; the next `herdr server` start, or `python3 stack-icon.py --colours`, does it.

## Colour

A Nerd Font glyph is monochrome: it takes the colour of the row it sits in, so every icon
would be the same grey. The token cannot carry a colour either — herdr normalises reported
metadata, trimming the value, removing control characters and capping it at 80 characters,
so an ANSI escape arrives without its `ESC` and prints the rest as text. The colour lives in
herdr's own `config.toml` instead: a token entry there accepts up to 16 ordered `rules`,
each one matching the token's value and setting a style. One rule per icon gives every
technology its own colour.

The plugin owns the palette, so it writes those rules itself. Install it, restart herdr, and
the icons are coloured; there is no block to paste, and nothing to keep in step by hand when
the plugin learns a new glyph.

| Stack | Colour | |
|---|---|---|
| iOS/macOS | `#7c7c82` | silver |
| Android | `#0d9152` | Android green |
| Rust | `#c2571a` | rust |
| Go | `#0087a8` | gopher cyan |
| Node | `#4c8f3a` | leaf green |
| Python | `#3d7fbf` | python blue |
| iOS **and** Android (KMP) | `#9061e8` | Kotlin purple |

The colours are the technologies' own, darkened to mid-tone, so each one keeps a contrast of
at least 3:1 on a white, a black, a Catppuccin Mocha, a One Dark and a Solarized Light
background. `equals` is exact, so the two-glyph KMP value gets a rule of its own and the
order is for reading only.

### When the rules are written

The `[[startup]]` hook writes them once before it starts watching, so a herdr restart is all
the integration there is. To write them again after changing the icon set or editing them by
hand, use the workspace right-click menu (**Update stack icon colours**), or:

    herdr plugin action invoke bonkey.stack-icon.colours
    python3 stack-icon.py --colours     # the same thing, without herdr's menu

A run that has nothing to change writes nothing, reloads nothing and logs nothing.

### What it writes

Every `$stack` entry in `ui.sidebar.*.rows` is styled on its own, in one panel or in both:

| in `config.toml` | what happens |
|---|---|
| `{ token = "$stack" }` | gains the `rules` |
| `"$stack"`, a bare string | becomes an entry, with the `rules` on it |
| an entry that already carries `rules` | they are replaced |
| `{ token = "$stack", fg = "#888", bold = true }` | `fg`, `bold` and `dim` stay, `rules` is added |
| no `$stack` in any sidebar row | nothing is written; one line in the log says what to add |
| `icons = "emoji"` | the rules the plugin wrote are removed again |

`fg`, `bold` and `dim` on the entry style every value that no rule matches, which is the
entry's own business, so they are kept and `rules` is written after them. With
[emoji](#icon-set) only the plugin's own set of rules is removed: a hand-written set is
left where it is, with a line in the log. Anything outside the `$stack` entries — comments,
blank lines, other tokens, every other table — is left byte for byte as it was.

### That file is yours

A rule herdr rejects makes it fall back to the **default** sidebar, which drops every custom
row. So the plugin writes the result to a temporary file next to the config, runs
`HERDR_CONFIG_PATH=<temp> herdr config check` over it, and only moves it into place when the
check passes; a config it cannot read whole, it does not touch at all. The file as it was is
copied into the plugin state directory
(`~/.local/state/herdr/plugins/bonkey.stack-icon/config-<timestamp>-<pid>.toml`) before
anything is moved, and no earlier copy is ever overwritten. The move itself is atomic, and
the file keeps the mode it had. After a successful write the plugin runs
`herdr server reload-config`. The config is `HERDR_CONFIG_PATH` when it is set, else
`~/.config/herdr/config.toml`.

This is also what happens on herdr 0.8, which has no `rules`: the check refuses the result
and the config keeps the shape it had.

### Opting out

`colours = "off"` in `$(herdr plugin config-dir bonkey.stack-icon)/config.toml` stops the
plugin touching herdr's config at all. `"auto"` is the default. The icons then take the
colour of their row, unless you write the rules yourself.

### By hand

The block the plugin writes, for anyone on herdr 0.8 or with `colours = "off"`. A style
applies to the entry it is written on, so each panel needs its own copy:

    [ui.sidebar.spaces]
    rows = [
      ["state_icon", { token = "$stack", rules = [
        { equals = "\ue711\ue70e", fg = "#9061e8" },  # iOS and Android together (KMP)
        { equals = "\ue711", fg = "#7c7c82" },        # iOS/macOS
        { equals = "\ue70e", fg = "#0d9152" },        # Android
        { equals = "\ue7a8", fg = "#c2571a" },        # Rust
        { equals = "\ue724", fg = "#0087a8" },        # Go
        { equals = "\ue718", fg = "#4c8f3a" },        # Node
        { equals = "\ue73c", fg = "#3d7fbf" },        # Python
      ] }, "workspace"],
      ["branch", "git_status"],
    ]

    [ui.sidebar.agents]
    rows = [
      ["state_icon", { token = "$stack", rules = [
        { equals = "\ue711\ue70e", fg = "#9061e8" },  # iOS and Android together (KMP)
        { equals = "\ue711", fg = "#7c7c82" },        # iOS/macOS
        { equals = "\ue70e", fg = "#0d9152" },        # Android
        { equals = "\ue7a8", fg = "#c2571a" },        # Rust
        { equals = "\ue724", fg = "#0087a8" },        # Go
        { equals = "\ue718", fg = "#4c8f3a" },        # Node
        { equals = "\ue73c", fg = "#3d7fbf" },        # Python
      ] }, "workspace", "tab"],
      ["agent"],
    ]

Then `herdr config check`, then `herdr server reload-config`. `rules` need herdr 0.9 or
newer; 0.8 gives a token one fixed `fg`, the same colour for every technology. `\ue711` is
the TOML escape for the glyph the plugin reports, so the file needs no private-use character
to survive a copy; the codepoints are the ones in the [detection table](#detection). `fg`
takes a strict `#RGB` or `#RRGGBB` and nothing else: `cyan` and a 256-colour index are both
rejected, and a rule also accepts `bold` and `dim`.

[Emoji](#icon-set) carry their own colour and need no rules; `fg` does not repaint a colour
emoji. An [override](#overrides) is an arbitrary string, which matches none of the rules
above, so it keeps the row's colour until a rule with its exact text is added.

## Overrides

`$(herdr plugin config-dir bonkey.stack-icon)/overrides.toml`, one entry per line, first
match wins. The key is a repository name (the main checkout's directory, also for linked
worktrees), a checkout directory name, or a path glob; `~/` is expanded. The icon is any
string — an emoji, a Nerd Font glyph or a word — so an entry wins over both icon sets. An
empty icon hides the token. A file with a line that does not parse is ignored as a whole,
with a message in `herdr plugin log --plugin bonkey.stack-icon`.

    "my-kmp-app" = "🤖"            # detection shows both, you want Android alone
    "~/Projects/League/*" = "🏒"
    "dotfiles" = ""

See `overrides.example.toml`.

## When it runs

Event hooks: `worktree.created`, `worktree.opened`, `workspace.created`, `workspace.focused`,
`pane.created` and `pane.focused`. Agent rows read pane metadata, so every pane is detected
from its own folder: a pane that works in another repository shows that repository's icon
and leaves its siblings alone. The Space row follows the focused pane; while no pane of the
workspace is focused it shows the workspace's own checkout, not wherever an unfocused pane
wandered off to. Detection is a handful of file existence tests; there is no
cache.

A token lives only in the running server. The `[[startup]]` hook therefore reports every
workspace herdr holds before it does anything else, and again whenever the socket closes;
without that, a Space row stays empty after a restart until its workspace is focused. Before
the first report it brings the [colour rules](#colour) in `config.toml` in step with the icon
set, which is why installing the plugin and restarting herdr is the whole integration.

The same hook then follows `cd`. A `cd` in a pane emits `pane.updated`, which herdr does not
dispatch to event hooks, so the hook subscribes to it on the herdr socket: a pane that moves
into another repository gets the right icon at once, and the Space row follows when that pane
is focused. Only the event's pane is checked, and nothing is reported when that pane's own
token already matches, since a report itself emits `pane.updated`. Startup hooks run when the
herdr server starts, so after installing either restart herdr or start the watcher by hand
once: `python3 stack-icon.py --watch &` from the plugin directory. It replaces any earlier
instance (pid file), reconnects when the socket closes, and exits after three failed
subscriptions. Log: `watch.log` under the plugin state directory,
`~/.local/state/herdr/plugins/bonkey.stack-icon/`.

Manual re-scan of the focused workspace, and a manual rewrite of the colour rules; both are
in the workspace right-click menu too:

    herdr plugin action invoke bonkey.stack-icon.refresh
    herdr plugin action invoke bonkey.stack-icon.colours

## Development

    git clone https://github.com/bonkey/herdr-stack-icon
    herdr plugin link "$PWD/herdr-stack-icon"

The script is re-read on every run; relink after editing `herdr-plugin.toml`. Check detection
for any path without herdr:

    python3 stack-icon.py --detect ~/Projects/some-repo
    python3 stack-icon.py --explain ~/Projects/some-repo  # root, markers, icon set, resulting icon
    python3 stack-icon.py --all                           # report every workspace, then exit
    python3 stack-icon.py --colours                       # write the colour rules, then exit
    python3 stack-icon.py --watch &                       # the startup hook, by hand

`--colours` and `--watch` write to `HERDR_CONFIG_PATH`, or to `~/.config/herdr/config.toml`
when it is unset. Point it at a copy while working on the patcher.

Tests need neither herdr nor a network. `test_detect.py` runs the rules against folder
fixtures, `test_report.py` runs the event path against a stub herdr and checks what is
published on the workspace and on each pane, `test_watch.py` runs the watcher against a
herdr socket the test itself serves, `test_config_rules.py` runs the [colour](#colour)
patcher over every config shape, `test/fixtures/user-config.toml` included, and
`test_colours.py` holds the rules in this file against both the icons the plugin reports and
the rules it writes:

    python3 -m unittest discover -s test

`herdr server reload-config` and plugin link/enable do not run startup hooks; the watcher
started by hand stays until the next herdr server start replaces it. A workspace keeps the
icon it was given until its next `workspace.focused` or a `cd` in one of its panes; after
updating the plugin, run `python3 stack-icon.py --all`, restart herdr, or focus the workspace.

## License

MIT
