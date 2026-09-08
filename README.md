# herdr-stack-icon

[Herdr](https://herdr.dev) plugin: a technology icon next to every workspace in the
sidebar, detected from the repository's files. Display only — nothing is renamed.

    🍏 les-gardiens        🤖 sundae-android        🍏🤖 shared-kmp
    🦀 ripgrep             🐹 gcai-go               🟩 sf-symbols-mcp        🐍 mobile-broom

## Install

    herdr plugin install bonkey/herdr-stack-icon

Requires herdr ≥ 0.8, bash and git. No other runtime.

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

and `herdr server reload-config`. Workspaces that were open before the install get their
icon the first time they are focused.

## Detection

Markers are searched with `find` down to depth 3, first from the workspace's own folder,
then from the repository root (`git rev-parse --show-toplevel`, so a linked worktree is
detected like its main checkout). A workspace opened in `packages/SwiftThing/` with its own
`Package.swift` is 🍏 even if the repository root says otherwise; a monorepo opened at its
root with `ios/App/Foo.xcodeproj` and `backend/package.json` counts as iOS. Dot-directories (`.git`, `.build`, `.venv`,
`.opencode`, ...), `node_modules`, `Pods`, `DerivedData`, `Carthage`, `vendor`, `target`,
`build` and `dist` are skipped; the scan takes a few milliseconds. First match wins:

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
`pane.created` and `pane.focused` (Agent rows read pane metadata, so every pane gets its own
copy of the icon). Detection is a handful of file existence tests; there is no cache.

A `cd` in a pane emits `pane.updated`, which herdr does not dispatch to event hooks, so a
`[[startup]]` watcher subscribes to it on the herdr socket: a pane that moves into another
repository gets the right icon at once, and the Space row follows when that pane is
focused. Only the event's pane is checked, and nothing is reported when its token already
matches, since a report itself emits `pane.updated`. The watcher needs `nc -U` (macOS,
netcat-openbsd), `ncat` or `python3`; without one it logs and exits, and icons still refresh
on focus. Startup hooks run when the herdr server starts, so after installing either restart
herdr or start the watcher by hand once: `bash stack-icon.sh --watch &` from the plugin
directory. It replaces any earlier instance (pid file), reconnects when the socket closes, and
exits after three failed subscriptions. Log: `watch.log` under the plugin state directory,
`~/.local/state/herdr/plugins/bonkey.stack-icon/`.

Manual re-scan of the focused workspace, also in the workspace right-click menu:

    herdr plugin action invoke bonkey.stack-icon.refresh

## Development

    git clone https://github.com/bonkey/herdr-stack-icon
    herdr plugin link "$PWD/herdr-stack-icon"

The script is re-read on every run; relink after editing `herdr-plugin.toml`. Check detection
for any path without herdr:

    bash stack-icon.sh --detect ~/Projects/some-repo
    bash stack-icon.sh --explain ~/Projects/some-repo   # root, markers found, resulting icon
    bash stack-icon.sh --watch &                         # the startup watcher, by hand

`herdr server reload-config` and plugin link/enable do not run startup hooks; the watcher
started by hand stays until the next herdr server start replaces it. A workspace keeps the
icon it was given until its next `workspace.focused` or a `cd` in one of its panes; after
updating the plugin, focus the workspace once or run the refresh action.

## License

MIT
