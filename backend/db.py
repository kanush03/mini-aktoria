import os
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(os.environ.get("MINI_AKTORIA_DB", Path(__file__).parent / "takeovers.db"))

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.execute("""CREATE TABLE IF NOT EXISTS takeovers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    robot_id TEXT, robot_kind TEXT, wall_x REAL, wall_half REAL,
    started_at REAL, ended_at REAL, outcome TEXT)""")
conn.execute("""CREATE TABLE IF NOT EXISTS steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    takeover_id INTEGER, t REAL,
    x REAL, y REAL, theta REAL, v REAL, w REAL)""")
conn.commit()


def start_takeover(robot_id, robot_kind, wall_x, wall_half):
    cur = conn.execute(
        "INSERT INTO takeovers (robot_id, robot_kind, wall_x, wall_half, started_at) "
        "VALUES (?,?,?,?,?)",
        (robot_id, robot_kind, wall_x, wall_half, time.time()))
    conn.commit()
    return cur.lastrowid


def log_step(tid, s, cmd):
    conn.execute(
        "INSERT INTO steps (takeover_id, t, x, y, theta, v, w) VALUES (?,?,?,?,?,?,?)",
        (tid, time.time(), s["x"], s["y"], s["theta"], cmd["v"], cmd["w"]))


def end_takeover(tid, outcome):
    conn.execute("UPDATE takeovers SET ended_at=?, outcome=? WHERE id=?",
                 (time.time(), outcome, tid))
    conn.commit()


def set_outcome(tid, outcome):
    conn.execute("UPDATE takeovers SET outcome=? WHERE id=?", (outcome, tid))
    conn.commit()


def load_episodes(outcomes=None):
    """Read takeovers back as episodes (same format as episodes.jsonl).

    outcomes: only return takeovers with one of these outcomes (None = all).
    """
    rows = conn.execute(
        "SELECT id, robot_id, robot_kind, wall_x, wall_half, started_at, ended_at, outcome "
        "FROM takeovers WHERE wall_x IS NOT NULL ORDER BY id").fetchall()
    episodes = []
    for tid, robot_id, kind, wall_x, wall_half, start, end, outcome in rows:
        if outcomes is not None and outcome not in outcomes:
            continue
        steps = conn.execute(
            "SELECT t, x, y, theta, v, w FROM steps WHERE takeover_id=? ORDER BY id",
            (tid,)).fetchall()
        episodes.append({
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
        })
    return episodes
