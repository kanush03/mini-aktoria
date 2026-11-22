import json
import sqlite3
from pathlib import Path

db = sqlite3.connect(Path(__file__).parent / "takeovers.db")
rows = db.execute(
    "SELECT id, robot_id, robot_kind, wall_x, wall_half, started_at, ended_at, outcome "
    "FROM takeovers").fetchall()
out = Path(__file__).parent / "episodes.jsonl"

with open(out, "w") as f:
    for tid, robot_id, kind, wall_x, wall_half, start, end, outcome in rows:
        steps = db.execute(
            "SELECT t, x, y, theta, v, w FROM steps WHERE takeover_id=? ORDER BY id",
            (tid,)).fetchall()
        episode = {
            "id": tid,
            "robot_id": robot_id,
            "robot_kind": kind,
            "world": {"wall_x": wall_x, "wall_half": wall_half},
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
        print(f"takeover {tid} ({robot_id}, {kind}, wall at {wall_x}, half-height {wall_half}): "
              f"{len(steps)} steps, {episode['duration_s']}s, outcome={outcome}")

print(f"\n{len(rows)} takeovers saved to {out.name}")