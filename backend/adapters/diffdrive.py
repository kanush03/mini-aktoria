from .base import RobotAdapter


class DiffDriveRobot(RobotAdapter):
    kind = "diff-drive"
    WHEELBASE = 0.5

    def __init__(self, wall_x=5.0):
        super().__init__(wall_x)
        self.cmd = {"left": 0.0, "right": 0.0}

    def from_drive(self, v, w):
        half = w * self.WHEELBASE / 2
        return {"left": v - half, "right": v + half}

    def send_command(self, cmd):
        self.cmd = cmd

    def step(self, dt):
        v = (self.cmd["left"] + self.cmd["right"]) / 2
        w = (self.cmd["right"] - self.cmd["left"]) / self.WHEELBASE
        self.move(v, w, dt)