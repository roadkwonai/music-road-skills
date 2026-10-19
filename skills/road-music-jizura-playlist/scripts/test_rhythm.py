#!/usr/bin/env python3
import hashlib
import importlib.util
import unittest
from pathlib import Path

import numpy as np

MODULE = Path(__file__).with_name('rhythm.py')
spec = importlib.util.spec_from_file_location('rhythm', MODULE)
rhythm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rhythm)


def pulse_train(bpm=140, phase=.135, duration=80, sample_rate=rhythm.SAMPLE_RATE):
    count = round(duration * sample_rate)
    samples = np.zeros(count, dtype=np.float32)
    width = round(sample_rate * .025)
    envelope = np.exp(-np.arange(width) / (sample_rate * .006)).astype(np.float32)
    for time in np.arange(phase, duration, 60 / bpm):
        start = round(time * sample_rate)
        if start + width <= count:
            samples[start:start + width] += envelope
    return samples


class RhythmTests(unittest.TestCase):
    def analysis(self, samples, bpm=138, phase=.13):
        digest = hashlib.sha256(samples.tobytes()).hexdigest()
        return rhythm.analyze(samples, '/absolute/synthetic.wav', digest,
                              {'audio': {'sha256': digest, 'bpm': bpm, 'beats': [phase]}})

    def test_fits_wrong_native_tempo_and_phase(self):
        value = self.analysis(pulse_train(phase=.135), phase=.13)
        self.assertAlmostEqual(value['bestCandidate']['bpm'], 140, delta=.05)
        # The spectral-flux timestamp is the attack-window peak, not the injected sample index.
        self.assertAlmostEqual(value['bestCandidate']['phase'], .1, delta=.01)
        self.assertGreater(value['nativeVsFit']['fittedScore'], value['nativeVsFit']['nativeScore'])
        self.assertGreater(value['gridDistance']['fitted']['strongOnsetsWithin40msRatio'], .9)
        self.assertLess(value['gridDistance']['fitted']['gridTickPrecision'], 1)

    def test_rejects_empty_nan_and_silence(self):
        for samples in (np.array([], dtype=np.float32), np.array([np.nan] * rhythm.NFFT, dtype=np.float32),
                        np.zeros(rhythm.NFFT, dtype=np.float32)):
            with self.assertRaises(ValueError):
                rhythm.onset_features(samples)

    def test_marks_unstructured_noise_low_confidence(self):
        rng = np.random.default_rng(4)
        samples = (rng.normal(0, .05, rhythm.SAMPLE_RATE * 80)).astype(np.float32)
        value = self.analysis(samples)
        self.assertEqual(value['confidence'], 'low')

    def test_rejects_native_hash_mismatch(self):
        samples = pulse_train()
        with self.assertRaisesRegex(ValueError, 'SHA256'):
            rhythm.analyze(samples, '/absolute/synthetic.wav', 'wrong',
                            {'audio': {'sha256': 'different', 'bpm': 140, 'beats': [.135]}})


if __name__ == '__main__':
    unittest.main()
