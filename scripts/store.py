"""Dependency-free storage shared by the Ring0 CLI and maintenance command."""
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import time

RING0_CAP = 2000
DAY = 86400
SCHEMA = """
CREATE TABLE IF NOT EXISTS memories(
 id INTEGER PRIMARY KEY, ring INTEGER, content TEXT,
 tags TEXT DEFAULT '', created_at INTEGER, updated_at INTEGER,
 access_count INTEGER DEFAULT 0, salience REAL DEFAULT 1.0);
CREATE TABLE IF NOT EXISTS proposals(
 id INTEGER PRIMARY KEY, content TEXT, tags TEXT DEFAULT '',
 status TEXT DEFAULT 'pending', created_at INTEGER);
CREATE TABLE IF NOT EXISTS events(
 id INTEGER PRIMARY KEY, memory_id INTEGER, action TEXT,
 detail TEXT, created_at INTEGER);
"""
FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS mem_fts USING fts5(content, content='memories', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS mem_ai AFTER INSERT ON memories BEGIN
 INSERT INTO mem_fts(rowid, content) VALUES (new.id, new.content); END;
CREATE TRIGGER IF NOT EXISTS mem_ad AFTER DELETE ON memories BEGIN
 INSERT INTO mem_fts(mem_fts, rowid, content) VALUES('delete', old.id, old.content); END;
CREATE TRIGGER IF NOT EXISTS mem_au AFTER UPDATE ON memories BEGIN
 INSERT INTO mem_fts(mem_fts, rowid, content) VALUES('delete', old.id, old.content);
 INSERT INTO mem_fts(rowid, content) VALUES (new.id, new.content); END;
"""


def paths(root=None):
    """Resolve from the user's project, never from the installed skill directory."""
    root = root or os.environ.get('RING_ROOT')
    custom_db = os.environ.get('RING_DB')
    if root:
        root = Path(root).expanduser().resolve()
    elif custom_db:
        db = Path(custom_db).expanduser().resolve()
        root = db.parent.parent if db.parent.name == '.agent' else db.parent
        return root, db
    else:
        cwd = Path.cwd().resolve()
        root = next((p for p in (cwd, *cwd.parents)
                     if (p / '.git').exists() or (p / '.agent/rings.db').exists()), cwd)
    db = Path(custom_db).expanduser() if custom_db else Path('.agent/rings.db')
    return root, (db if db.is_absolute() else root / db).resolve()


def text(value):
    value = value.strip()
    if not value:
        raise ValueError('Text cannot be empty.')
    return value


def pinned(tags):
    return 'pin' in re.split(r'[\s,]+', tags.lower())


class Store:
    def __init__(self, root=None):
        self.root, self.path = paths(root)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.c = sqlite3.connect(self.path, timeout=15)
        self.c.row_factory = sqlite3.Row
        self.c.executescript(SCHEMA)
        # Additive migration preserves databases created by the original skill.
        self.c.execute('BEGIN IMMEDIATE')
        for table, columns in {
            'memories': {'archived_at': 'INTEGER', 'last_access': 'INTEGER',
                         'last_decay': 'INTEGER'},
            'proposals': {'action': "TEXT DEFAULT 'add'", 'target_id': 'INTEGER'},
        }.items():
            existing = {r['name'] for r in self.c.execute(f'PRAGMA table_info({table})')}
            for name, definition in columns.items():
                if name not in existing:
                    self.c.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
        self.c.commit()
        existed = self.c.execute("SELECT 1 FROM sqlite_master WHERE name='mem_fts'").fetchone()
        try:
            self.c.executescript(FTS)
            if not existed:
                self.c.execute("INSERT INTO mem_fts(mem_fts) VALUES('rebuild')")
                self.c.commit()
            self.fts = True
        except sqlite3.OperationalError as exc:
            if 'no such module: fts5' not in str(exc):
                raise
            self.fts = False

    def close(self):
        self.c.close()

    def event(self, memory_id, action, detail=''):
        self.c.execute('INSERT INTO events(memory_id,action,detail,created_at) VALUES(?,?,?,?)',
                       (memory_id, action, detail, int(time.time())))

    def get(self, memory_id):
        row = self.c.execute('SELECT * FROM memories WHERE id=? AND archived_at IS NULL',
                             (memory_id,)).fetchone()
        if row is None:
            raise ValueError(f'No active memory #{memory_id}. Use list --all to see the archive.')
        return dict(row)

    def rows(self, ring=None, include_archived=False):
        where, args = [], []
        if not include_archived:
            where.append('archived_at IS NULL')
        if ring is not None:
            where.append('ring=?')
            args.append(ring)
        query = 'SELECT * FROM memories' + (' WHERE ' + ' AND '.join(where) if where else '')
        return [dict(r) for r in self.c.execute(query + ' ORDER BY id', args)]

    def add(self, content, ring=1, tags=''):
        content = text(content)
        if ring not in (1, 2, 3):
            raise ValueError('ring0 requires propose, then explicit user approval.')
        existing = self.c.execute(
            'SELECT id FROM memories WHERE ring=? AND content=? AND archived_at IS NULL',
            (ring, content)).fetchone()
        if existing:
            return {'id': existing['id'], 'ring': ring, 'content': content, 'existing': True}
        now = int(time.time())
        cur = self.c.execute(
            'INSERT INTO memories(ring,content,tags,created_at,updated_at) VALUES(?,?,?,?,?)',
            (ring, content, tags, now, now))
        self.event(cur.lastrowid, 'remember', f'ring{ring}')
        return {'id': cur.lastrowid, 'ring': ring, 'content': content, 'existing': False}

    def recall(self, query, ring=1, limit=3):
        query = text(query)
        tokens = list(dict.fromkeys(re.findall(r'\w+', query.casefold())))
        if not tokens:
            tokens = [query.casefold()]
        ranks = {}
        if self.fts:
            match = ' OR '.join('"' + t.replace('"', '""') + '"*' for t in tokens)
            for row in self.c.execute(
                'SELECT m.id, bm25(mem_fts) AS rank FROM mem_fts '
                'JOIN memories m ON m.id=mem_fts.rowid '
                'WHERE mem_fts MATCH ? AND m.ring=? AND m.archived_at IS NULL', (match, ring)):
                ranks[row['id']] = row['rank']
        candidates = []
        for row in self.rows(ring):
            haystack = (row['content'] + ' ' + row['tags']).casefold()
            hits = sum(t in haystack for t in tokens)
            if hits or row['id'] in ranks:
                candidates.append((hits, row))
        candidates.sort(key=lambda pair: (
            -pair[0], ranks.get(pair[1]['id'], 0), -pair[1]['salience'],
            -pair[1]['updated_at'], -pair[1]['id']))
        rows = [row for _, row in candidates[:limit]]
        now = int(time.time())
        for row in rows:
            self.c.execute('UPDATE memories SET access_count=access_count+1, last_access=? WHERE id=?',
                           (now, row['id']))
        return rows

    def move(self, memory_id, target=None, archive=False):
        row = self.get(memory_id)
        if row['ring'] == 0:
            raise ValueError(f'ring0 is protected. Use propose --remove {memory_id}, then approve.')
        if target is None:
            target = min(3, row['ring'] + 1)
        if target not in (1, 2, 3):
            raise ValueError('ring0 requires propose, then explicit user approval.')
        now = int(time.time())
        self.c.execute('UPDATE memories SET ring=?, updated_at=?, archived_at=? WHERE id=?',
                       (target, now, now if archive else None, memory_id))
        self.event(memory_id, 'archive' if archive else 'move', f"ring{row['ring']} -> ring{target}")
        return {'id': memory_id, 'ring': target, 'archived': archive}

    def propose(self, content, tags='', replace=None, remove=None):
        target = remove if remove is not None else replace
        action = 'remove' if remove is not None else 'replace' if replace is not None else 'add'
        if target is not None and self.get(target)['ring'] != 0:
            raise ValueError('Only active ring0 entries can be replaced or removed by a proposal.')
        content = '' if action == 'remove' else text(content)
        if action != 'remove' and len(content) > RING0_CAP:
            raise ValueError(f'A ring0 entry must fit within {RING0_CAP} characters.')
        cur = self.c.execute(
            'INSERT INTO proposals(content,tags,created_at,action,target_id) VALUES(?,?,?,?,?)',
            (content, tags, int(time.time()), action, target))
        return {'id': cur.lastrowid, 'action': action, 'content': content, 'target_id': target,
                'status': 'pending'}

    def resolve(self, proposal_id, approve=True):
        p = self.c.execute('SELECT * FROM proposals WHERE id=?', (proposal_id,)).fetchone()
        if p is None:
            raise ValueError(f'Unknown proposal #{proposal_id}. Use proposals to list pending requests.')
        if p['status'] != 'pending':
            raise ValueError(f"Proposal #{proposal_id} is already {p['status']}.")
        now = int(time.time())
        if approve:
            old = self.get(p['target_id']) if p['target_id'] is not None else None
            if old and old['ring'] != 0:
                raise ValueError('The target is no longer in ring0; create a new proposal.')
            total = sum(len(r['content']) for r in self.rows(0))
            size = total - (len(old['content']) if old else 0) + len(p['content'])
            if size > RING0_CAP:
                raise ValueError(f'ring0 would use {size}/{RING0_CAP} characters. Shorten or replace an entry.')
            if old:
                self.c.execute('UPDATE memories SET ring=3, archived_at=?, updated_at=? WHERE id=?',
                               (now, now, old['id']))
                self.event(old['id'], 'archive', f'approved proposal #{proposal_id}')
            if p['action'] != 'remove':
                cur = self.c.execute(
                    'INSERT INTO memories(ring,content,tags,created_at,updated_at) VALUES(0,?,?,?,?)',
                    (p['content'], p['tags'], now, now))
                self.event(cur.lastrowid, 'approve', f'proposal #{proposal_id}')
        status = 'approved' if approve else 'rejected'
        self.c.execute('UPDATE proposals SET status=? WHERE id=?', (status, proposal_id))
        return {'id': proposal_id, 'status': status}

    def proposals(self, include_all=False):
        return [dict(r) for r in self.c.execute(
            'SELECT * FROM proposals' + ('' if include_all else " WHERE status='pending'") + ' ORDER BY id')]

    def snapshot(self, query=None):
        long_term = self.recall(query) if query else sorted(
            self.rows(1), key=lambda r: (-r['salience'], -r['updated_at'], -r['id']))[:3]
        recent = sorted(self.rows(2), key=lambda r: (-r['updated_at'], -r['id']))[:5]
        return {'ring0': self.rows(0), 'ring1': long_term, 'ring2': recent}

    def dream(self, now=None):
        now = int(time.time()) if now is None else now
        actions, seen = [], set()
        for row in self.rows():
            if row['ring'] == 0:
                continue
            key = (row['ring'], row['content'])
            if key in seen:
                self.move(row['id'], 3, archive=True)
                actions.append(f"Archived duplicate #{row['id']} (content retained).")
                continue
            seen.add(key)
            if row['ring'] == 2 and row['access_count'] >= 3:
                self.move(row['id'], 1)
                actions.append(f"Promoted #{row['id']} to ring1.")
            elif not pinned(row['tags']):
                last_used = max(row['updated_at'], row['last_access'] or 0)
                if row['ring'] == 1 and last_used < now - 90 * DAY:
                    self.move(row['id'], 2)
                    # Recalls before demotion must not immediately promote it again.
                    self.c.execute('UPDATE memories SET access_count=0, last_decay=? WHERE id=?',
                                   (now, row['id']))
                    actions.append(f"Demoted cold memory #{row['id']} to ring2.")
                elif row['ring'] == 2:
                    baseline = max(row['updated_at'], row['last_decay'] or 0)
                    periods = max(0, (now - baseline) // (30 * DAY))
                    if periods:
                        self.c.execute('UPDATE memories SET salience=salience*?, last_decay=? WHERE id=?',
                                       (0.9 ** periods, baseline + periods * 30 * DAY, row['id']))
                        self.event(row['id'], 'decay', f'{periods} period(s)')
                        actions.append(f"Decayed #{row['id']} by {periods} 30-day period(s).")
        return actions

    def export(self):
        """Export every row, including the archive, with no retrieval-size limits."""
        base = self.root / '.agent/memory'
        base.mkdir(parents=True, exist_ok=True)
        files = []
        rows = self.rows(include_archived=True)
        for ring in (0, 1, 2, 3, 'archive'):
            selected = [r for r in rows if (r['archived_at'] is not None if ring == 'archive'
                        else r['ring'] == ring and r['archived_at'] is None)]
            name = 'archive' if ring == 'archive' else f'ring{ring}'
            body = [f'# {name}', '', '<!-- Generated from rings.db; edit through the CLI. -->', '']
            for row in selected:
                content = row['content'].replace('\n', '\n  ')
                body.append(f"- [{row['id']}] {content}" + (f" #{row['tags']}" if row['tags'] else ''))
            path = base / f'{name}.md'
            self._write(path, '\n'.join(body) + '\n')
            files.append(path)
        # Full-fidelity, portable backup; unlike Markdown, includes metadata and proposals.
        state = {'version': 1, 'memories': rows, 'proposals': self.proposals(True),
                 'events': [dict(r) for r in self.c.execute('SELECT * FROM events ORDER BY id')]}
        path = base / 'state.json'
        self._write(path, json.dumps(state, ensure_ascii=False, indent=2) + '\n')
        files.append(path)
        return files

    @staticmethod
    def _write(path, content):
        # Unique sibling files keep concurrent exports atomic and are immediately removed.
        import tempfile
        fd, name = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                handle.write(content)
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)

    def commit_exports(self, files):
        def git(*args):
            result = subprocess.run(['git', '-C', str(self.root), *args],
                                    text=True, capture_output=True)
            if result.returncode:
                raise ValueError(result.stderr.strip() or result.stdout.strip() or 'Git command failed.')
            return result.stdout

        relative = [str(p.relative_to(self.root)) for p in files]
        git('add', '--force', '--', *relative)
        if not git('diff', '--cached', '--name-only', '--', *relative).strip():
            return
        # --only leaves unrelated staged work out of the memory commit.
        git('-c', 'user.name=ring-memory', '-c', 'user.email=ring@local',
            'commit', '--only', '-m', 'ring: update memory', '--', *relative)

    def restore(self, source):
        if self.rows(include_archived=True) or self.proposals(True):
            raise ValueError('Restore needs an empty store. Select a new directory with --root.')
        state = json.loads(Path(source).read_text(encoding='utf-8'))
        if state.get('version') != 1:
            raise ValueError('Unsupported backup version.')
        # All inserts are in the caller transaction; malformed backups roll back together.
        for table in ('memories', 'proposals', 'events'):
            columns = [r['name'] for r in self.c.execute(f'PRAGMA table_info({table})')]
            for row in state[table]:
                self.c.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                               [row[name] for name in columns])
        for row in self.rows(include_archived=True):
            if (row['ring'] not in (0, 1, 2, 3) or not isinstance(row['content'], str)
                    or not row['content'].strip() or not isinstance(row['tags'], str)):
                raise ValueError('Invalid memory in backup.')
            for field in ('id', 'created_at', 'updated_at', 'access_count',
                          'archived_at', 'last_access', 'last_decay'):
                value = row[field]
                if value is None and field in ('archived_at', 'last_access', 'last_decay'):
                    continue
                if not isinstance(value, int) or value < (1 if field == 'id' else 0):
                    raise ValueError(f'Invalid {field} in backup memory.')
            salience = row['salience']
            if not isinstance(salience, (int, float)) or not math.isfinite(salience) or salience < 0:
                raise ValueError('Invalid salience in backup memory.')
        for proposal in self.proposals(True):
            if (proposal['status'] not in ('pending', 'approved', 'rejected')
                    or proposal['action'] not in ('add', 'replace', 'remove')
                    or not isinstance(proposal['content'], str)
                    or not isinstance(proposal['tags'], str)
                    or (proposal['action'] != 'remove' and not proposal['content'].strip())):
                raise ValueError('Invalid proposal in backup.')
            if proposal['action'] != 'add':
                if not any(r['id'] == proposal['target_id'] for r in self.rows(include_archived=True)):
                    raise ValueError('Missing proposal target in backup.')
        if sum(len(r['content']) for r in self.rows(0)) > RING0_CAP:
            raise ValueError('Backup exceeds the ring0 character cap.')
        return {'restored': len(state['memories'])}
