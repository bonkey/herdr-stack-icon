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
root with `ios/App/Foo.xcodeproj` and `backend/package.json` counts as iOS. `.git`, `node_modules`, `Pods`, `.build`,
`DerivedData`, `Carthage`, `vendor`, `.venv`, `target`, `build` and `dist` are skipped; the
scan takes a few milliseconds. First match wins:

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

`worktree.created`, `worktree.opened`, `workspace.created`, `workspace.focused` and
`pane.focused` (Agent rows read pane metadata, so a pane opened later gets the icon when it is
first focused). Detection is a handful of file existence tests; there is no cache.

Manual re-scan of the focused workspace, also in the workspace right-click menu:

    herdr plugin action invoke bonkey.stack-icon.refresh

## Development

    git clone https://github.com/bonkey/herdr-stack-icon
    herdr plugin link "$PWD/herdr-stack-icon"

The script is re-read on every run; relink after editing `herdr-plugin.toml`. Check detection
for any path without herdr:

    bash stack-icon.sh --detect ~/Projects/some-repo

## License

MIT
