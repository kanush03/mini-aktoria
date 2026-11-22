"""Does learning from takeovers reduce how often a human is needed?

For each number of demonstrations n, we train a policy on n takeovers, then drop robots into
fresh random worlds (never seen in training), let them get stuck, and let the learned policy try
to get them past the wall. If it fails, a human has to step in.

Writes docs/learning_results.json and docs/learning_curve.png.

  python evaluate.py            full run (about 1 minute)
  python evaluate.py --quick    smaller run for a fast check
"""
import argparse
import json
import random
import statistics
from pathlib import Path

import numpy as np

import scripted_operator
import sim
from learning import KNNPolicy

DOCS = Path(__file__).parent.parent / "docs"
SIZES = [0, 1, 2, 3, 5, 8, 12, 20]

parser = argparse.ArgumentParser()
parser.add_argument("--quick", action="store_true")
args = parser.parse_args()
N_WORLDS, REPS, POOL = (20, 5, 25) if args.quick else (60, 30, 60)

# ---- demonstrations (the "operator") and fresh test worlds
pool = scripted_operator.make_demos(POOL, seed=1)
rng = random.Random(999)
worlds = [sim.sample_world(rng) for _ in range(N_WORLDS)]

# ---- what does a human takeover cost in each test world? (time the operator needs + finishing)
human_cost = {}
stuck_steps = {}
for wall_x, wall_half in worlds:
    robot = sim.make_robot(sim.WheeledRobot, wall_x, wall_half)
    stuck_steps[(wall_x, wall_half)] = sim.drive_until_stuck(robot)
    ep = scripted_operator.demonstrate(wall_x, wall_half, random.Random(wall_x * 1000 + wall_half))
    human_cost[(wall_x, wall_half)] = ep["duration_s"]


def run_policy(policy):
    """One pass over all test worlds. Returns (solved_count, human_needed, total_seconds)."""
    solved, seconds = 0, 0.0
    for wall_x, wall_half in worlds:
        key = (wall_x, wall_half)
        robot = sim.make_robot(sim.WheeledRobot, wall_x, wall_half)
        sim.drive_until_stuck(robot)
        t = stuck_steps[key] * sim.DT
        if policy.ready:
            passed, used = sim.assist(robot, policy)
            t += used * sim.DT
            if passed:
                reached, finish = sim.drive_to_goal(robot)
                if reached:
                    solved += 1
                    seconds += t + finish * sim.DT
                    continue
        seconds += t + human_cost[key] + 2.0     # +2 s: autopilot drives the last stretch
    return solved, len(worlds) - solved, seconds


srng = random.Random(5)
curve = []
for n in SIZES:
    pcts, per_hour = [], []
    for _ in range(1 if n == 0 else REPS):
        policy = KNNPolicy().fit(srng.sample(pool, n)) if n else KNNPolicy()
        solved, human, seconds = run_policy(policy)
        pcts.append(100 * solved / len(worlds))
        per_hour.append(human / (seconds / 3600))
    row = {
        "demos": n,
        "solved_mean": round(statistics.mean(pcts), 1),
        "solved_min": round(min(pcts), 1),
        "solved_max": round(max(pcts), 1),
        "solved_p10": round(float(np.percentile(pcts, 10)), 1),
        "interventions_per_robot_hour": round(statistics.mean(per_hour), 1),
    }
    curve.append(row)
    print(f"{n:>3} demos: {row['solved_mean']:>5}% solved without a human "
          f"(min {row['solved_min']}, max {row['solved_max']}), "
          f"{row['interventions_per_robot_hour']} interventions per robot-hour")

base = curve[0]["interventions_per_robot_hour"]
for row in curve:
    row["reduction_pct"] = round(100 * (1 - row["interventions_per_robot_hour"] / base), 1)

results = {
    "meta": {
        "worlds_per_test": N_WORLDS, "subsets_per_size": REPS, "demo_pool": POOL,
        "operator": "scripted operator (not a human), see scripted_operator.py",
        "policy": "k-nearest-neighbours behaviour cloning, k=9",
        "success": "robot gets past the wall with the learned policy and the autopilot then reaches the goal",
        "assumption": "a human takeover costs the scripted operator's time; the learned policy gets 12 s",
    },
    "curve": curve,
}
DOCS.mkdir(exist_ok=True)
(DOCS / "learning_results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")

# ---- chart
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:
    print("matplotlib not installed: skipped the PNG chart")
else:
    xs = [r["demos"] for r in curve]
    fig, (a, b) = plt.subplots(1, 2, figsize=(10.5, 3.8))
    a.fill_between(xs, [r["solved_min"] for r in curve], [r["solved_max"] for r in curve],
                   color="#14b8a6", alpha=0.18, label="min to max over random subsets")
    a.plot(xs, [r["solved_mean"] for r in curve], "o-", color="#0f766e", label="mean")
    a.set_xlabel("takeovers used for training"); a.set_ylabel("stuck robots solved without a human (%)")
    a.set_ylim(-3, 103); a.grid(alpha=0.3); a.legend(loc="lower right", fontsize=8)
    a.set_title("Learning from takeovers")
    b.bar([str(x) for x in xs], [r["interventions_per_robot_hour"] for r in curve], color="#f59e0b")
    b.set_xlabel("takeovers used for training"); b.set_ylabel("human interventions per robot-hour")
    b.set_title("Human help needed"); b.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(DOCS / "learning_curve.png", dpi=140)
    print("saved docs/learning_curve.png")
print("saved docs/learning_results.json")
