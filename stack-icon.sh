#!/usr/bin/env bash
# Detect the technology stack of a herdr workspace's repository and report it as
# the `stack` sidebar token on the workspace (Space rows) and on each of its
# panes (Agent rows). Display only: nothing is renamed.
#
#   bash stack-icon.sh                  run from a herdr event or action (reads HERDR_* env)
#   bash stack-icon.sh --detect <path>  print the icon for a path and exit; no herdr calls
#   bash stack-icon.sh --explain <path> show root, markers found and the resulting icon
#
# Rules, first match wins, markers searched down to depth 3 from the workspace folder,
# then from the repository root:
#   overrides.toml entry               (see override below)
#   iOS/macOS and Android both present 🍏🤖
#   *.xcodeproj *.xcworkspace Package.swift Podfile              🍏
#   settings.gradle[.kts] build.gradle[.kts]                     🤖
#   Cargo.toml 🦀   go.mod 🐹   package.json 🟩   pyproject.toml / requirements.txt 🐍
#   nothing matched: the token is cleared, never a placeholder.
set -u

SOURCE="bonkey.stack-icon"
HERDR="${HERDR_BIN_PATH:-herdr}"

log() { printf 'stack-icon: %s\n' "$*" >&2; }

# First "key":"value" string in a JSON blob. Enough for herdr's context JSON;
# a path containing a double quote is not supported.
json_str() {
  printf '%s' "$1" | grep -o "\"$2\":\"[^\"]*\"" | head -n1 | cut -d'"' -f4 | sed 's#\\/#/#g'
}

trim() { printf '%s' "$1" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'; }

# Repository root for a directory; works inside linked worktrees. Falls back to
# the directory itself when it is not a git checkout.
repo_root() {
  local root
  root=$(git -C "$1" rev-parse --show-toplevel 2>/dev/null)
  if [ -n "$root" ]; then printf '%s\n' "$root"; else printf '%s\n' "$1"; fi
}

# Name of the repository a checkout belongs to: the main checkout's directory,
# also for linked worktrees (so "les-gardiens" for les-gardiens.feature-x).
repo_name() {
  local common
  common=$(git -C "$1" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
  case $common in
    "") basename "$1" ;;
    */.git) basename "$(dirname "$common")" ;;
    *) basename "$common" ;;
  esac
}

# overrides.toml in the plugin config dir (`herdr plugin config-dir bonkey.stack-icon`):
#   one `key = "icon"` per line, key = repository name, checkout directory name,
#   or a path glob (`~/` allowed). An empty icon hides the token. A file with an
#   unparsable line is ignored whole.
# Prints the icon and returns 0 on a match, returns 1 otherwise.
override() {
  local root=$1 dir="${HERDR_PLUGIN_CONFIG_DIR:-}" file line key val name checkout
  [ -n "$dir" ] || dir=$("$HERDR" plugin config-dir "$SOURCE" 2>/dev/null)
  file="$dir/overrides.toml"
  [ -f "$file" ] || return 1
  name=$(repo_name "$root")
  checkout=$(basename "$root")
  while IFS= read -r line || [ -n "$line" ]; do
    case $line in '' | '#'*) continue ;; esac
    if ! printf '%s' "$line" | grep -Eq '^[[:space:]]*("[^"]+"|[A-Za-z0-9_.~/*?-]+)[[:space:]]*=[[:space:]]*"[^"]*"[[:space:]]*(#.*)?$'; then
      log "ignoring $file: cannot parse line: $line"
      return 1
    fi
  done <"$file"
  while IFS= read -r line || [ -n "$line" ]; do
    case $line in '' | '#'*) continue ;; esac
    key=$(trim "${line%%=*}")
    key=${key#\"}
    key=${key%\"}
    val=${line#*=}
    val=${val#*\"}
    val=${val%%\"*}
    # shellcheck disable=SC2088
    case $key in "~/"*) key="$HOME/${key#"~/"}" ;; esac
    # shellcheck disable=SC2254
    case $name in $key) printf '%s\n' "$val"; return 0 ;; esac
    # shellcheck disable=SC2254
    case $checkout in $key) printf '%s\n' "$val"; return 0 ;; esac
    # shellcheck disable=SC2254
    case $root in $key) printf '%s\n' "$val"; return 0 ;; esac
  done <"$file"
  return 1
}

# Marker files under a directory, down to depth 3. Dot-directories (.git,
# .opencode, .build, .venv, ...) and dependency or build folders are skipped.
markers() {
  find "$1" -mindepth 1 -maxdepth 3 \
    \( -type d \( -name '.*' -o -name node_modules -o -name Pods -o -name DerivedData -o -name Carthage \
       -o -name vendor -o -name target -o -name build -o -name dist \) \) -prune -o \
    \( -name '*.xcodeproj' -o -name '*.xcworkspace' -o -name Package.swift -o -name Podfile \
       -o -name settings.gradle -o -name settings.gradle.kts -o -name build.gradle -o -name build.gradle.kts \
       -o -name Cargo.toml -o -name go.mod -o -name package.json -o -name pyproject.toml -o -name requirements.txt \) \
    -print 2>/dev/null
}

