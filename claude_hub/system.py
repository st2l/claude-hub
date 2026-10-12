"""Platform differences: config location, key-file permissions, console glyphs."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

IS_WINDOWS = os.name == "nt"


def config_dir() -> Path:
    """Per-user config directory: %APPDATA% on Windows, ~/.config elsewhere."""
    if IS_WINDOWS:
        roaming = os.environ.get("APPDATA")
        base = Path(roaming) if roaming else Path.home() / "AppData" / "Roaming"
        return base / "claude-hub"
    return Path.home() / ".config" / "claude-hub"


def restrict_file(path: Path) -> str | None:
    """Make `path` readable by its owner only.

    Returns None on success, or a human-readable reason it stayed readable by
    others — callers surface that instead of pretending the key is protected.
    """
    if not IS_WINDOWS:
        try:
            os.chmod(path, 0o600)
        except OSError as exc:
            return f"chmod 600 failed on {path}: {exc}"
        return None

    user = os.environ.get("USERNAME")
    if not user:
        return f"USERNAME unset — {path} keeps inherited permissions"
    icacls = shutil.which("icacls")
    if not icacls:
        return f"icacls not found — {path} keeps inherited permissions"
    done = subprocess.run(
        [icacls, str(path), "/inheritance:r", "/grant:r", f"{user}:(R,W)"],
        capture_output=True, text=True, check=False,
    )
    if done.returncode != 0:
        detail = (done.stderr or done.stdout).strip().splitlines()
        return f"icacls failed on {path}: {detail[0] if detail else 'unknown error'}"
    return None


def find_claude() -> str | None:
    """Locate the `claude` executable, or None if it is not installed."""
    found = shutil.which("claude")
    if found:
        return found

    if IS_WINDOWS:
        candidates = [
            Path.home() / ".local" / "bin" / "claude.exe",
            Path.home() / "AppData" / "Local" / "Programs" / "claude" / "claude.exe",
        ]
        roaming = os.environ.get("APPDATA")
        if roaming:
            candidates.append(Path(roaming) / "npm" / "claude.cmd")
    else:
        candidates = [Path.home() / ".local" / "bin" / "claude"]

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


_UNICODE_GLYPHS = {
    "hline": "─",
    "pointer": "▸",
    "on": "●",
    "off": "○",
    "yes": "✓",
    "no": "✗",
    "caret": "█",
    "arrow": "→",
    "dash": "—",
    "updown": "↑↓",
    "leftright": "←→",
}

_ASCII_GLYPHS = {
    "hline": "-",
    "pointer": ">",
    "on": "*",
    "off": "o",
    "yes": "+",
    "no": "x",
    "caret": "_",
    "arrow": "->",
    "dash": "-",
    "updown": "^v",
    "leftright": "<>",
}


def console_speaks_unicode() -> bool:
    """True when the console encoding can render the box-drawing glyph set.

    Windows consoles still run legacy code pages (cp866, cp1251) where curses
    raises on these characters, so the glyph set follows the encoding.
    """
    encoding = (getattr(sys.stdout, "encoding", None) or "").lower()
    return "utf" in encoding


GLYPH = _UNICODE_GLYPHS if console_speaks_unicode() else _ASCII_GLYPHS


def enable_ansi() -> None:
    """Turn on VT escape processing so ANSI colours render in Windows consoles.

    No-op on POSIX, and on a redirected stdout (where colour is unwanted
    anyway and GetConsoleMode has no console to report on).
    """
    if not IS_WINDOWS:
        return
    import ctypes

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.GetStdHandle(-11)
    mode = ctypes.c_uint32()
    if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)
