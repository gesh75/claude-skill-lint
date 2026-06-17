#!/usr/bin/env bash
# install.sh — install claude-skill-lint as a `skill-lint` command.
#
# Usage:
#   ./install.sh                 # install the latest release to ~/.local/bin
#   VERSION=v0.1.0 ./install.sh  # pin a specific release tag (or "main")
#   BIN_DIR=/usr/local/bin ./install.sh
#
# It downloads a single file (skill_lint.py) from this repo — review it at
# https://github.com/gesh75/claude-skill-lint before running.
set -euo pipefail

REPO="gesh75/claude-skill-lint"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
CMD_NAME="skill-lint"

note() { printf '\033[36m==>\033[0m %s\n' "$*"; }
err()  { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }

# 1. Require Python 3.8+
command -v python3 >/dev/null 2>&1 || err "python3 is required but not found."
python3 - <<'PY' || err "Python 3.8+ is required."
import sys
sys.exit(0 if sys.version_info >= (3, 8) else 1)
PY

# 2. Resolve the version to install (latest release unless VERSION is set).
resolve_latest() {
  curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" 2>/dev/null \
    | grep -m1 '"tag_name"' \
    | sed -E 's/.*"tag_name"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/'
}
REF="${VERSION:-$(resolve_latest || true)}"
REF="${REF:-main}"
note "Installing claude-skill-lint ($REF)"

# 3. Download the single-file tool.
URL="https://raw.githubusercontent.com/$REPO/$REF/skill_lint.py"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
curl -fsSL "$URL" -o "$TMP" || err "download failed: $URL"
head -1 "$TMP" | grep -q '^#!/usr/bin/env python3' || err "downloaded file does not look like skill_lint.py"

# 4. Install.
mkdir -p "$BIN_DIR"
install -m 0755 "$TMP" "$BIN_DIR/$CMD_NAME"
note "Installed to $BIN_DIR/$CMD_NAME"

# 5. PATH guidance + smoke test.
if ! printf '%s' ":$PATH:" | grep -q ":$BIN_DIR:"; then
  note "Add $BIN_DIR to your PATH, e.g.:"
  printf '    echo '\''export PATH="%s:$PATH"'\'' >> ~/.zshrc\n' "$BIN_DIR"
fi
"$BIN_DIR/$CMD_NAME" --help >/dev/null 2>&1 || python3 "$BIN_DIR/$CMD_NAME" --help >/dev/null
note "Done. Run: $CMD_NAME ~/.claude/skills"
