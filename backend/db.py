import sqlite3
import time
from pathlib import Path

conn = sqlite3.connect(Path(__file__).parent / "takeovers.db", check_same_thread=False)
conn.execute("""CREATE TABLE IF NOT EXISTS takeovers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    robot_id TEXT, robot_kind TEXT,
    started_at REAL, ended_at REAL, outcome TEXT)""")
conn.execute("""CREATE TABLE IF NOT EXISTS steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    takeover_id INTEGER, t REAL,
    x REAL, y REAL, theta REAL, v REAL, w REAL)""")
conn.commit()


def start_takeover(robot_id, robot_kind):
    cur = conn.execute(
        "INSERT INTO takeovers (robot_id, robot_kind, started_at) VALUES (?,?,?)",
        (robot_id, robot_kind, time.time()))
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