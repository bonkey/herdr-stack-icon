#!/usr/bin/env bash
# Detect the technology stack of a herdr workspace's repository and report it as
# the `stack` sidebar token on the workspace (Space rows) and on each of its
# panes (Agent rows). Display only: nothing is renamed.
#
#   bash stack-icon.sh                  run from a herdr event or action (reads HERDR_* env)
#   bash stack-icon.sh --detect <path>  print the icon for a path and exit; no herdr calls
#
# Rules, first match wins, evaluated at the repository root:
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

detect() {
  local root=$1 ios=0 android=0 f
  for f in Package.swift Podfile; do [ -e "$root/$f" ] && ios=1; done
  for f in "$root"/*.xcodeproj "$root"/*.xcworkspace; do [ -e "$f" ] && ios=1; done
  for f in settings.gradle settings.gradle.kts build.gradle build.gradle.kts; do [ -e "$root/$f" ] && android=1; done
  if [ "$ios" = 1 ] && [ "$android" = 1 ]; then printf '🍏🤖\n'; return 0; fi
  if [ "$ios" = 1 ]; then printf '🍏\n'; return 0; fi
  if [ "$android" = 1 ]; then printf '🤖\n'; return 0; fi
  [ -e "$root/Cargo.toml" ] && { printf '🦀\n'; return 0; }
  [ -e "$root/go.mod" ] && { printf '🐹\n'; return 0; }
  [ -e "$root/package.json" ] && { printf '🟩\n'; return 0; }
  if [ -e "$root/pyproject.toml" ] || [ -e "$root/requirements.txt" ]; then printf '🐍\n'; fi
  return 0
}

icon_for() {
  local root icon
  root=$(repo_root "$1")
  if icon=$(override "$root"); then :; else icon=$(detect "$root"); fi
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

  report workspace "$ws" "$icon" || { log "workspace $ws: report-metadata failed"; rc=1; }
  for pane in $("$HERDR" pane list --workspace "$ws" 2>/dev/null | grep -o '"pane_id":"[^"]*"' | cut -d'"' -f4); do
    report pane "$pane" "$icon" || { log "pane $pane: report-metadata failed"; rc=1; }
  done
  return $rc
}

main "$@"
