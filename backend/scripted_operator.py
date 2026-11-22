"""A scripted, slightly clumsy "operator" that produces takeover episodes in bulk.

It is NOT a human. It exists so the learning experiments are reproducible and can run without
someone steering for an hour. It follows the same routine a person uses (turn up-left, drive above
the wall, turn right, drive past), with random timing, random thresholds and random hesitations.
Episodes have exactly the same format as real takeovers exported from the web console.
"""
import random

from adapters.wheeled import WheeledRobot
import sim


def demonstrate(wall_x, wall_half, rng=random, robot_cls=WheeledRobot):
    robot = sim.make_robot(robot_cls, wall_x, wall_half)
    sim.drive_until_stuck(robot)

    th_up = rng.uniform(1.65, 2.2)             # point up and slightly left, or the wall blocks the way
    y_target = wall_half + rng.uniform(0.35, 0.65)
    th_back = rng.uniform(0.0, 0.25)
    x_target = wall_x + rng.uniform(0.3, 0.8)

    steps = []

    def press(v, w):
        # a human sometimes hesitates for a moment
        if rng.random() < 0.02:
            for _ in range(rng.randint(3, 10)):
                record(0.0, 0.0)
        record(v, w)

    def record(v, w):
        s = robot.get_state()
        steps.append({"t": round(len(steps) * sim.DT, 3),
                      "state": {"x": s["x"], "y": s["y"], "theta": s["theta"]},
                      "action": {"v": v, "w": w}})
        robot.send_command(robot.from_drive(v, w))
        robot.step(sim.DT)

    for _ in range(int(rng.uniform(0.3, 1.0) / sim.DT)):    # reaction time
        record(0.0, 0.0)

    phase = 1
    for _ in range(1500):
        s = robot.get_state()
        if phase == 1:
            if s["theta"] >= th_up:
                phase = 2
            else:
                press(0.0, 1.5)
                continue
        if phase == 2:
            if s["y"] >= y_target:
                phase = 3
            else:
                press(1.5, 0.0)
                continue
        if phase == 3:
            if s["theta"] <= th_back:
                phase = 4
            else:
                press(0.0, -1.5)
                continue
        if phase == 4:
            if s["x"] >= x_target:
                break
            press(1.5, 0.0)

    reached, _ = sim.drive_to_goal(robot)
    return {
        "robot_kind": robot_cls.kind,
        "world": {"wall_x": wall_x, "wall_half": wall_half},
        "outcome": "success" if reached else "failed",
        "duration_s": round(len(steps) * sim.DT, 2),
        "source": "scripted operator",
        "steps": steps,
    }


def make_demos(n, seed=0, robot_cls=WheeledRobot):
    rng = random.Random(seed)
    demos = []
    while len(demos) < n:
        wall_x, wall_half = sim.sample_world(rng)
        ep = demonstrate(wall_x, wall_half, rng, robot_cls)
        if ep["outcome"] == "success":
            demos.append(ep)
    return demos
