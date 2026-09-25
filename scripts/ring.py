#!/usr/bin/env python3
"""Ring memory store: SQLite + FTS5, vector optional. DB is index, markdown is truth."""
import argparse, sqlite3, os, time, sys
DB = os.environ.get("RING_DB", ".agent/rings.db")
RING0_CAP = 2000

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories(
 id INTEGER PRIMARY KEY, ring INTEGER, content TEXT,
 tags TEXT DEFAULT '', created_at INTEGER, updated_at INTEGER,
 access_count INTEGER DEFAULT 0, salience REAL DEFAULT 1.0);
CREATE VIRTUAL TABLE IF NOT EXISTS mem_fts USING fts5(content, content='memories', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS mem_ai AFTER INSERT ON memories BEGIN INSERT INTO mem_fts(rowid, content) VALUES (new.id, new.content); END;
CREATE TRIGGER IF NOT EXISTS mem_ad AFTER DELETE ON memories BEGIN INSERT INTO mem_fts(mem_fts, rowid, content) VALUES('delete', old.id, old.content); END;
CREATE TRIGGER IF NOT EXISTS mem_au AFTER UPDATE ON memories BEGIN INSERT INTO mem_fts(mem_fts, rowid, content) VALUES('delete', old.id, old.content); INSERT INTO mem_fts(rowid, content) VALUES (new.id, new.content); END;
CREATE TABLE IF NOT EXISTS proposals(
 id INTEGER PRIMARY KEY, content TEXT, tags TEXT DEFAULT '',
 status TEXT DEFAULT 'pending', created_at INTEGER);
"""

def db():
    d = os.path.dirname(DB)
    if d: os.makedirs(d, exist_ok=True)
    c = sqlite3.connect(DB)
    c.executescript(SCHEMA)
    return c

def git_commit(msg):
    import subprocess
    try:
        subprocess.run(["git", "add", ".agent/rings.db", ".agent/memory/"], check=False, capture_output=True)
        subprocess.run(["git", "-c", "user.name=ring-memory", "-c", "user.email=ring@local",
                        "commit", "-m", msg], check=False, capture_output=True)
    except Exception:
        pass

def export_md(args=None):
    import pathlib
    c = db()
    base = pathlib.Path(".agent/memory"); base.mkdir(parents=True, exist_ok=True)
    for ring in (0, 1, 2, 3):
        rows = list(c.execute("SELECT id, content, tags FROM memories WHERE ring=? ORDER BY salience DESC, updated_at DESC LIMIT 50", (ring,)))
        with open(base / f"ring{ring}.md", "w") as f:
            f.write(f"# ring{ring}\n\n")
            for i, t, tags in rows:
                f.write(f"- [{i}] {t}" + (f" #{tags}" if tags else "") + "\n")
    print("exported")

def ring0_chars(c):
    row = c.execute("SELECT COALESCE(SUM(LENGTH(content)),0) FROM memories WHERE ring=0").fetchone()
    return row[0] if row else 0

def remember(args):
    c = db(); now = int(time.time())
    if args.ring == 0:
        print("ring0 needs propose+approve first, direct write rejected", file=sys.stderr)
        sys.exit(1)
    cur = c.execute("INSERT INTO memories(ring,content,tags,created_at,updated_at) VALUES(?,?,?,?,?)",
        (args.ring, args.content, args.tags or "", now, now))
    c.commit()
    export_md(); git_commit(f"ring: remember ring{args.ring}")
    print(cur.lastrowid)

def recall(args):
    c = db()
    rows = []
    try:
        rows = list(c.execute(
            "SELECT m.id,m.ring,m.content FROM mem_fts JOIN memories m ON m.id=mem_fts.rowid"
            " WHERE mem_fts MATCH ? AND m.ring=? ORDER BY bm25(mem_fts), m.salience DESC LIMIT ?",
            (args.query, args.ring, args.limit)))
    except Exception:
        pass
    if not rows:
        rows = list(c.execute("SELECT id,ring,content FROM memories WHERE ring=? AND content LIKE ?"
                              " ORDER BY salience DESC, updated_at DESC LIMIT ?",
            (args.ring, f"%{args.query}%", args.limit)))
    for i, r, t in rows:
        c.execute("UPDATE memories SET access_count=access_count+1 WHERE id=?", (i,))
        print(f"[{i}|r{r}] {t}")
    c.commit()

def promote(args):
    c = db()
    if args.to == 0:
        print("ring0 needs propose+approve, use propose/approve instead", file=sys.stderr)
        sys.exit(1)
    c.execute("UPDATE memories SET ring=?, updated_at=? WHERE id=?", (args.to, int(time.time()), args.id))
    c.commit()
    export_md(); git_commit(f"ring: promote {args.id} to ring{args.to}")
    print("ok")

def demote(args):
    c = db()
    row = c.execute("SELECT ring FROM memories WHERE id=?", (args.id,)).fetchone()
    if not row:
        print("unknown id", file=sys.stderr); sys.exit(1)
    new_ring = min(3, row[0] + 1)
    c.execute("UPDATE memories SET ring=?, updated_at=? WHERE id=?", (new_ring, int(time.time()), args.id))
    c.commit()
    export_md(); git_commit(f"ring: demote {args.id} to ring{new_ring}")
    print(f"demoted to ring{new_ring}")

def propose(args):
    c = db()
    cur = c.execute("INSERT INTO proposals(content,tags,created_at) VALUES(?,?,?)",
        (args.content, args.tags or "", int(time.time())))
    c.commit()
    print(f"proposal {cur.lastrowid} pending: user must approve with approve --id {cur.lastrowid}")

def approve(args):
    c = db(); now = int(time.time())
    p = c.execute("SELECT content, tags, status FROM proposals WHERE id=?", (args.id,)).fetchone()
    if not p:
        print("unknown proposal", file=sys.stderr); sys.exit(1)
    content, tags, status = p
    if status != "pending":
        print(f"proposal already {status}", file=sys.stderr); sys.exit(1)
    if ring0_chars(c) + len(content) > RING0_CAP:
        print(f"ring0 cap {RING0_CAP} would be exceeded ({ring0_chars(c)} + {len(content)}), shorten first", file=sys.stderr)
        sys.exit(1)
    c.execute("INSERT INTO memories(ring,content,tags,created_at,updated_at) VALUES(0,?,?,?,?)",
        (content, tags, now, now))
    c.execute("UPDATE proposals SET status='approved' WHERE id=?", (args.id,))
    c.commit()
    export_md(); git_commit(f"ring: approve proposal {args.id} to ring0")
    print("approved to ring0")

def status(args):
    c = db()
    for (ring, n) in c.execute("SELECT ring, COUNT(*) FROM memories GROUP BY ring ORDER BY ring"):
        print(f"ring{ring}: {n}")
    print(f"ring0 chars: {ring0_chars(c)}/{RING0_CAP}")
    pend = c.execute("SELECT COUNT(*) FROM proposals WHERE status='pending'").fetchone()[0]
    print(f"pending proposals: {pend}")

def snapshot(args):
    c = db()
    print("--- ring0 ---")
    for (t,) in c.execute("SELECT content FROM memories WHERE ring=0 ORDER BY updated_at LIMIT 20"):
        print(f"- {t}")
    print("--- ring1 top ---")
    for (t,) in c.execute("SELECT content FROM memories WHERE ring=1 ORDER BY salience DESC LIMIT 10"):
        print(f"- {t}")
    print("--- ring2 recent ---")
    for (t,) in c.execute("SELECT content FROM memories WHERE ring=2 ORDER BY updated_at DESC LIMIT 5"):
        print(f"- {t}")

if __name__ == "__main__":
    pa = argparse.ArgumentParser(); sub = pa.add_subparsers(dest="c", required=True)
    r1 = sub.add_parser("remember"); r1.add_argument("--ring", type=int, required=True, choices=[1,2,3]); r1.add_argument("--content", required=True); r1.add_argument("--tags", default="")
    r2 = sub.add_parser("recall"); r2.add_argument("--query", required=True); r2.add_argument("--ring", type=int, default=1); r2.add_argument("--limit", type=int, default=3)
    r3 = sub.add_parser("promote"); r3.add_argument("--id", type=int, required=True); r3.add_argument("--to", type=int, required=True, choices=[1,2,3])
    r4 = sub.add_parser("demote"); r4.add_argument("--id", type=int, required=True)
    r5 = sub.add_parser("propose"); r5.add_argument("--content", required=True); r5.add_argument("--tags", default="")
    r6 = sub.add_parser("approve"); r6.add_argument("--id", type=int, required=True)
    sub.add_parser("status"); sub.add_parser("snapshot"); sub.add_parser("export")
    a2 = pa.parse_args()
    {"remember": remember, "recall": recall, "promote": promote, "demote": demote,
     "propose": propose, "approve": approve, "status": status,
     "snapshot": snapshot, "export": export_md}[a2.c](a2)
