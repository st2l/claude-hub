"""Self-update: pull the checkout claude-hub is running from.

The installer leaves a git clone at ~/.local/share/claude-hub, so updating is
a fetch plus a reset. Reset rather than pull because the checkout is not meant
to be edited in place: a stray local change should not turn an update into a
merge conflict. Anything we would throw away is reported first.

If this copy is not a git checkout at all (a tarball, a pip install, a
site-packages copy) there is nothing to pull, and the answer is the installer.
"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRANCH = "main"
INSTALL_CMD = (
    "curl -fsSL https://raw.githubusercontent.com/st2l/claude-hub/main/"
    "install.sh | bash"
)


def _git(*args, timeout: int = 60) -> tuple[int, str]:
    try:
        done = subprocess.run(
            ["git", "-C", str(ROOT), *args],
            capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return 1, str(error)
    return done.returncode, (done.stdout + done.stderr).strip()


def is_git_checkout() -> bool:
    return (ROOT / ".git").exists()


def current_revision() -> str:
    code, out = _git("rev-parse", "--short", "HEAD")
    return out if code == 0 else "unknown"


def local_changes() -> list[str]:
    code, out = _git("status", "--porcelain")
    if code != 0 or not out:
        return []
    return out.splitlines()


def check() -> tuple[bool, str]:
    """(an update is waiting, description). Fetches, changes nothing."""
    if not is_git_checkout():
        return False, f"not a git checkout: {ROOT}"

    code, out = _git("fetch", "--quiet", "origin", BRANCH, timeout=90)
    if code != 0:
        return False, f"fetch failed: {out.splitlines()[-1] if out else code}"

    code, out = _git("rev-list", "--count", f"HEAD..origin/{BRANCH}")
    if code != 0:
        return False, f"cannot compare: {out}"
    try:
        behind = int(out)
    except ValueError:
        return False, f"cannot compare: {out}"

    if behind == 0:
        return False, f"up to date ({current_revision()})"
    return True, f"{behind} commit{'s' if behind != 1 else ''} behind origin/{BRANCH}"


def update(force: bool = False) -> tuple[bool, str]:
    """Fast-forward to origin. Refuses to discard local edits unless forced."""
    if not is_git_checkout():
        return False, f"not a git checkout, reinstall with: {INSTALL_CMD}"

    dirty = local_changes()
    if dirty and not force:
        return False, (
            f"{len(dirty)} local change(s) would be lost: "
            f"{', '.join(line.split(maxsplit=1)[-1] for line in dirty[:3])}"
            f"{' ...' if len(dirty) > 3 else ''}"
        )

    before = current_revision()
    code, out = _git("fetch", "--quiet", "origin", BRANCH, timeout=90)
    if code != 0:
        return False, f"fetch failed: {out.splitlines()[-1] if out else code}"

    code, out = _git("reset", "--hard", f"origin/{BRANCH}")
    if code != 0:
        return False, f"reset failed: {out.splitlines()[-1] if out else code}"

    after = current_revision()
    if before == after:
        return True, f"already at {after}"
    return True, f"{before} -> {after}"


def main(argv: list[str] | None = None):
    argv = argv or []
    if "--check" in argv or "-c" in argv:
        pending, note = check()
        print(("update available: " if pending else "") + note)
        return

    force = "--force" in argv or "-f" in argv
    print(f"Updating {ROOT}")
    ok, note = update(force=force)
    print(note if ok else f"[x] {note}")
    if ok:
        # The statusline lives in Claude Code's settings and points at a file
        # in this checkout, so a fresh install needs re-registering.
        from claude_hub import config, integration
        ctx = config.context_settings(config.load())
        for line in integration.install(statusline=ctx.get("statusline", True)):
            print(line)


if __name__ == "__main__":
    import sys
    main(sys.argv[1:])
