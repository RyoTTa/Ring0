import json
import unittest
import test_automatic as fixtures


class HygieneTests(unittest.TestCase):
    setUp = fixtures.AutomaticTests.setUp
    capture = fixtures.AutomaticTests.capture
    prepare = fixtures.AutomaticTests.prepare
    result = fixtures.AutomaticTests.result
    def test_excluded_session_blocks_existing_and_inflight_data(self):
        self.capture()
        batch = self.prepare()
        self.archive.store.add('pnpm test fact', 1, 'auto session:ses_test')
        config = self.root / '.opencode/ring-memory.json'
        config.parent.mkdir(exist_ok=True)
        config.write_text(json.dumps({'excludedSessions': ['ses_test']}))
        self.assertFalse(self.capture()['accepted'])
        self.assertIsNone(self.prepare())
        self.assertFalse(self.archive.apply(batch['id'], 'owner', self.result())['applied'])
        self.assertEqual(self.archive.search('pnpm'), [])
        self.assertEqual(self.archive.store.recall('pnpm'), [])
        self.assertEqual(self.archive.store.snapshot()['ring1'], [])
        self.assertEqual(self.archive.status()['pending'], 0)

    def test_evaluation_quote_does_not_become_fact(self):
        self.capture([fixtures.user(text='평가용 예시: 이 프로젝트는 pnpm을 사용한다.')])
        batch = self.prepare()
        result = self.archive.apply(batch['id'], 'owner', self.result())
        self.assertEqual(result['skipped_facts'], 1)
        self.assertEqual(self.archive.store.rows(1), [])

    def test_recall_does_not_promote_and_supersession_preserves_history(self):
        store = self.archive.store
        old = store.add('deployment pending', 2)['id']
        new = store.add('deployment completed', 2)['id']
        for _ in range(5):
            store.recall('deployment', 2)
        store.dream()
        self.assertEqual(store.get(old)['ring'], 2)
        store.supersede(old, new, 'completion verified')
        self.assertEqual([r['id'] for r in store.recall('deployment', 2)], [new])
        self.assertEqual(len(store.rows(include_archived=True)), 2)
        self.assertEqual(json.loads(store.c.execute("SELECT detail FROM events WHERE action='superseded'").fetchone()[0])['by'], new)
        proposal = store.propose('protected kernel')
        store.resolve(proposal['id'])
        kernel = store.rows(0)[0]['id']
        with self.assertRaises(ValueError):
            store.supersede(kernel, new, 'not allowed')

    def test_archived_source_cannot_return_through_raw_recall(self):
        self.capture()
        batch = self.prepare()
        result = self.archive.apply(batch['id'], 'owner', self.result())
        self.archive.store.move(result['memory_ids'][0], archive=True)
        self.assertEqual(self.archive.search('pnpm'), [])
