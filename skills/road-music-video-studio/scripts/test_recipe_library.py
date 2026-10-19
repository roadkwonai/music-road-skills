from pathlib import Path
import json
import tempfile
import unittest
from studio_status import recipe_snapshot

class RecipeLibraryTests(unittest.TestCase):
    def test_local_bundle_needs_no_service_or_schema_to_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'docs').mkdir();(root/'cli').mkdir();(root/'cli/road-music.js').write_text('// fixture')
            card = {'id':'a','title':'기도 CCM','tags':['기도'],'prompt':'예시'}
            (root/'docs/ccm-recipes.json').write_text(json.dumps({'schemaVersion':1,'guides':[card],'styles':[]}),encoding='utf-8')
            result = recipe_snapshot('ccm', env={'ROADMUSIC_CLI_ROOT':str(root)})
            self.assertEqual(result['guides'][0]['title'],'기도 CCM')
            self.assertTrue(result['readOnly'])
            self.assertFalse(result['safety']['generation'])
    def test_distributed_recipes_remain_available_without_a_cli(self):
        result = recipe_snapshot('ccm', env={'ROADMUSIC_CLI_ROOT':'/missing/cli'}, script_path=Path('/var/empty/guide.py'))
        self.assertEqual(result['state'],'ready')
        self.assertGreaterEqual(len(result['guides']),52)
        self.assertEqual(len(result['styles']),48)
        source = next((p for p in Path(__file__).resolve().parents if (p/'cli/road-music.js').is_file()),None)
        if source:
            for name in ['command-recipes.json','ccm-recipes.json']:
                bundled = Path(__file__).resolve().parents[1]/'assets/knowledge'/name
                self.assertEqual(json.loads((source/'docs'/name).read_text()),json.loads(bundled.read_text()))

    def test_ccm_engine_and_revision_contracts(self):
        data = recipe_snapshot('ccm',env={'ROADMUSIC_CLI_ROOT':'/missing/cli'},script_path=Path('/var/empty/guide.py'))
        cards = {item['id']:item for item in data['guides']}
        for item in cards.values():
            variants = [v['prompt'] for v in item['variations']]
            self.assertEqual(len(set(variants)),len(variants))
            self.assertNotIn(item['prompt'],variants)
        for name in ['yue-plan','yue-six-eight']:
            self.assertNotIn('engine:"yue"·',cards[name]['prompt'])
        for variant in cards['yue-mlx']['variations']:
            self.assertIn('engine:"yue-mlx"',variant['prompt'])
            self.assertNotIn('engine:"yue"',variant['prompt'])
        commands=[step['command'] for step in cards['yue-partial']['commands']]
        self.assertNotIn('song:render',commands)
        self.assertLess(commands.index('score:compare'),commands.index('song:generate'))
        self.assertLess(commands.index('song:generate'),commands.index('job:wait'))

    def test_unknown_collection_and_invalid_bundle_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'docs').mkdir();(root/'cli').mkdir();(root/'cli/road-music.js').write_text('// fixture')
            (root/'docs/ccm-recipes.json').write_text('{broken',encoding='utf-8')
            self.assertEqual(recipe_snapshot('ccm',env={'ROADMUSIC_CLI_ROOT':str(root)})['state'],'unavailable')
            with self.assertRaises(ValueError):recipe_snapshot('../../private',env={'ROADMUSIC_CLI_ROOT':str(root)})

if __name__=='__main__': unittest.main()
