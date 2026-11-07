import math
from .base import RobotAdapter

class WheeledRobot(RobotAdapter):
    def __init__(self):
        self.x, self.y, self.theta = 0.0, 0.0, 0.0
        self.v, self.w = 0.0, 0.0
        self.wall_x = 5.0  # wall at x=5, robot cannot pass

    def get_state(self):
        return {"x": self.x, "y": self.y, "theta": self.theta}

    def send_command(self, cmd):
        self.v = cmd.get("v", 0.0)
        self.w = cmd.get("w", 0.0)

    def step(self, dt):
        self.theta += self.w * dt
        nx = self.x + self.v * math.cos(self.theta) * dt
        ny = self.y + self.v * math.sin(self.theta) * dt
        if nx < self.wall_x:  # only move if not hitting the wall
            self.x, self.y = nx, ny