#!/usr/bin/env python3
"""Minimal ring-memory store: SQLite + FTS5, vector optional."""
import argparse, sqlite3, os, time, sys
DB = os.environ.get("RING_DB", ".agent/rings.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories(
 id INTEGER PRIMARY KEY, ring INTEGER, content TEXT,
 tags TEXT DEFAULT '', created_at INTEGER, updated_at INTEGER,
 access_count INTEGER DEFAULT 0, salience REAL DEFAULT 1.0);
CREATE VIRTUAL TABLE IF NOT EXISTS mem_fts USING fts5(content, content='memories', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS mem_ai AFTER INSERT ON memories BEGIN INSERT INTO mem_fts(rowid, content) VALUES (new.id, new.content); END;
CREATE TRIGGER IF NOT EXISTS mem_ad AFTER DELETE ON memories BEGIN INSERT INTO mem_fts(mem_fts, rowid, content) VALUES('delete', old.id, old.content); END;
"""

def db():
    os.makedirs(os.path.dirname(DB) or ".", exist_ok=True)
    c = sqlite3.connect(DB)
    c.executescript(SCHEMA)
    return c

def remember(args):
    if args.ring == 0:
        print("ring0 writes need explicit user confirmation, aborting", file=sys.stderr)
        if not args.force: sys.exit(1)
    c = db(); now = int(time.time())
    cur = c.execute("INSERT INTO memories(ring,content,tags,created_at,updated_at) VALUES(?,?,?,?,?)",
        (args.ring, args.content, args.tags or "", now, now))
    c.commit()
    export_md(); git_commit(f"ring: remember ring{args.ring}")
    print(cur.lastrowid)

def recall(args):
    c = db()
    rows = []
    try:
        rows = list(c.execute("SELECT m.id,m.ring,m.content FROM mem_fts f JOIN memories m ON m.id=f.rowid WHERE mem_fts MATCH ? AND m.ring=? ORDER BY m.salience DESC LIMIT ?",
            (args.query, args.ring, args.limit)))
    except Exception:
        pass
    if not rows:
        rows = list(c.execute("SELECT id,ring,content FROM memories WHERE ring=? AND content LIKE ? ORDER BY salience DESC, updated_at DESC LIMIT ?",
            (args.ring, f"%{args.query}%", args.limit)))
    for i, r, t in rows:
        c.execute("UPDATE memories SET access_count=access_count+1 WHERE id=?", (i,))
        print(f"[{i}|r{r}] {t}")
    c.commit()

def git_commit(msg):
    import subprocess
    try:
        subprocess.run(["git", "add", ".agent/rings.db", ".agent/memory/"], check=False, capture_output=True)
        subprocess.run(["git", "-c", "user.name=ring-memory", "-c", "user.email=ring@local", "commit", "-m", msg], check=False, capture_output=True)
    except Exception:
        pass

def export_md(args=None):
    import pathlib
    c = db()
    base = pathlib.Path(".agent/memory"); base.mkdir(parents=True, exist_ok=True)
    for ring in (0, 1, 2, 3):
        rows = list(c.execute("SELECT id, content, tags, updated_at FROM memories WHERE ring=? ORDER BY salience DESC, updated_at DESC LIMIT 50", (ring,)))
        with open(base / f"ring{ring}.md", "w") as f:
            f.write(f"# ring{ring}\n\n")
            for i, t, tags, _ in rows:
                f.write(f"- [{i}] {t}" + (f" #{tags}" if tags else "") + "\n")
    print("exported")

def promote(args):
    c = db()
    c.execute("UPDATE memories SET ring=?, updated_at=? WHERE id=?", (args.to, int(time.time()), args.id))
    c.commit()
    export_md(); git_commit(f"ring: promote {args.id} to ring{args.to}")
    print("ok")

def snapshot(args):
    c = db()
    for ring in (0, 1):
        print(f"--- ring{ring} ---")
        for (t,) in c.execute("SELECT content FROM memories WHERE ring=? ORDER BY salience DESC LIMIT 10", (ring,)):
            print(f"- {t}")
    print("--- ring2 recent ---")
    for (t,) in c.execute("SELECT content FROM memories WHERE ring=2 ORDER BY updated_at DESC LIMIT 5"):
        print(f"- {t}")

if __name__ == "__main__":
    pa = argparse.ArgumentParser(); sub = pa.add_subparsers(dest="c", required=True)
    r1 = sub.add_parser("remember"); r1.add_argument("--ring", type=int, required=True); r1.add_argument("--content", required=True); r1.add_argument("--tags", default=""); r1.add_argument("--force", action="store_true")
    r2 = sub.add_parser("recall"); r2.add_argument("--query", required=True); r2.add_argument("--ring", type=int, default=1); r2.add_argument("--limit", type=int, default=3)
    r3 = sub.add_parser("promote"); r3.add_argument("--id", type=int, required=True); r3.add_argument("--to", type=int, required=True)
    r4 = sub.add_parser("snapshot")
    r5 = sub.add_parser("export")
    a2 = pa.parse_args()
    if a2.c == "remember": remember(a2)
    elif a2.c == "recall": recall(a2)
    elif a2.c == "promote": promote(a2)
    elif a2.c == "snapshot": snapshot(a2)
    elif a2.c == "export": export_md(a2)
