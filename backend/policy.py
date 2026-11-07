import math

class AutoPilot:
    def __init__(self, goal, stuck_window=20, eps=0.01):
        self.goal = goal
        self.hist = []
        self.window = stuck_window
        self.eps = eps

    def act(self, state):
        dx = self.goal[0] - state["x"]
        dy = self.goal[1] - state["y"]
        target = math.atan2(dy, dx)
        err = (target - state["theta"] + math.pi) % (2 * math.pi) - math.pi
        v = 1.0 if abs(err) < 0.3 else 0.0
        return {"v": v, "w": 2.0 * err}

    def is_stuck(self, state):
        self.hist.append((state["x"], state["y"]))
        if len(self.hist) < self.window:
            return False
        self.hist = self.hist[-self.window:]
        moved = math.dist(self.hist[0], self.hist[-1])
        return moved < self.eps