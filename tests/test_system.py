"""Both platform branches of claude_hub.system, including the Windows one."""
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from claude_hub import system


class ConfigDirTest(unittest.TestCase):
    def test_posix_uses_xdg_style_path(self):
        with mock.patch.object(system, "IS_WINDOWS", False):
            self.assertEqual(
                system.config_dir(), Path.home() / ".config" / "claude-hub"
            )

    def test_windows_uses_appdata(self):
        with mock.patch.object(system, "IS_WINDOWS", True), \
                mock.patch.dict(system.os.environ, {"APPDATA": r"C:\Users\me\AppData\Roaming"}):
            self.assertEqual(
                system.config_dir(), Path(r"C:\Users\me\AppData\Roaming") / "claude-hub"
            )

    def test_windows_without_appdata_falls_back_under_home(self):
        with mock.patch.object(system, "IS_WINDOWS", True), \
                mock.patch.dict(system.os.environ, {}, clear=True):
            self.assertEqual(
                system.config_dir(),
                Path.home() / "AppData" / "Roaming" / "claude-hub",
            )


class RestrictFileTest(unittest.TestCase):
    def test_posix_chmods_to_owner_only(self):
        key = Path(self.enterContext(TemporaryDirectory())) / "key"
        key.write_text("secret")
        with mock.patch.object(system, "IS_WINDOWS", False):
            self.assertIsNone(system.restrict_file(key))
        self.assertEqual(key.stat().st_mode & 0o777, 0o600)

    def test_windows_runs_icacls(self):
        run = mock.Mock(return_value=subprocess.CompletedProcess([], 0, "", ""))
        with mock.patch.object(system, "IS_WINDOWS", True), \
                mock.patch.dict(system.os.environ, {"USERNAME": "me"}), \
                mock.patch.object(system.shutil, "which", return_value="icacls.exe"), \
                mock.patch.object(system.subprocess, "run", run):
            self.assertIsNone(system.restrict_file(Path(r"C:\keys\k")))
        argv = run.call_args.args[0]
        self.assertEqual(argv[1:], [r"C:\keys\k", "/inheritance:r", "/grant:r", "me:(R,W)"])

    def test_windows_reports_icacls_failure(self):
        failed = subprocess.CompletedProcess([], 1, "", "Invalid parameter")
        with mock.patch.object(system, "IS_WINDOWS", True), \
                mock.patch.dict(system.os.environ, {"USERNAME": "me"}), \
                mock.patch.object(system.shutil, "which", return_value="icacls.exe"), \
                mock.patch.object(system.subprocess, "run", return_value=failed):
            warning = system.restrict_file(Path(r"C:\keys\k"))
        self.assertIn("icacls failed", warning)

    def test_windows_reports_missing_icacls(self):
        with mock.patch.object(system, "IS_WINDOWS", True), \
                mock.patch.dict(system.os.environ, {"USERNAME": "me"}), \
                mock.patch.object(system.shutil, "which", return_value=None):
            warning = system.restrict_file(Path(r"C:\keys\k"))
        self.assertIn("icacls not found", warning)


class FindClaudeTest(unittest.TestCase):
    def test_path_lookup_wins(self):
        with mock.patch.object(system.shutil, "which", return_value=r"C:\bin\claude.cmd"):
            self.assertEqual(system.find_claude(), r"C:\bin\claude.cmd")

    def test_windows_falls_back_to_native_installer_path(self):
        home = Path(self.enterContext(TemporaryDirectory()))
        native = home / ".local" / "bin" / "claude.exe"
        native.parent.mkdir(parents=True)
        native.write_text("")
        self.enterContext(mock.patch.object(system, "IS_WINDOWS", True))
        self.enterContext(mock.patch.object(system.shutil, "which", return_value=None))
        self.enterContext(mock.patch.object(system.Path, "home", return_value=home))
        self.enterContext(mock.patch.dict(system.os.environ, {}, clear=True))
        self.assertEqual(system.find_claude(), str(native))

    def test_returns_none_when_not_installed(self):
        home = Path(self.enterContext(TemporaryDirectory()))
        with mock.patch.object(system.shutil, "which", return_value=None), \
                mock.patch.object(system.Path, "home", return_value=home):
            self.assertIsNone(system.find_claude())


class GlyphTest(unittest.TestCase):
    def test_both_sets_cover_the_same_names(self):
        self.assertEqual(
            set(system._UNICODE_GLYPHS), set(system._ASCII_GLYPHS)
        )

    def test_ascii_set_is_encodable_on_legacy_code_pages(self):
        for name, glyph in system._ASCII_GLYPHS.items():
            with self.subTest(glyph=name):
                glyph.encode("cp866")

    def test_encoding_decides_the_set(self):
        for encoding, unicode_ok in (("utf-8", True), ("UTF-8", True),
                                     ("cp866", False), ("cp1251", False),
                                     (None, False)):
            stdout = SimpleNamespace(encoding=encoding)
            with self.subTest(encoding=encoding), \
                    mock.patch.object(system.sys, "stdout", stdout):
                self.assertEqual(system.console_speaks_unicode(), unicode_ok)


class EnableAnsiTest(unittest.TestCase):
    def test_noop_off_windows(self):
        with mock.patch.object(system, "IS_WINDOWS", False):
            self.assertIsNone(system.enable_ansi())


if __name__ == "__main__":
    unittest.main()
