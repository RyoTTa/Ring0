#!/usr/bin/env python3
"""Sleeptime dreaming: decay, dedupe, promote/demote candidates, contradiction flags, export+commit."""
import sqlite3, os, time, subprocess
DB = os.environ.get("RING_DB", ".agent/rings.db")

def run(cmd):
    subprocess.run(cmd, check=False, capture_output=True)

def main():
    if not os.path.exists(DB):
        print("no db"); return
    c = sqlite3.connect(DB); now = int(time.time())
    c.executescript("""
CREATE TRIGGER IF NOT EXISTS mem_au AFTER UPDATE ON memories BEGIN INSERT INTO mem_fts(mem_fts, rowid, content) VALUES('delete', old.id, old.content); INSERT INTO mem_fts(rowid, content) VALUES (new.id, new.content); END;
""")
    c.execute("UPDATE memories SET salience=salience*0.9 WHERE ring=2 AND updated_at<? AND tags NOT LIKE '%pin%'", (now-30*86400,))
    c.execute("DELETE FROM memories WHERE id NOT IN (SELECT MIN(id) FROM memories GROUP BY ring, content)")
    c.execute("UPDATE memories SET ring=1, updated_at=? WHERE ring=2 AND access_count>=3", (now,))
    c.execute("UPDATE memories SET ring=2, updated_at=? WHERE ring=1 AND access_count=0 AND updated_at<? AND tags NOT LIKE '%pin%'", (now, now-90*86400))
    c.commit()
    rows = list(c.execute("SELECT id, content FROM memories WHERE ring=1 LIMIT 100"))
    words = lambda s: set(s.lower().split())
    for i in range(len(rows)):
        for j in range(i+1, len(rows)):
            a, b = rows[i], rows[j]
            wa, wb = words(a[1]), words(b[1])
            if wa and wb and len(wa & wb) / max(len(wa | wb), 1) > 0.5:
                print(f"possible overlap: [{a[0]}] vs [{b[0]}]")
    import pathlib
    base = pathlib.Path(".agent/memory"); base.mkdir(parents=True, exist_ok=True)
    for ring in (0, 1, 2, 3):
        rs = c.execute("SELECT id, content, tags FROM memories WHERE ring=? ORDER BY salience DESC LIMIT 50", (ring,))
        with open(base/f"ring{ring}.md","w") as f:
            f.write(f"# ring{ring}\n\n")
            for i,t,tags in rs:
                f.write(f"- [{i}] {t}" + (f" #{tags}" if tags else "") + "\n")
    run(["git","add",".agent/rings.db",".agent/memory/"])
    run(["git","-c","user.name=ring-memory","-c","user.email=ring@local","commit","-m","ring: dream consolidation"])
    print("dream done")

if __name__ == "__main__":
    main()
