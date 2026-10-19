from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from studio_status import _instrument_guides, cli_root, reference_snapshot, status_snapshot


class Result:
    def __init__(self, payload, code=0):
        self.returncode = code
        self.stdout = json.dumps(payload) + '\n'
        self.stderr = ''


class StudioStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'cli').mkdir()
        (self.root / 'cli' / 'road-music.js').write_text('// fixture\n')
        self.skill = self.root / '.agents' / 'skills' / 'road-music-video-studio' / 'scripts'
        self.skill.mkdir(parents=True)
        (self.skill.parent / 'SKILL.md').write_text('fixture')
        (self.skill / 'studio.py').write_text('fixture')

    def tearDown(self):
        self.temp.cleanup()

    def runner(self, calls, connected=False):
        def run(argv, *, cwd, env, timeout):
            calls.append((argv, cwd, env, timeout))
            command = argv[2]
            if command == 'schema':
                return Result({'ok': True, 'result': {'commands': [
                    {'command': 'app:state', 'description': '상태', 'params': {'type': 'object', 'properties': {}, 'required': []}},
                    {'command': 'song:delete', 'description': '삭제', 'destructive': True, 'params': {'type': 'object', 'properties': {'dir': {'type': 'string'}}, 'required': ['dir']}},
                ]}})
            if command == 'cli:version':
                return Result({'ok': True, 'result': {'cliVersion': '0.1.0', 'appVersion': '0.1.0'}})
            if command == 'service:status':
                return Result({'ok': True, 'result': {'running': connected}})
            if command == 'storage:status':
                return Result({'ok': True, 'result': {'capabilities': {'workspaceScan': {'enabled': True, 'reason': None}, 'git': {'enabled': False, 'reason': 'Git 저장소 없음'}}, 'history': {'writesOnStatus': False}}})
            return Result({'ok': True, 'result': {'ready': True, 'token': 'must-not-leak', 'lyrics': 'must-not-leak'}})
        return run

    def test_cli_root_prefers_explicit_actual_root(self):
        self.assertEqual(cli_root({'ROADMUSIC_CLI_ROOT': str(self.root)}, self.skill / 'studio_status.py'), self.root.resolve())
        self.assertIsNone(cli_root({'ROADMUSIC_CLI_ROOT': str(self.root / 'missing')}, Path('/var/empty/road-music-status.py')))

    def test_status_never_starts_or_opens_when_service_is_absent(self):
        calls = []
        value = status_snapshot({'ROADMUSIC_CLI_ROOT': str(self.root)}, self.runner(calls), '2026-10-19T00:00:00Z', self.skill / 'studio_status.py')
        self.assertEqual(value['service']['state'], 'not-running')
        self.assertEqual([call[0][2] for call in calls], ['schema', 'cli:version', 'storage:status', 'service:status'])
        self.assertFalse(value['storage']['data']['capabilities']['git']['enabled'])
        self.assertTrue(value['storage']['data']['capabilities']['workspaceScan']['enabled'])
        self.assertIn('--no-start', calls[-1][0])
        self.assertTrue(all(call[2]['ROADMUSIC_STUDIO_AUTO_OPEN'] == '0' for call in calls))
        self.assertEqual(value['safety'], {'autoStart': False, 'autoOpen': False, 'install': False, 'render': False, 'update': False})

    def test_connected_status_uses_no_start_and_redacts_sensitive_response_fields(self):
        calls = []
        value = status_snapshot({'ROADMUSIC_CLI_ROOT': str(self.root)}, self.runner(calls, connected=True), script_path=self.skill / 'studio_status.py')
        self.assertEqual(value['service']['state'], 'connected')
        self.assertEqual(set(value['runtime']['checks']), {'app:capabilities', 'setup:check', 'engines:list', 'queue:list', 'video:state'})
        runtime_calls = calls[4:]
        self.assertTrue(all('--no-start' in call[0] for call in runtime_calls))
        self.assertNotIn('token', value['runtime']['checks']['app:capabilities']['data'])
        self.assertNotIn('lyrics', value['runtime']['checks']['app:capabilities']['data'])

    def test_storage_status_failure_does_not_start_a_service_or_run_a_scan(self):
        calls = []
        normal = self.runner(calls)
        def run(argv, **kwargs):
            if argv[2] == 'storage:status':
                calls.append((argv, kwargs['cwd'], kwargs['env'], kwargs['timeout']))
                return Result({'ok': False, 'error': {'message': 'unavailable'}})
            return normal(argv, **kwargs)
        value = status_snapshot({'ROADMUSIC_CLI_ROOT': str(self.root)}, run, script_path=self.skill / 'studio_status.py')
        self.assertEqual(value['storage']['state'], 'failed')
        self.assertEqual([call[0][2] for call in calls], ['schema', 'cli:version', 'storage:status', 'service:status'])

    def test_reference_reads_schema_once_and_classifies_public_commands(self):
        calls = []
        value = reference_snapshot({'ROADMUSIC_CLI_ROOT': str(self.root)}, self.runner(calls), script_path=self.skill / 'studio_status.py')
        self.assertEqual([call[0][2] for call in calls], ['schema'])
        commands = {item['command']: item for item in value['commands']}
        self.assertEqual(commands['app:state']['classification'], 'read')
        self.assertEqual(commands['song:delete']['classification'], 'delete')
        self.assertEqual(commands['song:delete']['required'], ['dir'])
        self.assertIn('schema --json', commands['song:delete']['example'])
        guides = {item['id']: item for item in value['guides']}
        self.assertIn('instrument-keyboards', guides)
        self.assertEqual(guides['instrument-keyboards']['category'], '악기')
        self.assertIn('피아노', guides['instrument-keyboards']['prompt'])
        self.assertIn('악기', guides['instrument-guitar-band']['avoidWhen'])
        self.assertIn('YuE', guides['yue-advanced']['title'])

    def test_instrument_guides_only_expose_schema_enum_values(self):
        schema = {'commands': [{
            'command': 'song:generate',
            'params': {'properties': {'parts': {'properties': {
                'instruments': {'items': {'enum': ['piano', 'electric guitar']}}
            }}}},
        }]}
        cards = _instrument_guides(schema)
        self.assertEqual([card['title'] for card in cards], ['piano', 'electric guitar'])
        self.assertEqual(cards[0]['category'], '악기')
        self.assertIn('건반', cards[0]['tags'])
        self.assertIn('기타·베이스', cards[1]['tags'])
        self.assertNotIn('guitar', {card['title'] for card in cards})


if __name__ == '__main__':
    unittest.main()
