"""Compaction regimes and the window each model ends up compacting against.

Claude Code reads CLAUDE_CODE_MAX_CONTEXT_TOKENS only while DISABLE_COMPACT is
set, so raising the window used to mean losing compaction entirely. These
cover the split: compaction on, where it resolves a recognised model's window
itself, and compaction off, where one window is forced on everything.
"""
import unittest
from unittest import mock

from claude_hub import launcher
from claude_hub.launcher import _apply_context, _recognised, _real_window


PROV = {"name": "gw", "type": "gateway", "url": "https://gw.example",
        "encode_model_ids": False}

CLAUDE_TIERS = {
    "OPUS": "cc/claude-opus-5",
    "HAIKU": "no-think/cc/claude-haiku-4-5-20251001",
}


def apply(cfg, tiers, env=None, advertised=None, windows=None):
    env = env if env is not None else {}
    with mock.patch.object(launcher.integration, "install"), \
         mock.patch.object(launcher.integration, "context_windows",
                           return_value=windows or {}), \
         mock.patch.object(launcher, "_advertised",
                           return_value=advertised or {}):
        notes = _apply_context(env, cfg, tiers, PROV)
    return env, notes


class RecognisedTest(unittest.TestCase):
    def test_gateway_prefixes_do_not_hide_a_claude_name(self):
        for mid in ("cc/claude-opus-5", "no-think/cc/claude-haiku-4-5",
                    "claude-fable-5"):
            self.assertTrue(_recognised(mid), mid)

    def test_non_claude_ids_are_unknown(self):
        for mid in ("auto/best-coding", "openrouter/qwen/qwen3", ""):
            self.assertFalse(_recognised(mid), mid)


class RealWindowTest(unittest.TestCase):
    def test_manual_table_wins_over_the_provider(self):
        got = _real_window("auto/best-coding", {"best-coding": 500000},
                           {"auto/best-coding": 1000000})
        self.assertEqual(got, 500000)

    def test_provider_figure_is_used_when_the_table_is_silent(self):
        self.assertEqual(
            _real_window("auto/best-coding", {}, {"auto/best-coding": 1000000}),
            1000000,
        )

    def test_comment_keys_are_skipped(self):
        self.assertIsNone(_real_window("auto/x", {"_comment": 1}, {}))

    def test_unknown_everywhere_is_none(self):
        self.assertIsNone(_real_window("auto/x", {}, {}))


class CompactionOnTest(unittest.TestCase):
    cfg = {"context": {"window": 1000000, "disable_compact": False}}

    def test_recognised_models_get_no_overrides(self):
        env, notes = apply(self.cfg, CLAUDE_TIERS)
        self.assertEqual(env, {})
        self.assertIn("each model's own window", notes[0])

    def test_stale_vars_from_the_parent_env_are_cleared(self):
        env, _ = apply(self.cfg, CLAUDE_TIERS, env={
            "DISABLE_COMPACT": "1",
            "CLAUDE_CODE_MAX_CONTEXT_TOKENS": "1000000",
            "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "999",
            "PATH": "/usr/bin",
        })
        self.assertEqual(env, {"PATH": "/usr/bin"})

    def test_unknown_model_with_a_bigger_window_lifts_enforcement(self):
        env, notes = apply(
            self.cfg, {"OPUS": "auto/best-coding"},
            advertised={"auto/best-coding": 1000000},
        )
        self.assertEqual(
            env["CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT"], "1")
        self.assertEqual(env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"], "1000000")
        self.assertNotIn("DISABLE_COMPACT", env)
        self.assertIn("auto/best-coding", notes[0])

    def test_trigger_is_the_smallest_window_among_unknown_models(self):
        env, _ = apply(
            self.cfg,
            {"OPUS": "auto/big", "SONNET": "auto/small"},
            advertised={"auto/big": 1000000, "auto/small": 262144},
        )
        self.assertEqual(env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"], "262144")

    def test_unknown_model_at_or_below_the_floor_is_left_to_claude_code(self):
        env, _ = apply(self.cfg, {"OPUS": "auto/small"},
                       advertised={"auto/small": 200000})
        self.assertEqual(env, {})

    def test_unknown_model_without_any_window_is_left_alone(self):
        env, _ = apply(self.cfg, {"OPUS": "auto/mystery"})
        self.assertEqual(env, {})

    def test_a_recognised_model_is_never_treated_as_unknown(self):
        env, _ = apply(self.cfg, CLAUDE_TIERS,
                       advertised={"cc/claude-opus-5": 1000000})
        self.assertEqual(env, {})

    def test_blank_tier_is_skipped(self):
        env, _ = apply(self.cfg, {"OPUS": "", "SONNET": None})
        self.assertEqual(env, {})


class CompactionOffTest(unittest.TestCase):
    cfg = {"context": {"window": 1000000, "disable_compact": True}}

    def test_window_is_forced_and_compaction_disabled(self):
        env, notes = apply(self.cfg, CLAUDE_TIERS)
        self.assertEqual(env["DISABLE_COMPACT"], "1")
        self.assertEqual(env["CLAUDE_CODE_MAX_CONTEXT_TOKENS"], "1000000")
        self.assertIn("/compact disabled", notes[0])

    def test_the_unknown_model_levers_stay_out_of_it(self):
        env, _ = apply(self.cfg, {"OPUS": "auto/best-coding"},
                       advertised={"auto/best-coding": 1000000})
        self.assertNotIn("CLAUDE_CODE_AUTO_COMPACT_WINDOW", env)
        self.assertNotIn(
            "CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT", env)

    def test_default_config_keeps_compaction_on(self):
        from claude_hub.config import DEFAULT_CONTEXT
        self.assertFalse(DEFAULT_CONTEXT["disable_compact"])


if __name__ == "__main__":
    unittest.main()
