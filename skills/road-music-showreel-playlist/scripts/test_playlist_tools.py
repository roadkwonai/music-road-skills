#!/usr/bin/env python3
"""Small behavioral checks for the reusable playlist helpers."""

from __future__ import annotations

import math
from pathlib import Path
import tempfile
import unittest
import wave

from playlist_tools import ANALYSIS_RATE, concat_wavs, normalize_display, spectrum_data


def write_wav(path, frames, frequency=0, rate=48_000, channels=2):
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(rate)
        for frame in range(frames):
            value = int(12_000 * math.sin(2 * math.pi * frequency * frame / rate)) if frequency else 0
            output.writeframesraw(value.to_bytes(2, "little", signed=True) * channels)


def write_tone_onset(path, silent_frames, tone_frames, frequency=440):
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(48_000)
        output.writeframesraw(b"\0\0\0\0" * silent_frames)
        for frame in range(tone_frames):
            value = int(12_000 * math.sin(2 * math.pi * frequency * frame / 48_000))
            output.writeframesraw(value.to_bytes(2, "little", signed=True) * 2)


class DisplayTests(unittest.TestCase):
    def test_skip_defaults_and_channel(self):
        self.assertEqual(normalize_display(), {"showSpectrum": False, "showQueue": False, "showNowPlaying": False, "channelName": ""})
        self.assertEqual(normalize_display({"showSpectrum": True, "showQueue": " SKIP ", "showNowPlaying": None, "channelName": "  Road Music  "}), {"showSpectrum": True, "showQueue": False, "showNowPlaying": False, "channelName": "Road Music"})

    def test_display_rejects_invalid_values(self):
        for value in ({"showSpectrum": "yes"}, {"unknown": True}, {"channelName": "bad\nname"}, {"channelName": "x" * 121}, []):
            with self.assertRaises(ValueError):
                normalize_display(value)


class AudioTests(unittest.TestCase):
    def test_concat_preserves_frames_and_existing_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first, second, target = root / "a.wav", root / "b.wav", root / "mix.wav"
            write_wav(first, 120, 440)
            write_wav(second, 80, 880)
            self.assertEqual(concat_wavs([first, second], target), 200)
            with wave.open(str(target)) as joined:
                self.assertEqual(joined.getnframes(), 200)
                samples = joined.readframes(200)
            with wave.open(str(first)) as source:
                self.assertEqual(samples[: 120 * 4], source.readframes(120))
            with self.assertRaises(FileExistsError):
                concat_wavs([first], target)

    def test_concat_rejects_wrong_channels_without_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            good, bad, target = root / "good.wav", root / "bad.wav", root / "mix.wav"
            write_wav(good, 10)
            write_wav(bad, 10, channels=1)
            with self.assertRaises(ValueError):
                concat_wavs([good, bad], target)
            self.assertFalse(target.exists())

    def test_spectrum_is_deterministic_and_frequency_sensitive(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            silent, low, high = root / "silent.wav", root / "low.wav", root / "high.wav"
            write_wav(silent, 9_600)
            write_wav(low, 9_600, 220)
            write_wav(high, 9_600, 4_000)
            silence = spectrum_data(silent, bands=24)
            low_data = spectrum_data(low, bands=24)
            high_data = spectrum_data(high, bands=24)
            self.assertEqual(silence["frames"], [[0] * 24 for _ in silence["frames"]])
            self.assertEqual(low_data, spectrum_data(low, bands=24))
            self.assertEqual(low_data["sampleRate"], ANALYSIS_RATE)
            self.assertAlmostEqual(low_data["durationSeconds"], .2)
            self.assertEqual(len(spectrum_data(low, bands=24, dt=1)["frames"]), 1)
            self.assertNotEqual(max(range(24), key=lambda i: low_data["frames"][0][i]), max(range(24), key=lambda i: high_data["frames"][0][i]))

    def test_spectrum_centers_windows_and_keeps_actual_clock(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "onset.wav"
            write_tone_onset(source, 48_000, 48_000)
            data = spectrum_data(source, bands=24, dt=.0333333)
            self.assertEqual(data["windowAlignment"], "center")
            self.assertEqual(data["requestedDt"], .0333333)
            self.assertEqual(data["hopSamples"], 800)
            self.assertEqual(data["dt"], 800 / ANALYSIS_RATE)
            self.assertEqual(len(data["frames"]), math.ceil(data["durationSeconds"] / data["dt"]))
            # At t=0.8s the centered 170ms window ends before the 1.0s tone onset.
            self.assertEqual(max(data["frames"][24]), 0)
            # At t=1.0s the centered window contains the tone; no extra frame is emitted after the end.
            self.assertGreater(max(data["frames"][30]), 0)
            self.assertEqual(max(data["frames"][0]), 0)
            self.assertGreater(max(data["frames"][-1]), 0)
            self.assertEqual(len(data["frames"]), 60)


if __name__ == "__main__":
    unittest.main()