# Markers are searched from the repository root down to depth 3 (a monorepo
# with ios/App/Foo.xcodeproj and backend/), skipping dependency and build folders.
detect() {
  local root=$1 ios=0 android=0 rust=0 go=0 node=0 py=0 f
  while IFS= read -r f; do
    case ${f##*/} in
      *.xcodeproj | *.xcworkspace | Package.swift | Podfile) ios=1 ;;
      settings.gradle | settings.gradle.kts | build.gradle | build.gradle.kts) android=1 ;;
      Cargo.toml) rust=1 ;;
      go.mod) go=1 ;;
      package.json) node=1 ;;
      pyproject.toml | requirements.txt) py=1 ;;
    esac
  done < <(markers "$root")
  if [ "$ios" = 1 ] && [ "$android" = 1 ]; then printf '🍏🤖\n'; return 0; fi
  if [ "$ios" = 1 ]; then printf '🍏\n'; return 0; fi
  if [ "$android" = 1 ]; then printf '🤖\n'; return 0; fi
  if [ "$rust" = 1 ]; then printf '🦀\n'; return 0; fi
  if [ "$go" = 1 ]; then printf '🐹\n'; return 0; fi
  if [ "$node" = 1 ]; then printf '🟩\n'; return 0; fi
  if [ "$py" = 1 ]; then printf '🐍\n'; fi
  return 0
}

# The workspace's own folder is checked before the repository root, so a
# workspace opened in a package inside a larger repo shows that package's stack.
icon_for() {
  local cwd=$1 root icon
  root=$(repo_root "$cwd")
  if icon=$(override "$root"); then :; else
    icon=""
    [ "$cwd" != "$root" ] && icon=$(detect "$cwd")
    [ -n "$icon" ] || icon=$(detect "$root")
  fi
  printf '%s\n' "$icon"
}

# report <workspace|pane> <id> <icon>
report() {
  if [ -n "$3" ]; then
    "$HERDR" "$1" report-metadata "$2" --source "$SOURCE" --token "stack=$3" >/dev/null
  else
    "$HERDR" "$1" report-metadata "$2" --source "$SOURCE" --clear-token stack >/dev/null
  fi
}

main() {
  local ws cwd icon pane rc=0
  if [ "${1:-}" = "--detect" ]; then
    icon_for "${2:?usage: stack-icon.sh --detect <path>}"
    return 0
  fi
  if [ "${1:-}" = "--explain" ]; then
    cwd=${2:?usage: stack-icon.sh --explain <path>}
    local root
    root=$(repo_root "$cwd")
    printf 'folder:    %s\nrepo root: %s\nrepo name: %s\n' "$cwd" "$root" "$(repo_name "$root")"
    printf 'override:  %s\n' "$(override "$root" || printf '(none)')"
    printf 'markers under folder:\n'; markers "$cwd" | sed "s#^$cwd/#  #"
    [ "$cwd" != "$root" ] && { printf 'markers under repo root:\n'; markers "$root" | sed "s#^$root/#  #"; }
    printf 'icon:      [%s]\n' "$(icon_for "$cwd")"
    return 0
  fi

  ws=${HERDR_WORKSPACE_ID:-}
  [ -n "$ws" ] || ws=$(json_str "${HERDR_PLUGIN_CONTEXT_JSON:-}" workspace_id)
  if [ -z "$ws" ]; then
    log "no workspace in context"
    return 1
  fi
  cwd=$(json_str "${HERDR_PLUGIN_CONTEXT_JSON:-}" workspace_cwd)
  [ -n "$cwd" ] || cwd=$("$HERDR" pane list --workspace "$ws" 2>/dev/null | grep -o '"cwd":"[^"]*"' | head -n1 | cut -d'"' -f4)
  if [ -d "$cwd" ]; then
    icon=$(icon_for "$cwd")
  else
    icon=""
  fi
  # One line per run in `herdr plugin log --plugin bonkey.stack-icon`.
  log "${HERDR_PLUGIN_EVENT:-${HERDR_PLUGIN_ACTION_ID:-run}} $ws cwd=$cwd root=$(repo_root "$cwd") icon=[$icon] plugin=$HERDR_PLUGIN_ROOT"

  report workspace "$ws" "$icon" || { log "workspace $ws: report-metadata failed"; rc=1; }
  for pane in $("$HERDR" pane list --workspace "$ws" 2>/dev/null | grep -o '"pane_id":"[^"]*"' | cut -d'"' -f4); do
    report pane "$pane" "$icon" || { log "pane $pane: report-metadata failed"; rc=1; }
  done
  return $rc
}

main "$@"
