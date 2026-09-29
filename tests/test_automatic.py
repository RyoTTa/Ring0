import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from automatic import Automatic, api, belongs, pages, scope, sync


def user(mid='msg_user', text='이 프로젝트는 pnpm을 사용한다.'):
    return {'id': mid, 'type': 'user', 'text': text, 'time': {'created': 1}}


def assistant(mid='msg_reply', done=True):
    return {'id': mid, 'type': 'assistant', 'time': {'created': 2, **({'completed': 3} if done else {})},
            'content': [{'type': 'text', 'text': 'pnpm 설정을 확인했다.'},
                        {'type': 'tool', 'name': 'shell', 'state': {'status': 'completed', 'input': {'command': 'pnpm test'},
                                                                  'content': [{'type': 'text', 'text': 'passed'}]}}]}


class AutomaticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='.auto-test-', dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = Automatic(self.root)
        self.addCleanup(self.archive.close)
        self.session = {'id': 'ses_test', 'location': {'directory': str(self.root)}, 'time': {'updated': 3}}

    def capture(self, messages=None, session=None):
        with self.archive.c:
            return self.archive.capture(session or self.session, messages or [user(), assistant()])

    def prepare(self, owner='owner'):
        with self.archive.c:
            return self.archive.prepare(self.session['id'], owner)

    def result(self):
        return {'summary': 'pnpm 설정과 테스트를 확인했다.', 'facts': [
            {'content': '이 프로젝트는 pnpm을 사용한다.', 'message_id': 'msg_user', 'quote': '이 프로젝트는 pnpm을 사용한다.'}]}

    def test_isolation_rejects_siblings_nested_projects_and_symlinks(self):
        outside = self.root.parent / (self.root.name + '-other')
        self.assertFalse(belongs(self.root, outside))
        nested = self.root / 'nested'
        nested.mkdir()
        self.assertTrue(belongs(self.root, nested))
        (nested / '.git').write_text('gitdir: placeholder')
        self.assertFalse(belongs(self.root, nested))
        (self.root / 'escape').symlink_to(self.root.parent, target_is_directory=True)
        self.assertFalse(belongs(self.root, self.root / 'escape'))
        wrong = {**self.session, 'location': {'directory': str(outside)}}
        self.assertFalse(self.capture(session=wrong)['accepted'])
        self.assertEqual(self.archive.status()['records'], 0)

    def test_environment_cannot_redirect_automatic_memory(self):
        with patch.dict(os.environ, {'RING_DB': str(self.root / 'wrong.db'), 'RING_ROOT': '/not-this-project'}):
            other = Automatic(self.root)
            self.assertEqual(other.store.path, self.root / '.agent/rings.db')
            other.close()
        self.assertFalse((self.root / 'wrong.db').exists())

    def test_capture_keeps_full_payload_and_updates_without_duplicates(self):
        payload = assistant()
        payload['content'][0]['text'] = 'long-output ' * 2000
        first = self.capture([user(), payload])
        second = self.capture([user(), payload])
        self.assertEqual(first['changed'], 2)
        self.assertEqual(second['changed'], 0)
        self.assertEqual(self.archive.status()['records'], 2)
        saved = self.archive.c.execute("SELECT payload FROM history.records WHERE kind='assistant'").fetchone()[0]
        self.assertEqual(json.loads(saved), payload)
        self.assertLessEqual(len(self.prepare()['records'][1]['text']), 4000)

    def test_moved_sessions_do_not_import_other_project_history(self):
        result = self.capture([user(), {'id': 'msg_move', 'type': 'location-switched'}])
        self.assertFalse(result['accepted'])
        self.assertEqual(self.archive.status()['records'], 0)

    def test_summary_lease_and_application_are_idempotent(self):
        self.capture()
        batch = self.prepare()
        self.assertIsNone(self.prepare('another-worker'))
        with self.archive.c:
            result = self.archive.apply(batch['id'], 'owner', self.result())
            repeat = self.archive.apply(batch['id'], 'owner', self.result())
        self.assertTrue(result['applied'])
        self.assertFalse(repeat['applied'])
        self.assertEqual(len(self.archive.store.rows(1)), 1)
        self.assertEqual(len(self.archive.store.rows(2)), 1)
        self.assertEqual(self.archive.store.rows(0), [])
        self.assertEqual(self.archive.status()['pending'], 0)

    def test_facts_require_verbatim_user_evidence(self):
        self.capture()
        batch = self.prepare()
        result = self.result()
        result['facts'].extend([
            {'content': 'made-up fact', 'message_id': 'msg_reply', 'quote': 'pnpm 설정을 확인했다.'},
            {'content': 'another made-up fact', 'message_id': 'msg_user', 'quote': 'not in user text'},
            {'content': 'invalid', 'message_id': 'msg_user', 'quote': ''}])
        with self.archive.c:
            applied = self.archive.apply(batch['id'], 'owner', result)
        self.assertEqual(applied['skipped_facts'], 3)
        self.assertEqual(len(self.archive.store.rows(1)), 1)

    def test_source_edits_invalidate_inflight_summary(self):
        self.capture()
        batch = self.prepare()
        self.capture([user(text='이 프로젝트는 npm으로 변경했다.'), assistant()])
        with self.assertRaisesRegex(ValueError, 'Source changed'), self.archive.c:
            self.archive.apply(batch['id'], 'owner', self.result())
        self.assertEqual(self.archive.store.rows(), [])

    def test_crashed_summary_leases_expire_and_unfinished_replies_wait(self):
        self.capture([user(), assistant(done=False)])
        batch = self.prepare()
        self.assertEqual([r['type'] for r in batch['records']], ['user'])
        with self.archive.c:
            self.archive.c.execute('UPDATE history.batches SET expires=?', (int(time.time()) - 1,))
        recovered = self.prepare('restart')
        self.assertEqual(recovered['id'], batch['id'])
        with self.archive.c:
            self.archive.release(batch['id'], 'restart')
        self.assertIsNotNone(self.prepare('next'))

    def test_context_budget_kernel_and_once_per_turn_recalls(self):
        with self.archive.c:
            proposal = self.archive.store.propose('k' * 2000)
            self.archive.store.resolve(proposal['id'])
            memory_id = self.archive.store.add('pnpm project', 2)['id']
            self.archive.store.add('pnpm ' + 'x' * 6000, 1)
            first = self.archive.context('ses_current', 'msg_turn1', 'pnpm', 3000)
            repeat = self.archive.context('ses_current', 'msg_turn1', 'pnpm', 3000)
        self.assertIn('k' * 2000, first['text'])
        self.assertLessEqual(len(first['text']), 3000)
        self.assertTrue(first['first_in_turn'])
        self.assertFalse(repeat['first_in_turn'])
        self.assertEqual(self.archive.store.get(memory_id)['access_count'], 1)

    def test_other_session_history_is_retrievable_before_summarization(self):
        self.capture()
        with self.archive.c:
            context = self.archive.context('ses_new', 'msg_new', 'pnpm')
        self.assertIn('ses_test/msg_user', context['text'])
        self.assertIn('pnpm', self.archive.search('pnpm')[0]['text'])

    def test_paginated_backfill_does_not_fetch_sibling_messages(self):
        sibling = {**self.session, 'id': 'ses_other', 'location': {'directory': str(self.root.parent)}}
        seen = []
        def request(path):
            seen.append(path)
            if path.startswith('/api/session?'):
                return {'data': [self.session, sibling], 'cursor': {}}
            if path == '/api/session/ses_test':
                return {'data': self.session}
            if 'cursor=page2' in path:
                return {'data': [assistant()], 'cursor': {}}
            if '/message?' in path:
                return {'data': [user()], 'cursor': {'next': 'page2'}}
            raise AssertionError(path)
        result = sync(self.archive, request=request)
        self.assertEqual(result['sessions'], ['ses_test'])
        self.assertFalse(any('ses_other/' in path for path in seen))
        self.assertEqual(self.archive.status()['records'], 2)
        seen.clear()
        sync(self.archive, request=request)
        self.assertEqual(len(seen), 1)  # Unchanged sessions need no full-history reread.

    def test_context_capture_does_not_hide_older_history_from_backfill(self):
        self.capture([assistant()])
        def request(path):
            if path.startswith('/api/session?'):
                return {'data': [self.session], 'cursor': {}}
            if '/message?' in path:
                return {'data': [user(), assistant()], 'cursor': {}}
            return {'data': self.session}
        sync(self.archive, request=request)
        self.assertEqual(self.archive.status()['records'], 2)

    def test_scope_rejects_history_from_a_prior_project(self):
        def request(path):
            if '/message?' in path:
                self.assertIn('type=location-switched', path)
                return {'data': [{'type': 'location-switched', 'location': self.session['location'],
                                  'previous': {'location': {'directory': str(self.root.parent)}}}], 'cursor': {}}
            return {'data': self.session}
        self.assertFalse(scope(self.root, 'ses_test', request)['accepted'])

    def test_auto_install_is_project_only_and_preserves_settings(self):
        install = [sys.executable, str(ROOT / 'scripts/install.py')]
        result = subprocess.run([*install, '--project', str(self.root), '--auto'], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        plugin = self.root / '.opencode/plugins/ring-memory'
        self.assertTrue((plugin / 'index.js').exists())
        self.assertTrue((plugin / 'runtime.js').exists())
        config = self.root / '.opencode/ring-memory.json'
        config.write_text('{"enabled":false}')
        repeat = subprocess.run([*install, '--project', str(self.root), '--auto', '--force'], text=True, capture_output=True)
        self.assertEqual(repeat.returncode, 0, repeat.stderr)
        self.assertEqual(json.loads(config.read_text()), {'enabled': False})
        global_result = subprocess.run([*install, '--global', '--auto'], text=True, capture_output=True)
        self.assertEqual(global_result.returncode, 2)
        self.assertIn('project-local', global_result.stderr)

    def test_api_uses_file_backed_stdout_for_large_history(self):
        payload = {'data': [{'text': '대용량 도구 결과' * 100000}], 'cursor': {}}
        def command(args, **kwargs):
            self.assertNotEqual(kwargs['stdout'], subprocess.PIPE)
            kwargs['stdout'].write(json.dumps(payload, ensure_ascii=False))
            return subprocess.CompletedProcess(args, 0, stderr='')
        with patch('automatic.subprocess.run', side_effect=command):
            self.assertEqual(api('/api/session/test/message'), payload)


if __name__ == '__main__':
    unittest.main()
