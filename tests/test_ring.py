"""Data-integrity and end-to-end checks; all test stores stay inside this checkout."""
import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from store import DAY, RING0_CAP, SCHEMA, Store, paths
from ring import main


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='.ring-test-', dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.environment = patch.dict(os.environ, {k: v for k, v in os.environ.items()
                                                   if k not in ('RING_ROOT', 'RING_DB')}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.store = Store(self.project)
        self.addCleanup(self.store.close)

    def cli(self, *args, success=True):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(['--root', str(self.project), '--json', *map(str, args)])
        self.assertEqual(code, 0 if success else 1, stderr.getvalue())
        return json.loads(stdout.getvalue() if success else stderr.getvalue())

    def save(self, content, ring=1, tags=''):
        with self.store.c:
            return self.store.add(content, ring, tags)['id']

    def kernel(self, content):
        with self.store.c:
            proposal = self.store.propose(content)
            self.store.resolve(proposal['id'])
        return self.store.rows(0)[-1]['id']

    def test_default_save_duplicate_and_legacy_arguments(self):
        first = self.cli('remember', '짧은 답변을 선호한다', '--tags', 'preference')
        second = self.cli('remember', '--content', '짧은 답변을 선호한다', '--ring', '1')
        self.assertEqual(first['ring'], 1)
        self.assertEqual(first['id'], second['id'])
        self.assertTrue(second['existing'])
        result = self.cli('recall', '--query', '답변')
        self.assertEqual([r['id'] for r in result], [first['id']])

    def test_plain_text_queries_punctuation_korean_and_tags(self):
        expected = self.save('이 프로젝트에서는 pnpm을 사용한다', tags='패키지 project')
        self.save('Use Docker for deployment')
        for query in ('pnpm?', 'pnpm "package" OR', 'pnpm을', '패키지', '"pnpm" -unknown:'):
            self.assertEqual(self.cli('recall', query)[0]['id'], expected)
        self.assertEqual(self.cli('recall', 'no-matching-word'), [])

    def test_multi_term_relevance_and_keyword_fallback(self):
        preferred = self.save('deploy pnpm package')
        self.save('deploy Docker')
        self.assertEqual(self.cli('recall', 'pnpm deploy')[0]['id'], preferred)
        self.store.fts = False
        with self.store.c:
            self.assertEqual(self.store.recall('pnpm?')[0]['id'], preferred)

    def test_blank_text_and_unknown_ids_are_errors(self):
        self.assertIn('empty', self.cli('remember', '  ', success=False)['error'])
        self.assertIn('No active memory', self.cli('forget', 999, success=False)['error'])
        self.assertIn('No active memory', self.cli('promote', 999, success=False)['error'])
        self.assertIn('Unknown proposal', self.cli('approve', 999, success=False)['error'])

    def test_snapshot_includes_every_kernel_entry(self):
        for number in range(25):
            self.kernel(f'Kernel fact {number}')
        self.assertEqual(len(self.cli('snapshot')['ring0']), 25)

    def test_kernel_proposal_approval_cap_and_rejection(self):
        proposal = self.cli('propose', 'a' * RING0_CAP)
        self.assertEqual(self.cli('status')['ring0_chars'], 0)
        self.cli('approve', '--id', proposal['id'])
        extra = self.cli('propose', 'b')
        self.assertIn('2001/2000', self.cli('approve', extra['id'], success=False)['error'])
        self.assertEqual(self.cli('proposals')[0]['status'], 'pending')
        self.cli('reject', extra['id'])
        self.assertEqual(self.cli('proposals'), [])
        self.assertIn('already', self.cli('approve', proposal['id'], success=False)['error'])

    def test_kernel_moves_blocked_and_replacement_retains_history(self):
        memory_id = self.kernel('a' * RING0_CAP)
        for command in ('forget', 'demote'):
            self.assertIn('protected', self.cli(command, memory_id, success=False)['error'])
        replacement = self.cli('propose', 'b' * RING0_CAP, '--replace', memory_id)
        self.cli('approve', replacement['id'])
        self.assertEqual(self.cli('snapshot')['ring0'][0]['content'], 'b' * RING0_CAP)
        self.assertEqual(len(self.cli('list', '--all')), 2)
        self.assertEqual(self.cli('status')['archived'], 1)
        current = self.cli('snapshot')['ring0'][0]['id']
        removal = self.cli('propose', '--remove', current)
        self.cli('approve', removal['id'])
        self.assertEqual(self.cli('snapshot')['ring0'], [])
        self.assertEqual(len(self.cli('list', '--all')), 2)

    def test_forget_removes_from_recall_but_preserves_record(self):
        memory_id = self.save('old preference')
        self.cli('forget', memory_id)
        self.assertEqual(self.cli('recall', 'preference'), [])
        self.assertEqual(self.cli('list'), [])
        self.assertEqual(self.cli('list', '--all')[0]['content'], 'old preference')
        self.assertIn('old preference', (self.project / '.agent/memory/archive.md').read_text())

    def test_export_contains_more_than_fifty_entries_and_round_trips(self):
        for number in range(65):
            self.save(f'Fact {number}\nsecond line', tags='project')
        self.kernel('Core fact')
        self.cli('propose', 'Pending fact')
        self.cli('forget', 1)
        self.cli('recall', 'Fact')
        self.cli('export')
        folder = self.project / '.agent/memory'
        self.assertIn('[65] Fact 64', (folder / 'ring1.md').read_text())
        state = json.loads((folder / 'state.json').read_text())
        self.assertEqual(len(state['memories']), 66)
        with tempfile.TemporaryDirectory(prefix='.ring-restore-', dir=ROOT) as restored:
            output = self.cli('--root', restored, 'restore', folder / 'state.json')
            self.assertEqual(output['restored'], 66)
            copy = json.loads((Path(restored) / '.agent/memory/state.json').read_text())
            self.assertEqual(copy, state)
        self.assertIn('empty store', self.cli('restore', folder / 'state.json', success=False)['error'])

    def test_malformed_restore_rolls_back_partial_inserts(self):
        backup = self.project / 'malformed.json'
        backup.write_text(json.dumps({'version': 1, 'memories': [
            {'id': 1, 'ring': 1, 'content': 'valid', 'tags': '', 'created_at': 1, 'updated_at': 1,
             'access_count': 0, 'salience': 1, 'archived_at': None, 'last_access': None, 'last_decay': None},
            {'id': 2}], 'proposals': [], 'events': []}))
        self.cli('restore', backup, success=False)
        self.assertEqual(self.cli('list', '--all'), [])

    def test_dream_dry_run_and_elapsed_decay_are_idempotent(self):
        memory_id = self.save('old episode', 2)
        now = int(time.time())
        with self.store.c:
            self.store.c.execute('UPDATE memories SET updated_at=? WHERE id=?', (now - 61 * DAY, memory_id))
        dry = self.cli('dream', '--dry-run')
        self.assertTrue(dry['actions'])
        self.assertEqual(self.store.get(memory_id)['salience'], 1)
        self.assertFalse((self.project / '.agent/memory').exists())
        self.cli('dream')
        first = self.store.get(memory_id)
        self.cli('dream')
        self.assertAlmostEqual(first['salience'], 0.81)
        self.assertEqual(self.store.get(memory_id), first)

    def test_restore_rejects_metadata_that_would_break_future_reads(self):
        memory_id = self.save('valid memory')
        self.cli('export')
        state = json.loads((self.project / '.agent/memory/state.json').read_text())
        for field, bad_value in (('salience', 'not-a-number'), ('updated_at', -1), ('tags', None)):
            with self.subTest(field=field), tempfile.TemporaryDirectory(prefix='.ring-restore-', dir=ROOT) as target:
                changed = json.loads(json.dumps(state))
                changed['memories'][0][field] = bad_value
                backup = Path(target) / 'invalid.json'
                backup.write_text(json.dumps(changed))
                self.assertIn('Invalid', self.cli('--root', target, 'restore', backup, success=False)['error'])
                self.assertEqual(self.cli('--root', target, 'list', '--all'), [])
        self.assertEqual(self.store.get(memory_id)['content'], 'valid memory')

    def test_pin_is_a_tag_not_a_substring(self):
        pin = self.save('pinned episode', 2, 'project,pin')
        unpinned = self.save('shopping episode', 2, 'shopping')
        with self.store.c:
            self.store.c.execute('UPDATE memories SET updated_at=?', (int(time.time()) - 31 * DAY,))
        self.cli('dream')
        self.assertEqual(self.store.get(pin)['salience'], 1)
        self.assertAlmostEqual(self.store.get(unpinned)['salience'], 0.9)

    def test_cold_demotions_do_not_immediately_repromote(self):
        memory_id = self.save('cold long-term')
        with self.store.c:
            self.store.c.execute('UPDATE memories SET updated_at=?, access_count=9 WHERE id=?',
                                 (int(time.time()) - 91 * DAY, memory_id))
        self.cli('dream')
        self.cli('dream')
        self.assertEqual(self.store.get(memory_id)['ring'], 2)
        for _ in range(3):
            self.cli('recall', 'cold', '--ring', 2)
        self.cli('dream')
        self.assertEqual(self.store.get(memory_id)['ring'], 1)

    def test_recent_recall_keeps_old_long_term_memory_active(self):
        memory_id = self.save('useful long-term')
        with self.store.c:
            self.store.c.execute('UPDATE memories SET updated_at=?', (int(time.time()) - 100 * DAY,))
        self.cli('recall', 'useful')
        self.cli('dream')
        self.assertEqual(self.store.get(memory_id)['ring'], 1)

    def test_duplicate_consolidation_keeps_content_and_kernel(self):
        memory_id = self.save('duplicate')
        self.kernel('duplicate kernel')
        self.kernel('duplicate kernel')
        with self.store.c:
            self.store.c.execute('INSERT INTO memories(ring,content,tags,created_at,updated_at) '
                                 'SELECT ring,content,tags,created_at,updated_at FROM memories WHERE id=?',
                                 (memory_id,))
        before = self.cli('list', '--all')
        self.cli('dream')
        self.assertEqual(len(self.cli('list', '--all')), len(before))
        self.assertEqual(len(self.cli('list', '--ring', 0)), 2)
        self.assertEqual(len(self.cli('list', '--ring', 1)), 1)
        self.assertEqual(self.cli('status')['archived'], 1)

    def test_original_database_is_migrated_without_losing_ids(self):
        with tempfile.TemporaryDirectory(prefix='.ring-legacy-', dir=ROOT) as legacy:
            path = Path(legacy) / '.agent/rings.db'
            path.parent.mkdir()
            c = sqlite3.connect(path)
            c.executescript(SCHEMA)
            c.execute("INSERT INTO memories(id,ring,content,created_at,updated_at) VALUES(42,1,'legacy fact',1,1)")
            c.execute("INSERT INTO proposals(id,content,created_at) VALUES(12,'legacy kernel',1)")
            c.commit()
            c.close()
            self.assertEqual(self.cli('--root', legacy, 'recall', 'legacy')[0]['id'], 42)
            self.cli('--root', legacy, 'approve', 12)
            snapshot = self.cli('--root', legacy, 'snapshot')
            self.assertEqual(snapshot['ring0'][0]['content'], 'legacy kernel')

    def test_nearest_project_and_explicit_root_resolution(self):
        nested = self.project / 'packages/app'
        nested.mkdir(parents=True)
        with patch('pathlib.Path.cwd', return_value=nested):
            self.assertEqual(paths()[0], self.project)
        with patch.dict(os.environ, {'RING_ROOT': str(self.project), 'RING_DB': 'custom/memory.db'}):
            self.assertEqual(paths()[1], self.project / 'custom/memory.db')
        custom = self.project / 'separate/data.db'
        with patch.dict(os.environ, {'RING_DB': str(custom)}):
            self.assertEqual(paths(), (custom.parent, custom))

    def test_cli_from_nested_directory_and_installed_script(self):
        nested = self.project / 'packages/app'
        nested.mkdir(parents=True)
        process = subprocess.run([sys.executable, str(ROOT / 'scripts/ring.py'), 'remember', 'nested fact', '--json'],
                                 cwd=nested, text=True, capture_output=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(self.cli('recall', 'nested')[0]['content'], 'nested fact')
        self.assertFalse((nested / '.agent').exists())

    def test_git_opt_in_preserves_unrelated_staging_and_handles_ignore(self):
        def git(*args):
            result = subprocess.run(['git', '-C', str(self.project), *args], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout
        git('init', '-q')
        (self.project / '.gitignore').write_text('.agent/\n*.db\n')
        (self.project / 'user.txt').write_text('initial')
        git('add', '.gitignore', 'user.txt')
        git('-c', 'user.name=Test', '-c', 'user.email=test@example.com', 'commit', '-qm', 'initial')
        initial = git('rev-parse', 'HEAD')
        (self.project / 'user.txt').write_text('user work')
        git('add', 'user.txt')
        self.cli('remember', 'no automatic commit')
        self.assertEqual(git('rev-parse', 'HEAD'), initial)
        self.cli('export', '--commit')
        committed = git('show', '--pretty=format:', '--name-only', 'HEAD')
        self.assertIn('.agent/memory/state.json', committed)
        self.assertNotIn('user.txt', committed)
        self.assertNotIn('rings.db', committed)
        self.assertEqual(git('diff', '--cached', '--name-only').strip(), 'user.txt')

    def test_commit_failure_reports_saved_database(self):
        # This temporary folder sits within the checkout's Git repo, so create a
        # malformed local .git marker to keep the operation away from the parent.
        (self.project / '.git').write_text('gitdir: missing-directory\n')
        result = self.cli('remember', 'saved despite git failure', '--commit', success=False)
        self.assertIn('Database saved', result['error'])
        self.assertEqual(len(self.cli('recall', 'saved despite')), 1)

    def test_installer_repeat_conflict_dry_run_and_global_scope(self):
        project = self.project / 'my project'
        project.mkdir()
        def install(*args, success=True, env=None):
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/install.py'), *map(str, args)],
                                    cwd=project, text=True, capture_output=True, env=env)
            self.assertEqual(result.returncode, 0 if success else 1, result.stderr)
            return result
        install('--project', project, '--dry-run')
        self.assertFalse((project / '.opencode').exists())
        install('--project', project)
        install('--project', project)
        command = project / '.opencode/commands/remember.md'
        command.write_text('user customization')
        install('--project', project, success=False)
        self.assertEqual(command.read_text(), 'user customization')
        install('--project', project, '--force')
        self.assertIn('$ARGUMENTS', command.read_text())
        skill_script = project / '.opencode/skills/ring-memory/scripts/ring.py'
        result = subprocess.run([sys.executable, str(skill_script), '--root', str(project),
                                 'remember', 'installed works', '--json'], cwd=project, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((project / '.agent/rings.db').exists())
        self.assertFalse((skill_script.parent / '.agent').exists())
        config = self.project / 'config'
        install('--global', env={**os.environ, 'XDG_CONFIG_HOME': str(config)})
        self.assertTrue((config / 'opencode/skills/ring-memory/SKILL.md').exists())


if __name__ == '__main__':
    unittest.main()
