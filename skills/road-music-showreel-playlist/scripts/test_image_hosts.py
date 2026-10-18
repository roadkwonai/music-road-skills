import copy
import json
from pathlib import Path
import tempfile
import unittest
import cd_presets as cd

class ImageHosts(unittest.TestCase):
    def test_host_plans_preserve_art_and_roundtrip(self):
        base = cd.genre_plan('록 발라드', style='그루브', host='codex')
        providers = {
            'codex': ('image_gen', 'built-in'),
            'claude': ('gpt-image', 'codex-cli-bridge'),
            'antigravity': ('antigravity-native', 'host-native'),
            'antigravity-cli': ('antigravity-native', 'host-native'),
        }
        for host, (tool, mode) in providers.items():
            plan = cd.genre_plan('록 발라드', style='그루브', host=host)
            self.assertEqual(plan['imageGeneration']['assets'], base['imageGeneration']['assets'])
            self.assertEqual(plan['imageGeneration']['host'], host)
            self.assertEqual((plan['imageGeneration']['requiredTool'], plan['imageGeneration']['mode']), (tool, mode))
            with tempfile.TemporaryDirectory() as temp:
                p=Path(temp)/'plan.json';p.write_text(json.dumps(plan));self.assertEqual(cd.load_plan(p),plan)
        with self.assertRaises(ValueError): cd.genre_plan('팝', host='imaginary')

    def test_legacy_plan_and_mismatched_provider(self):
        plan=cd.genre_plan('팝');del plan['imageGeneration']['host']
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'plan.json';p.write_text(json.dumps(plan));self.assertEqual(cd.load_plan(p),plan)
            plan['imageGeneration']['host']='antigravity';p.write_text(json.dumps(plan))
            with self.assertRaises(ValueError):cd.load_plan(p)

if __name__=='__main__': unittest.main()
