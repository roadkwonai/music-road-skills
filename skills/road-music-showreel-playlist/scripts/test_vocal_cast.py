#!/usr/bin/env python3
"""Behavioral checks for explicit vocal casting and asset verification."""

from __future__ import annotations

import unittest

from vocal_cast import casting_spec, check_asset_casting


def manifest(casting=None):
    result = {
        "photoA": "photo-a.png",
        "photoB": "photo-b.png",
        "photoC": "photo-c.png",
        "case": "case.png",
        "paper": "paper.png",
    }
    if casting is not None:
        result["casting"] = casting
    return result


class CastingSpecTests(unittest.TestCase):
    def test_female_band_keeps_a_female_lead(self):
        spec = casting_spec("여성 보컬", "band", "Dawn Signal")
        self.assertEqual(spec["vocal"], "female")
        self.assertIn("adult female lead vocalist", spec["subject"])
        self.assertIn("band", spec["subject"])
        self.assertIn("Dawn Signal", spec["subject"])
        self.assertFalse(spec["needsConfirmation"])

    def test_male_mixed_and_aliases(self):
        self.assertIn("adult male vocalist", casting_spec("남성보컬", "solo")["subject"])
        mixed = casting_spec("혼성", "duo")
        self.assertEqual(mixed["vocal"], "mixed")
        self.assertIn("female and male", mixed["subject"])
        self.assertEqual(casting_spec("female")["vocal"], "female")

    def test_none_conflict_and_unknown(self):
        self.assertTrue(casting_spec("연주곡")["instrumental"])
        self.assertEqual(casting_spec(instrumental=True)["vocal"], "none")
        with self.assertRaises(ValueError):
            casting_spec("female", instrumental=True)
        unknown = casting_spec()
        self.assertEqual(unknown["vocal"], "unknown")
        self.assertTrue(unknown["needsConfirmation"])
        self.assertNotIn("female", unknown["subject"])

    def test_rejects_invalid_casting_inputs(self):
        with self.assertRaises(ValueError):
            casting_spec("child")
        with self.assertRaises(ValueError):
            casting_spec("female", "quartet")
        with self.assertRaises(ValueError):
            casting_spec("female", instrumental="yes")


class AssetCastingTests(unittest.TestCase):
    def test_known_vocal_requires_reviewed_matching_metadata(self):
        spec = casting_spec("female", "band")
        self.assertEqual(
            check_asset_casting(spec, manifest({"vocal": "female", "act": "band", "reviewed": True}))["status"],
            "matched",
        )
        for casting in (None, {"vocal": "female", "act": "band", "reviewed": False}, {"vocal": "male", "act": "band", "reviewed": True}):
            with self.assertRaises(ValueError):
                check_asset_casting(spec, manifest(casting))

    def test_explicit_act_rejects_a_different_reviewed_cast(self):
        female_band = casting_spec("female", "band")
        with self.assertRaises(ValueError):
            check_asset_casting(female_band, manifest({"vocal": "female", "act": "solo", "reviewed": True}))
        auto = casting_spec("female")
        self.assertEqual(
            check_asset_casting(auto, manifest({"vocal": "female", "act": "solo", "reviewed": True}))["status"],
            "matched",
        )
        with self.assertRaises(ValueError):
            check_asset_casting(auto, manifest({"vocal": "female", "act": "artwork", "reviewed": True}))

    def test_unknown_is_never_a_gender_confirmation(self):
        result = check_asset_casting(casting_spec("unknown"), manifest())
        self.assertEqual(result, {"status": "unconfirmed", "vocal": "unknown", "act": "auto"})

    def test_unknown_explicit_act_needs_matching_review(self):
        unknown_band = casting_spec("unknown", "band")
        self.assertEqual(check_asset_casting(unknown_band, manifest())["status"], "unconfirmed")
        self.assertEqual(
            check_asset_casting(unknown_band, manifest({"vocal": "unknown", "act": "band", "reviewed": False}))["status"],
            "unconfirmed",
        )
        with self.assertRaises(ValueError):
            check_asset_casting(unknown_band, manifest({"vocal": "unknown", "act": "solo", "reviewed": True}))

    def test_artwork_override_and_demo_exception(self):
        artwork = casting_spec("female", "artwork")
        self.assertEqual(
            check_asset_casting(artwork, manifest({"vocal": "male", "act": "artwork", "reviewed": True}))["status"],
            "matched",
        )
        with self.assertRaises(ValueError):
            check_asset_casting(artwork, manifest({"vocal": "female", "act": "band", "reviewed": True}))
        self.assertEqual(check_asset_casting(casting_spec("male"), manifest(), allow_demo=True)["status"], "demo-only")

    def test_rejects_bad_asset_metadata(self):
        with self.assertRaises(ValueError):
            check_asset_casting(casting_spec("female"), {"photoA": "a.png"})
        with self.assertRaises(ValueError):
            check_asset_casting(casting_spec("female"), manifest({"vocal": "female", "act": "solo", "reviewed": "yes"}))


if __name__ == "__main__":
    unittest.main()
