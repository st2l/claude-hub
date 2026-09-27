#!/usr/bin/env bash
# install.sh — one-line installer for claude-hub.
#   curl -fsSL https://raw.githubusercontent.com/st2l/claude-hub/main/install.sh | bash
set -euo pipefail

REPO="https://github.com/st2l/claude-hub.git"
DEST="${HOME}/.local/share/claude-hub"
BIN_DIR="${HOME}/.local/bin"
BIN="${BIN_DIR}/claude-hub"

say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; }

command -v python3 >/dev/null 2>&1 || { err "python3 required"; exit 1; }
command -v git >/dev/null 2>&1     || { err "git required"; exit 1; }

mkdir -p "$BIN_DIR"

if [ -d "$DEST/.git" ]; then
  say "Updating existing clone at $DEST"
  git -C "$DEST" fetch --depth 1 origin main
  git -C "$DEST" reset --hard origin/main
else
  say "Cloning into $DEST"
  rm -rf "$DEST.tmp"
  git clone --depth 1 "$REPO" "$DEST.tmp"
  rm -rf "$DEST"
  mv "$DEST.tmp" "$DEST"
fi

say "Installing launcher at $BIN"
cat > "$BIN" <<'LAUNCHER'
#!/usr/bin/env bash
export PYTHONPATH="$HOME/.local/share/claude-hub${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m claude_hub "$@"
LAUNCHER
chmod +x "$BIN"

say "Wiring the statusline into Claude Code"
PYTHONPATH="$DEST${PYTHONPATH:+:$PYTHONPATH}" python3 -m claude_hub.integration || \
  err "statusline not registered, run 'claude-hub -s on' later"

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) say "NOTE: $BIN_DIR is not in PATH — add 'export PATH=\"\$HOME/.local/bin:\$PATH\"' to your rc" ;;
esac

echo
say "Done! Run: claude-hub"
say "Add a provider on the Providers tab, then press L to launch."
say "Later: 'claude-hub -u' updates this install in place."
