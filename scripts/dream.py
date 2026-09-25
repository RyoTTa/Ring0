#!/usr/bin/env python3
"""Sleeptime dreaming: dedupe, decay, promote candidates, then export + git commit."""
import sqlite3, os, time, subprocess
DB = os.environ.get("RING_DB", ".agent/rings.db")

def run(cmd):
    subprocess.run(cmd, check=False, capture_output=True)

def main():
    if not os.path.exists(DB):
        print("no db"); return
    c = sqlite3.connect(DB); now = int(time.time())
    # decay ring2 older than 30d unless pinned
    c.execute("UPDATE memories SET salience=salience*0.9 WHERE ring=2 AND updated_at<? AND tags NOT LIKE '%pin%'", (now-30*86400,))
    # delete near-duplicate ring2/3 (same content)
    c.execute("DELETE FROM memories WHERE id NOT IN (SELECT MIN(id) FROM memories GROUP BY ring, content)")
    # promote candidates: ring2 accessed 3+ times -> ring1
    c.execute("UPDATE memories SET ring=1, updated_at=? WHERE ring=2 AND access_count>=3", (now,))
    c.commit()
    # export markdown for git diff
    import pathlib
    base = pathlib.Path(".agent/memory"); base.mkdir(parents=True, exist_ok=True)
    for ring in (0, 1, 2, 3):
        rows = c.execute("SELECT id, content, tags FROM memories WHERE ring=? ORDER BY salience DESC LIMIT 50", (ring,))
        with open(base/f"ring{ring}.md","w") as f:
            f.write(f"# ring{ring}\n\n")
            for i,t,tags in rows:
                f.write(f"- [{i}] {t}" + (f" #{tags}" if tags else "") + "\n")
    run(["git","add",".agent/rings.db",".agent/memory/"])
    run(["git","-c","user.name=ring-memory","-c","user.email=ring@local","commit","-m","ring: dream consolidation"])
    print("dream done")

if __name__ == "__main__":
    main()
