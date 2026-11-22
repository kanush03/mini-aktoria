"""Write every logged takeover to episodes.jsonl (one JSON line per takeover)."""
import json
from pathlib import Path

import db

out = Path(__file__).parent / "episodes.jsonl"
episodes = db.load_episodes()

with open(out, "w") as f:
    for ep in episodes:
        f.write(json.dumps(ep) + "\n")
        w = ep["world"]
        print(f"takeover {ep['id']} ({ep['robot_id']}, {ep['robot_kind']}, wall at {w['wall_x']}, "
              f"half-height {w['wall_half']}): {len(ep['steps'])} steps, {ep['duration_s']}s, "
              f"outcome={ep['outcome']}")

print(f"\n{len(episodes)} takeovers saved to {out.name}")
