"""Model id schemes: encoding, decoding, and what reaches the gateway.

The regression these cover: tiers and profiles persist a model id as a plain
string, so an id saved under one scheme used to be exported verbatim under
another, and the gateway read claude-hub's "-dd-" disguise as a provider name.
"""
import unittest

from claude_hub import models as mdl
from claude_hub.launcher import tier_model_id, resolve_provider


RAW = {"name": "raw-gw", "type": "gateway", "url": "https://gw.example",
       "encode_model_ids": False}
ENC = {"name": "enc-gw", "type": "gateway", "url": "https://gw.example",
       "encode_model_ids": True}
DIRECT = {"name": "direct", "type": "direct", "url": "https://api.example"}


class EncodeDecodeTest(unittest.TestCase):
    def test_round_trip_preserves_id(self):
        for clean in ("auto/best-free", "auto/coding:free",
                      "no-think/cc/claude-opus-5", "openrouter/qwen/qwen3"):
            self.assertEqual(mdl._decode_cpa_id(mdl._encode_cpa_id(clean)), clean)

    def test_claude_ids_are_never_disguised(self):
        self.assertEqual(mdl._encode_cpa_id("claude-fable-5"), "claude-fable-5")

    def test_decode_passes_through_plain_ids(self):
        self.assertEqual(mdl._decode_cpa_id("auto/best-free"), "auto/best-free")

    def test_known_failing_id_decodes_to_real_model(self):
        # The id from the 401 this fix came from.
        self.assertEqual(
            mdl._decode_cpa_id("claude-fable-5-dd-eerf-tseb/otua"),
            "auto/best-free",
        )


class TierModelIdTest(unittest.TestCase):
    def test_encoded_tier_is_stripped_for_a_raw_gateway(self):
        self.assertEqual(
            tier_model_id("claude-fable-5-dd-eerf-tseb/otua", RAW),
            "auto/best-free",
        )

    def test_raw_tier_is_disguised_for_an_encoding_gateway(self):
        self.assertEqual(
            tier_model_id("auto/best-free", ENC),
            "claude-fable-5-dd-eerf-tseb/otua",
        )

    def test_already_correct_ids_are_left_alone(self):
        self.assertEqual(tier_model_id("auto/best-free", RAW), "auto/best-free")
        self.assertEqual(
            tier_model_id("claude-fable-5-dd-eerf-tseb/otua", ENC),
            "claude-fable-5-dd-eerf-tseb/otua",
        )

    def test_direct_provider_always_gets_the_clean_id(self):
        self.assertEqual(
            tier_model_id("claude-fable-5-dd-eerf-tseb/otua", DIRECT),
            "auto/best-free",
        )

    def test_empty_id_survives(self):
        self.assertEqual(tier_model_id("", RAW), "")

    def test_switching_scheme_is_idempotent(self):
        once = tier_model_id("auto/best-free", ENC)
        self.assertEqual(tier_model_id(once, ENC), once)
        self.assertEqual(tier_model_id(once, RAW), "auto/best-free")


class ResolveProviderTest(unittest.TestCase):
    def test_coverage_matches_across_schemes(self):
        """A tier stored encoded still matches a provider serving it raw."""
        cfg = {
            "providers": [
                {"name": "a", "type": "gateway", "url": "https://a",
                 "encode_model_ids": False},
                {"name": "b", "type": "gateway", "url": "https://b",
                 "encode_model_ids": False},
            ],
            "tiers": {"OPUS": "claude-fable-5-dd-eerf-tseb/otua"},
        }
        served = {
            "a": [],
            "b": [{"id": "auto/best-free", "clean_id": "auto/best-free"}],
        }
        orig = mdl.fetch_models
        mdl.fetch_models = lambda p, force=False: served[p["name"]]
        try:
            provider, notes = resolve_provider(cfg)
        finally:
            mdl.fetch_models = orig
        self.assertEqual(provider["name"], "b")
        self.assertEqual(notes, [])


if __name__ == "__main__":
    unittest.main()
