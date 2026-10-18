import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import wave
import numpy as np

SCRIPT = Path(__file__).resolve().with_name('audio_onsets.py')
spec = importlib.util.spec_from_file_location('audio_onsets', SCRIPT)
onsets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(onsets)


class AudioOnsetsTests(unittest.TestCase):
    def test_silence_and_short_inputs(self):
        for length in (0, 500, 1024, 1184, 16000):
            self.assertEqual(onsets.detect(np.zeros(length)), [])

    def test_quiet_and_loud_attacks(self):
        audio = np.zeros(onsets.RATE * 14, dtype=np.float32)
        for second in range(1, 14):
            audio[second * onsets.RATE] = 0.05 if second < 6 else 1
        events = onsets.detect(audio)
        for second in (1, 3, 5, 7, 10, 13):
            self.assertTrue(any(abs(t-second)<0.06 for t, _ in events), second)
        self.assertTrue(all(b[0]-a[0]>=0.27 for a,b in zip(events,events[1:])))
        self.assertTrue(all(0<=t<14 and np.isfinite(s) for t,s in events))

    def test_invalid_values(self):
        for spacing in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError): onsets.detect(np.zeros(16000), spacing)
        for value in (float('nan'), float('inf')):
            with self.assertRaises(ValueError): onsets.detect(np.full(16000, value))
        with self.assertRaises(ValueError): onsets.detect(np.zeros((10,2)))

    def test_cli_source_hash_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            src=Path(folder)/'music.wav'; out=Path(folder)/'events.json'
            pcm=np.zeros(32000,dtype='<i2');pcm[8000]=16000
            with wave.open(str(src),'wb') as f:
                f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(pcm.tobytes())
            source_hash=hashlib.sha256(src.read_bytes()).hexdigest()
            cmd=[sys.executable,str(SCRIPT),'--audio',str(src),'--out',str(out)]
            subprocess.run(cmd,check=True,capture_output=True)
            result=json.loads(out.read_text())
            self.assertEqual(result['sourceAudioSha256'],source_hash)
            self.assertEqual(result['durationSeconds'],2)
            self.assertTrue(any(abs(e['timeSeconds']-.5)<.06 for e in result['events']))
            self.assertEqual(hashlib.sha256(src.read_bytes()).hexdigest(),source_hash)
            saved=out.read_bytes()
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
            self.assertEqual(out.read_bytes(),saved)
            self.assertNotEqual(subprocess.run([*cmd[:-1],str(src)],capture_output=True).returncode,0)
            self.assertEqual(hashlib.sha256(src.read_bytes()).hexdigest(),source_hash)


if __name__ == '__main__': unittest.main()
