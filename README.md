# herdr-stack-icon

[Herdr](https://herdr.dev) plugin: a technology icon next to every workspace in the
sidebar, detected from the repository's files. Display only — nothing is renamed.

    🍏 les-gardiens        🤖 sundae-android        🍏🤖 shared-kmp
    🦀 ripgrep             🐹 gcai-go               🟩 sf-symbols-mcp        🐍 mobile-broom

## Install

    herdr plugin install bonkey/herdr-stack-icon

Requires herdr ≥ 0.8, Python 3.9 or newer (macOS Command Line Tools include it) and git.
The standard library is enough; there is nothing to install.

Then render the token in `config.toml` — the plugin only reports a value; add
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

## Detection

Markers are searched down to depth 3, first from the workspace's own folder,
then from the repository root (`git rev-parse --show-toplevel`, so a linked worktree is
detected like its main checkout). A workspace opened in `packages/SwiftThing/` with its own
`Package.swift` is 🍏 even if the repository root says otherwise.

A marker in the folder itself decides alone: a documentation repository with its own
`pyproject.toml` is 🐍 even when a sub-app one level down has `package.json`. Markers
further down decide only when the folder itself holds none, so a monorepo opened at its
root with `ios/App/Foo.xcodeproj` and `backend/package.json` counts as iOS. Further down,
`package.json` needs a lock file next to it (`package-lock.json`, `npm-shrinkwrap.json`,
`yarn.lock`, `pnpm-lock.yaml`, `bun.lock[b]`), so a repository that uses npm for tooling
keeps the icon of its own stack.

Dot-directories (`.git`, `.build`, `.venv`,
`.opencode`, ...), `node_modules`, `Pods`, `DerivedData`, `Carthage`, `vendor`, `target`,
`build` and `dist` are skipped; the scan takes a few milliseconds. iOS and Android together
are the KMP case at any depth; otherwise the first match wins within the deciding tier:

| Marker | Icon |
|---|---|
| entry in `overrides.toml` (below) | as configured |
| iOS/macOS **and** Android markers both present (KMP etc.) | 🍏🤖 |
| `*.xcodeproj`, `*.xcworkspace`, `Package.swift`, `Podfile` | 🍏 |
| `settings.gradle[.kts]`, `build.gradle[.kts]` | 🤖 |
| `Cargo.toml` | 🦀 |
| `go.mod` | 🐹 |
| `package.json` | 🟩 |
| `pyproject.toml`, `requirements.txt` | 🐍 |
| nothing | token cleared, no placeholder |

## Overrides

`$(herdr plugin config-dir bonkey.stack-icon)/overrides.toml`, one entry per line, first
match wins. The key is a repository name (the main checkout's directory, also for linked
worktrees), a checkout directory name, or a path glob; `~/` is expanded. An empty icon hides
the token. A file with a line that does not parse is ignored as a whole, with a message in
`herdr plugin log --plugin bonkey.stack-icon`.

    "my-kmp-app" = "🤖"            # detection says 🍏🤖, you want 🤖
    "~/Projects/League/*" = "🏒"
    "dotfiles" = ""

See `overrides.example.toml`.

## When it runs

Event hooks: `worktree.created`, `worktree.opened`, `workspace.created`, `workspace.focused`,
`pane.created` and `pane.focused`. Agent rows read pane metadata, so every pane is detected
from its own folder: a pane that works in another repository shows that repository's icon
and leaves its siblings alone. The Space row follows the focused pane, or the workspace's
folder while no pane is focused. Detection is a handful of file existence tests; there is no
cache.

A token lives only in the running server. The `[[startup]]` hook therefore reports every
workspace herdr holds before it does anything else, and again whenever the socket closes;
without that, a Space row stays empty after a restart until its workspace is focused.

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

Manual re-scan of the focused workspace, also in the workspace right-click menu:

    herdr plugin action invoke bonkey.stack-icon.refresh

## Development

    git clone https://github.com/bonkey/herdr-stack-icon
    herdr plugin link "$PWD/herdr-stack-icon"

The script is re-read on every run; relink after editing `herdr-plugin.toml`. Check detection
for any path without herdr:

    python3 stack-icon.py --detect ~/Projects/some-repo
    python3 stack-icon.py --explain ~/Projects/some-repo  # root, markers found, resulting icon
    python3 stack-icon.py --all                           # report every workspace, then exit
    python3 stack-icon.py --watch &                       # the startup hook, by hand

Tests need neither herdr nor a network. `test_detect.py` runs the rules against folder
fixtures, `test_report.py` runs the event path against a stub herdr and checks what is
published on the workspace and on each pane, and `test_watch.py` runs the watcher against a
herdr socket the test itself serves:

    python3 -m unittest discover -s test

`herdr server reload-config` and plugin link/enable do not run startup hooks; the watcher
started by hand stays until the next herdr server start replaces it. A workspace keeps the
icon it was given until its next `workspace.focused` or a `cd` in one of its panes; after
updating the plugin, run `python3 stack-icon.py --all`, restart herdr, or focus the workspace.

## License

MIT
