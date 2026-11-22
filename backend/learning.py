"""Learning from takeovers: behaviour cloning with a k-nearest-neighbours policy.

Idea in one sentence: when a robot is stuck, find the situations in the takeover data that look
most like the current one, and do what the human operator did there.

Input  (what the policy sees): where the robot is relative to the wall, and its heading.
Output (what it does):         one of the operator's key presses, as a (forward, turn) command.
"""
import json
import math
from pathlib import Path

import numpy as np


def features(x, y, theta, wall_x, wall_half):
    """Describe the situation relative to the obstacle, so it works for any wall."""
    theta = (theta + math.pi) % (2 * math.pi) - math.pi
    return (
        (x - wall_x) / 0.5,                 # how far before / past the wall
        (abs(y) - wall_half) / 0.3,         # how far above the top of the wall (negative = beside it)
        theta / 0.4,                        # heading
    )


class KNNPolicy:
    def __init__(self, k=9):
        self.k = k
        self.X = np.zeros((0, 3))
        self.action_table = []              # list of (v, w) pairs
        self.action_ids = np.zeros(0, dtype=int)
        self.meta = {}

    # ----- training
    def fit(self, episodes, source=""):
        rows, acts = [], []
        for ep in episodes:
            wall_x, wall_half = ep["world"]["wall_x"], ep["world"]["wall_half"]
            for st in ep["steps"]:
                v, w = st["action"]["v"], st["action"]["w"]
                if v == 0 and w == 0:
                    continue                # operator pressed nothing: not a decision
                s = st["state"]
                rows.append(features(s["x"], s["y"], s["theta"], wall_x, wall_half))
                acts.append((round(v, 2), round(w, 2)))
        self.action_table = sorted(set(acts))
        index = {a: i for i, a in enumerate(self.action_table)}
        self.X = np.array(rows, dtype=float).reshape(-1, 3)
        self.action_ids = np.array([index[a] for a in acts], dtype=int)
        self.meta = {"demos": len(episodes), "samples": len(rows), "source": source}
        return self

    @property
    def ready(self):
        return len(self.X) > 0

    # ----- using it
    def act(self, state, wall_x, wall_half):
        if not self.ready:
            return 0.0, 0.0
        f = np.array(features(state["x"], state["y"], state["theta"], wall_x, wall_half))
        d2 = ((self.X - f) ** 2).sum(axis=1)
        k = min(self.k, len(d2))
        near = np.argpartition(d2, k - 1)[:k]
        votes = np.bincount(self.action_ids[near], minlength=len(self.action_table))
        return self.action_table[int(votes.argmax())]

    # ----- saving
    def save(self, path):
        data = {"k": self.k, "meta": self.meta, "action_table": self.action_table,
                "X": np.round(self.X, 4).tolist(), "action_ids": self.action_ids.tolist()}
        Path(path).write_text(json.dumps(data), encoding="utf-8")

    @classmethod
    def load(cls, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        p = cls(k=data["k"])
        p.X = np.array(data["X"], dtype=float).reshape(-1, 3)
        p.action_table = [tuple(a) for a in data["action_table"]]
        p.action_ids = np.array(data["action_ids"], dtype=int)
        p.meta = data["meta"]
        return p
