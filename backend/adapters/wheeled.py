from .base import RobotAdapter


class WheeledRobot(RobotAdapter):
    kind = "wheeled"

    def __init__(self, wall_x=5.0):
        super().__init__(wall_x)
        self.cmd = {"v": 0.0, "w": 0.0}

    def from_drive(self, v, w):
        return {"v": v, "w": w}

    def send_command(self, cmd):
        self.cmd = cmd

    def step(self, dt):
        self.move(self.cmd["v"], self.cmd["w"], dt)