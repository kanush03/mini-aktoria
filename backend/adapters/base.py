import math
from abc import ABC, abstractmethod


class RobotAdapter(ABC):
    kind = "robot"

    def __init__(self, wall_x=5.0, wall_half=1.0):
        self.x, self.y, self.theta = 0.0, 0.0, 0.0
        self.wall_x = wall_x
        self.wall_half = wall_half

    def get_state(self):
        return {"x": self.x, "y": self.y, "theta": self.theta}

    def move(self, v, w, dt):
        self.theta += w * dt
        nx = self.x + v * math.cos(self.theta) * dt
        ny = self.y + v * math.sin(self.theta) * dt
        crosses = (self.x < self.wall_x <= nx) or (nx < self.wall_x <= self.x)
        if crosses and abs(ny) < self.wall_half:
            return  # hit the wall
        self.x, self.y = nx, ny

    @abstractmethod
    def from_drive(self, v, w):
        """Turn a generic forward/turn command into this robot's own controls."""

    @abstractmethod
    def send_command(self, cmd):
        ...

    @abstractmethod
    def step(self, dt):
        ...