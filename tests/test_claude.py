"""Claude Code hook bridge checks; all stores stay inside this checkout."""
import contextlib
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
from automatic import Automatic
from claude_bridge import queue, snapshot_text, transcript_messages


def transcript(*entries):
    lines = []
    for i, (kind, text) in enumerate(entries):
        if kind == 'user':
            lines.append(json.dumps({'type': 'user', 'uuid': f'u{i}',
                                     'message': {'role': 'user', 'content': text}}))
        else:
            lines.append(json.dumps({'type': 'assistant', 'uuid': f'a{i}',
                                     'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': text}]}}))
    return '\n'.join(lines) + '\n'


class ClaudeBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='.claude-test-', dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.environment = patch.dict(os.environ, {k: v for k, v in os.environ.items()
                                                   if k not in ('RING_ROOT', 'RING_DB')}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.archive = Automatic(self.project)
        self.addCleanup(self.archive.close)

    def bridge(self, action, payload=None):
        script = str(ROOT / 'scripts/claude_bridge.py')
        stdin = json.dumps(payload or {}) if payload is not None else '{}'
        result = subprocess.run([sys.executable, script, '--root', str(self.project), action],
                                input=stdin, text=True, capture_output=True)
        return result

    def test_transcript_parse_skips_tool_results(self):
        path = self.project / 't.jsonl'
        path.write_text(transcript(('user', 'remember pnpm'), ('assistant', 'ok')) +
                        json.dumps({'type': 'user', 'uuid': 'tool1',
                                    'message': {'role': 'user', 'content': [{'type': 'tool_result', 'content': 'x'}]}}) + '\n')
        messages = transcript_messages(str(path))
        self.assertEqual([(m['kind'], m['text']) for m in messages],
                         [('user', 'remember pnpm'), ('assistant', 'ok')])

    def test_queue_dedupes_and_rejects_outside_project(self):
        with self.archive.c:
            first = queue(self.archive, 'ses1', str(self.project),
                          [{'id': 'u0', 'kind': 'user', 'text': 'remember pnpm'}])
            second = queue(self.archive, 'ses1', str(self.project),
                           [{'id': 'u0', 'kind': 'user', 'text': 'remember pnpm'}])
        self.assertEqual((first['changed'], second['changed']), (1, 0))
        with self.archive.c:
            outside = queue(self.archive, 'ses1', str(self.project.parent),
                            [{'id': 'u9', 'kind': 'user', 'text': 'nope'}])
        self.assertFalse(outside['accepted'])

    def test_context_start_injects_snapshot_and_prompt_recalls(self):
        with self.archive.c:
            self.archive.store.add('이 프로젝트는 pnpm을 사용한다.', 1, kind='decision', target='package manager')
            self.archive.store.set_state('goal', 'ship it')
        start = self.bridge('context-start', {'session_id': 's', 'cwd': str(self.project)})
        self.assertEqual(start.returncode, 0, start.stderr)
        context = json.loads(start.stdout)['additionalContext']
        self.assertIn('pnpm', context)
        self.assertIn('ship it', context)
        prompt = self.bridge('context-prompt', {'session_id': 's', 'cwd': str(self.project), 'prompt': 'pnpm 뭐였지'})
        self.assertEqual(prompt.returncode, 0, prompt.stderr)
        self.assertIn('pnpm', json.loads(prompt.stdout)['additionalContext'])

    def test_capture_round_trip_and_digest_without_model(self):
        path = self.project / 't.jsonl'
        path.write_text(transcript(('user', '이 프로젝트는 pnpm을 사용한다.'), ('assistant', '확인했다.')))
        cap = self.bridge('capture', {'session_id': 'ses1', 'cwd': str(self.project), 'transcript_path': str(path)})
        self.assertEqual(cap.returncode, 0, cap.stderr)
        status = self.bridge('status')
        self.assertGreaterEqual(json.loads(status.stdout)['pending'], 1)
        # No `claude` binary here: digest must leave records pending, honestly.
        with patch('claude_bridge.shutil.which', return_value=None):
            from claude_bridge import digest
            with self.archive.c:
                result = digest(self.archive, 'ses1')
        self.assertFalse(result['applied'])
        self.assertIn('PATH', result['reason'])

    def test_digest_applies_mocked_summarizer(self):
        path = self.project / 't.jsonl'
        path.write_text(transcript(('user', '이 프로젝트는 pnpm을 사용한다.'), ('assistant', '확인했다.')))
        with self.archive.c:
            queue(self.archive, 'ses1', str(self.project), transcript_messages(str(path)))
        summary = json.dumps({'summary': 'pnpm 사용 확인.', 'facts': [
            {'content': '이 프로젝트는 pnpm을 사용한다.', 'message_id': 'u0',
             'quote': '이 프로젝트는 pnpm을 사용한다.', 'kind': 'decision', 'target': 'package manager'}]})
        proc = subprocess.CompletedProcess(['claude', '-p'], 0, stdout=summary, stderr='')
        with patch('claude_bridge.shutil.which', return_value='/usr/bin/claude'), \
             patch('claude_bridge.subprocess.run', return_value=proc):
            from claude_bridge import digest
            with self.archive.c:
                result = digest(self.archive, 'ses1')
        self.assertTrue(result['applied'])
        rows = self.archive.store.rows(1)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['kind'], rows[0]['target']), ('decision', 'package manager'))
        self.assertTrue(rows[0]['source'].startswith('ses1/'))

    def test_install_auto_hooks_are_idempotent(self):
        install = [sys.executable, str(ROOT / 'scripts/install.py')]
        target = self.project / 'claude-proj'
        target.mkdir()
        for _ in range(2):
            result = subprocess.run([*install, '--host', 'claude', '--project', str(target), '--auto', '--force'],
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        settings = json.loads((target / '.claude/settings.json').read_text())
        starts = [e for e in settings['hooks']['SessionStart'] if 'context-start' in json.dumps(e)]
        self.assertEqual(len(starts), 1)


if __name__ == '__main__':
    unittest.main()
