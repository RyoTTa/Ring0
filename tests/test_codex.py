"""Codex hook bridge checks; all stores stay inside this checkout."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'plugins/claude'))
sys.path.insert(0, str(ROOT / 'plugins/codex'))
from automatic import Automatic
from codex_bridge import opted_in, transcript_messages


class CodexBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='.codex-test-', dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.environment = patch.dict(os.environ, {k: v for k, v in os.environ.items()
                                                   if k not in ('RING_ROOT', 'RING_DB')}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.archive = Automatic(self.project)
        self.addCleanup(self.archive.close)
        (self.project / '.codex').mkdir()
        (self.project / '.codex' / 'ring-memory.json').write_text('{"enabled": true}')

    def bridge(self, action, payload, env=None):
        script = str(ROOT / 'plugins/codex/codex_bridge.py')
        result = subprocess.run([sys.executable, script, action], input=json.dumps(payload),
                                text=True, capture_output=True,
                                env={**os.environ, **(env or {})})
        return result

    def base(self, **extra):
        payload = {'session_id': 'ses1', 'cwd': str(self.project),
                   'hook_event_name': 'SessionStart', 'model': 'test'}
        payload.update(extra)
        return payload

    def test_parser_accepts_shapes_and_skips_tool_calls(self):
        path = self.project / 'rollout.jsonl'
        path.write_text('\n'.join([
            json.dumps({'role': 'user', 'content': [{'type': 'input_text', 'text': 'remember pnpm'}]}),
            json.dumps({'role': 'assistant', 'message': 'pnpm 확인했다.'}),
            json.dumps({'role': 'assistant', 'type': 'function_call', 'content': 'ls'}),
            'not json at all',
        ]) + '\n')
        messages = transcript_messages(str(path))
        self.assertEqual([(m['kind'], m['text']) for m in messages],
                         [('user', 'remember pnpm'), ('assistant', 'pnpm 확인했다.')])

    def test_opt_in_requires_marker(self):
        self.assertEqual(opted_in(str(self.project)), self.project)
        self.assertEqual(opted_in(str(self.project / 'sub' / 'dir')), self.project)
        with tempfile.TemporaryDirectory(prefix='.codex-outside-', dir=ROOT) as outside:
            self.assertIsNone(opted_in(outside))

    def test_context_start_injects_snapshot(self):
        with self.archive.c:
            self.archive.store.add('이 프로젝트는 pnpm을 사용한다.', 1, kind='decision', target='package manager')
        result = self.bridge('context-start', self.base())
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        self.assertEqual(out['hookSpecificOutput']['hookEventName'], 'SessionStart')
        self.assertIn('pnpm', out['hookSpecificOutput']['additionalContext'])

    def test_outside_opt_in_is_silent(self):
        with tempfile.TemporaryDirectory(prefix='.codex-outside-', dir=ROOT) as outside:
            result = self.bridge('context-start', self.base(cwd=outside))
        self.assertEqual((result.returncode, result.stdout), (0, ''))

    def test_capture_queues_and_digest_applies_mocked_exec(self):
        path = self.project / 'rollout.jsonl'
        path.write_text(json.dumps({'role': 'user', 'content': '이 프로젝트는 pnpm을 사용한다.'}) + '\n')
        cap = self.bridge('capture', self.base(hook_event_name='SessionEnd', transcript_path=str(path)))
        self.assertEqual(cap.returncode, 0, cap.stderr)
        status = self.bridge('status', self.base())
        self.assertGreaterEqual(json.loads(status.stdout)['pending'], 1)
        # The queued id depends on parser output; accept whatever it stored.
        with self.archive.c:
            pending = self.archive.prepare('ses1', 'owner')
        self.assertIsNotNone(pending)
        fact_id = pending['records'][0]['id']
        with self.archive.c:
            self.archive.c.execute('UPDATE history.batches SET expires=0')
        summary = json.dumps({'summary': 'pnpm 사용 확인.', 'facts': [
            {'content': '이 프로젝트는 pnpm을 사용한다.', 'message_id': fact_id,
             'quote': '이 프로젝트는 pnpm을 사용한다.', 'kind': 'decision', 'target': 'package manager'}]})
        bindir = self.project / 'bin'
        bindir.mkdir()
        fake = bindir / 'codex'
        fake.write_text('#!/bin/sh\nprintf \'%s\' "$CODEX_MOCK_JSON"\n')
        fake.chmod(0o755)
        env = {'PATH': str(bindir) + os.pathsep + os.environ.get('PATH', ''),
               'CODEX_MOCK_JSON': summary}
        result = self.bridge('digest', self.base(), env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['applied'])
        rows = self.archive.store.rows(1)
        self.assertEqual((rows[0]['kind'], rows[0]['target']), ('decision', 'package manager'))

    def test_digest_without_binary_stays_pending(self):
        path = self.project / 'rollout.jsonl'
        path.write_text(json.dumps({'role': 'user', 'content': '이 프로젝트는 pnpm을 사용한다.'}) + '\n')
        self.bridge('capture', self.base(transcript_path=str(path)))
        bindir = self.project / 'emptybin'
        bindir.mkdir()
        env = {'PATH': str(bindir)}
        result = self.bridge('digest', self.base(), env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        self.assertFalse(out['applied'])
        self.assertIn('PATH', out['reason'])


if __name__ == '__main__':
    unittest.main()
