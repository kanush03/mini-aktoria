import json
import sqlite3
from pathlib import Path

db = sqlite3.connect(Path(__file__).parent / "takeovers.db")
rows = db.execute("SELECT id, started_at, ended_at, outcome FROM takeovers").fetchall()
out = Path(__file__).parent / "episodes.jsonl"

with open(out, "w") as f:
    for tid, start, end, outcome in rows:
        steps = db.execute(
            "SELECT t, x, y, theta, v, w FROM steps WHERE takeover_id=? ORDER BY id",
            (tid,)).fetchall()
        episode = {
            "id": tid,
            "outcome": outcome,
            "duration_s": round((end or start) - start, 2),
            "steps": [
                {"t": round(t - start, 3),
                 "state": {"x": x, "y": y, "theta": th},
                 "action": {"v": v, "w": w}}
                for t, x, y, th, v, w in steps
            ],
        }
        f.write(json.dumps(episode) + "\n")
        print(f"takeover {tid}: {len(steps)} steps, {episode['duration_s']}s, outcome={outcome}")

print(f"\n{len(rows)} takeovers saved to {out.name}")