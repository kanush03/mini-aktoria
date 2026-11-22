"""Headless helpers: build worlds and run robots without the web server.

Used by the server (assist mode), the scripted operator, the evaluation script and the tests.
"""
import math
import random

from adapters.wheeled import WheeledRobot
from adapters.diffdrive import DiffDriveRobot
from policy import AutoPilot

GOAL = (10, 0)
DT = 0.05              # simulation step in seconds
STUCK_WINDOW = 30      # steps without movement before a robot counts as stuck
PASS_MARGIN = 0.6      # a robot is "past the wall" when it is this far beyond it
ASSIST_TIMEOUT = 12.0  # seconds the learned policy gets before a human is asked


def sample_world(rng=random):
    """A random wall: (distance from start, half height)."""
    return round(rng.uniform(3.5, 6.5), 2), round(rng.uniform(0.8, 1.4), 2)


def make_robot(robot_cls, wall_x, wall_half):
    robot = robot_cls(wall_x=wall_x)
    robot.wall_half = wall_half
    return robot


def new_pilot():
    return AutoPilot(goal=GOAL, stuck_window=STUCK_WINDOW)


def drive_until_stuck(robot, max_steps=1500):
    """Run the autopilot until the robot is stuck. Returns the number of steps, or None."""
    pilot = new_pilot()
    for i in range(max_steps):
        s = robot.get_state()
        if pilot.is_stuck(s):
            return i
        robot.send_command(robot.from_drive(**pilot.act(s)))
        robot.step(DT)
    return None


def drive_to_goal(robot, max_steps=1500):
    """Run the autopilot only. Returns (reached_goal, steps)."""
    pilot = new_pilot()
    for i in range(max_steps):
        s = robot.get_state()
        if math.dist((s["x"], s["y"]), GOAL) < 0.3:
            return True, i
        if pilot.is_stuck(s):
            return False, i
        robot.send_command(robot.from_drive(**pilot.act(s)))
        robot.step(DT)
    return False, max_steps


def assist(robot, policy, max_s=ASSIST_TIMEOUT):
    """Let a learned policy try to get a stuck robot past the wall.

    Returns (passed_wall, steps_used).
    """
    n = int(max_s / DT)
    for i in range(n):
        s = robot.get_state()
        if s["x"] > robot.wall_x + PASS_MARGIN:
            return True, i
        v, w = policy.act(s, robot.wall_x, robot.wall_half)
        robot.send_command(robot.from_drive(v, w))
        robot.step(DT)
    return False, n
