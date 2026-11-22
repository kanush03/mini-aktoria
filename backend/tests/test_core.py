import json
import random
import time

from fastapi.testclient import TestClient

import db
import scripted_operator
import sim
from adapters.diffdrive import DiffDriveRobot
from adapters.wheeled import WheeledRobot
from learning import KNNPolicy


# ---------- robots and the adapter layer
def test_both_robot_types_follow_the_same_drive_command():
    a = sim.make_robot(WheeledRobot, 50.0, 1.0)
    b = sim.make_robot(DiffDriveRobot, 50.0, 1.0)
    for step in range(200):
        v, w = (1.0, 0.4) if step < 100 else (0.5, -0.8)
        a.send_command(a.from_drive(v, w)); a.step(sim.DT)
        b.send_command(b.from_drive(v, w)); b.step(sim.DT)
    sa, sb = a.get_state(), b.get_state()
    assert abs(sa["x"] - sb["x"]) < 1e-6 and abs(sa["y"] - sb["y"]) < 1e-6


def test_native_commands_really_differ():
    assert set(WheeledRobot().from_drive(1, 0.5)) == {"v", "w"}
    assert set(DiffDriveRobot().from_drive(1, 0.5)) == {"left", "right"}


def test_robot_gets_stuck_at_the_wall():
    robot = sim.make_robot(WheeledRobot, 5.0, 1.0)
    assert sim.drive_until_stuck(robot) is not None
    assert 4.9 < robot.get_state()["x"] <= 5.0


def test_robot_can_pass_above_the_wall():
    robot = sim.make_robot(WheeledRobot, 5.0, 1.0)
    robot.y, robot.x, robot.theta = 1.5, 4.0, 0.0
    for _ in range(60):
        robot.send_command({"v": 1.5, "w": 0.0}); robot.step(sim.DT)
    assert robot.get_state()["x"] > 5.5


def test_no_false_stuck_alarm_in_open_field():
    robot = sim.make_robot(WheeledRobot, 100.0, 1.0)      # wall far away
    reached, _ = sim.drive_to_goal(robot)
    assert reached


# ---------- operator data and learning
def test_scripted_operator_solves_every_world():
    demos = scripted_operator.make_demos(15, seed=3)
    assert len(demos) == 15 and all(d["outcome"] == "success" for d in demos)


def test_learning_from_a_few_takeovers_solves_new_worlds():
    policy = KNNPolicy().fit(scripted_operator.make_demos(8, seed=11))
    rng = random.Random(77)
    solved = 0
    for _ in range(30):
        wall_x, wall_half = sim.sample_world(rng)
        robot = sim.make_robot(rng.choice([WheeledRobot, DiffDriveRobot]), wall_x, wall_half)
        sim.drive_until_stuck(robot)
        passed, _ = sim.assist(robot, policy)
        solved += bool(passed and sim.drive_to_goal(robot)[0])
    assert solved >= 27          # at least 90%


def test_untrained_policy_does_nothing():
    assert KNNPolicy().act({"x": 1, "y": 0, "theta": 0}, 5.0, 1.0) == (0.0, 0.0)


def test_policy_save_and_load(tmp_path):
    policy = KNNPolicy().fit(scripted_operator.make_demos(4, seed=5), source="test")
    policy.save(tmp_path / "m.json")
    loaded = KNNPolicy.load(tmp_path / "m.json")
    state = {"x": 4.9, "y": 0.0, "theta": 0.0}
    assert loaded.act(state, 5.0, 1.0) == policy.act(state, 5.0, 1.0)
    assert loaded.meta["source"] == "test"


# ---------- takeover log
def test_database_roundtrip():
    tid = db.start_takeover("R9", "wheeled", 5.2, 1.1)
    db.log_step(tid, {"x": 5.0, "y": 0.0, "theta": 0.0}, {"v": 0.0, "w": 1.5})
    db.log_step(tid, {"x": 5.0, "y": 0.0, "theta": 0.1}, {"v": 0.0, "w": 1.5})
    db.end_takeover(tid, "success")
    ep = [e for e in db.load_episodes(outcomes=("success",)) if e["id"] == tid][0]
    assert ep["robot_id"] == "R9" and ep["world"] == {"wall_x": 5.2, "wall_half": 1.1}
    assert len(ep["steps"]) == 2 and ep["steps"][0]["action"] == {"v": 0.0, "w": 1.5}


# ---------- the live server
def recv(ws):
    while True:
        data = json.loads(ws.receive_text())
        if "robots" in data:
            return data


def test_server_reports_fleet_and_asks_for_more_data():
    import server
    with TestClient(server.app) as client, client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "reset"}))
        ws.send_text(json.dumps({"type": "learn"}))
        time.sleep(0.3)
        data = recv(ws)
        assert [r["id"] for r in data["robots"]] == ["R1", "R2", "R3"]
        assert all(0.8 <= r["wall_half"] <= 1.4 for r in data["robots"])
        assert any("Need at least" in e["text"] for e in data["events"])


def test_server_latency_ping_gets_a_reply():
    import server
    with TestClient(server.app) as client, client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "ping", "t": 123.0}))
        for _ in range(100):
            data = json.loads(ws.receive_text())
            if data.get("type") == "pong":
                assert data["t"] == 123.0
                return
        raise AssertionError("no pong")


def test_server_learned_assist_frees_the_operator():
    import server
    with TestClient(server.app) as client, client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "reset"}))
        ws.send_text(json.dumps({"type": "assist", "on": True}))
        start = time.time()
        while time.time() - start < 40:
            data = recv(ws)
            if all(r["mode"] == "done" for r in data["robots"]):
                break
        assert all(r["mode"] == "done" for r in data["robots"])
        assert data["stats"]["takeovers"] == 0 and data["stats"]["recoveries"] >= 1
