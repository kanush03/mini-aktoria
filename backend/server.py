import asyncio
import json
import math
import random
import time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from adapters.wheeled import WheeledRobot
from adapters.diffdrive import DiffDriveRobot
from learning import KNNPolicy
import db
import sim

ROOT = Path(__file__).parent.parent
PAGE = ROOT / "frontend" / "index.html"
RESULTS = ROOT / "docs" / "learning_results.json"
MODEL = Path(__file__).parent / "model.json"

GOAL = sim.GOAL
DT = sim.DT
SAFETY_TIMEOUT = 0.5   # seconds without operator commands -> robot stops
MIN_DEMOS_TO_LEARN = 3


class Unit:
    """One robot of the fleet plus everything the server tracks about it."""

    def __init__(self, uid, robot):
        self.id = uid
        self.robot = robot
        self.pilot = sim.new_pilot()
        self.mode = "auto"          # auto, assist, stuck, manual, done
        self.stuck_since = None
        self.assist_t = 0.0         # seconds the learned policy has been trying
        self.tid = None
        self.last_tid = None
        self.cmd = (0.0, 0.0)       # operator command: (v, w)
        self.last_cmd_at = 0.0
        self.safety_stop = False
        self.t_auto = 0.0           # simulated seconds spent in each mode
        self.t_assist = 0.0
        self.t_stuck = 0.0
        self.t_manual = 0.0


def random_world(robot):
    """Every run, each robot gets a wall at a slightly different place and size."""
    robot.wall_x, robot.wall_half = sim.sample_world()
    return robot


def make_fleet():
    return [
        Unit("R1", random_world(WheeledRobot())),
        Unit("R2", random_world(DiffDriveRobot())),
        Unit("R3", random_world(WheeledRobot())),
    ]


def new_stats():
    return {"ticks": 0, "op_ticks": 0, "takeovers": 0, "waits": [],
            "recoveries": 0, "assist_failures": 0}


fleet = make_fleet()
controlling = None
clients = set()
background = set()
net = {"name": "Good", "delay": 0, "loss": 0.0}   # simulated network
stats = new_stats()
events = []                                        # short activity feed for the console
event_counter = 0
learning = {"assist": False, "policy": None}


def load_model():
    if MODEL.exists():
        learning["policy"] = KNNPolicy.load(MODEL)


def log_event(text, kind="info"):
    global event_counter
    event_counter += 1
    events.append({"id": event_counter, "t": time.strftime("%H:%M:%S"), "text": text, "kind": kind})
    del events[:-12]


def get_unit(uid):
    return next((u for u in fleet if u.id == uid), None)


def tick():
    stats["ticks"] += 1
    if controlling is not None:
        stats["op_ticks"] += 1
    policy = learning["policy"]
    for u in fleet:
        if u.mode == "auto":
            u.t_auto += DT
        elif u.mode == "assist":
            u.t_assist += DT
        elif u.mode == "stuck":
            u.t_stuck += DT
        elif u.mode == "manual":
            u.t_manual += DT
        s = u.robot.get_state()
        stop = u.robot.from_drive(0, 0)

        if u.mode == "auto":
            if math.dist((s["x"], s["y"]), GOAL) < 0.3:
                u.mode = "done"
                u.robot.send_command(stop)
                log_event(f"{u.id} reached the goal", "ok")
                if u.last_tid:
                    db.set_outcome(u.last_tid, "success")
                    u.last_tid = None
            elif u.pilot.is_stuck(s):
                if learning["assist"] and policy and policy.ready:
                    u.mode = "assist"
                    u.assist_t = 0.0
                    log_event(f"{u.id} is stuck: trying the learned policy", "learn")
                else:
                    u.mode = "stuck"
                    u.stuck_since = time.time()
                    log_event(f"{u.id} is stuck and needs help", "warn")
                u.robot.send_command(stop)
                if u.last_tid:
                    db.set_outcome(u.last_tid, "failed_stuck_again")
                    u.last_tid = None
            else:
                a = u.pilot.act(s)
                u.robot.send_command(u.robot.from_drive(a["v"], a["w"]))

        elif u.mode == "assist":
            if s["x"] > u.robot.wall_x + sim.PASS_MARGIN:
                u.mode = "auto"
                u.pilot.hist = []
                stats["recoveries"] += 1
                log_event(f"{u.id} got past the wall on its own (no human needed)", "learn")
            elif u.assist_t > sim.ASSIST_TIMEOUT or policy is None:
                u.mode = "stuck"
                u.stuck_since = time.time()
                stats["assist_failures"] += 1
                u.robot.send_command(stop)
                log_event(f"{u.id}: learned policy failed, a human is needed", "warn")
            else:
                v, w = policy.act(s, u.robot.wall_x, u.robot.wall_half)
                u.robot.send_command(u.robot.from_drive(v, w))
                u.assist_t += DT

        elif u.mode == "manual":
            if time.time() - u.last_cmd_at > SAFETY_TIMEOUT:
                v, w = 0.0, 0.0              # safety stop: no commands arriving
                u.safety_stop = True
            else:
                v, w = u.cmd
                u.safety_stop = False
            u.robot.send_command(u.robot.from_drive(v, w))
            db.log_step(u.tid, s, {"v": v, "w": w})
        else:
            u.robot.send_command(stop)
        u.robot.step(DT)


def learn_from_takeovers():
    episodes = db.load_episodes(outcomes=("success", "handed_back"))
    if len(episodes) < MIN_DEMOS_TO_LEARN:
        log_event(f"Need at least {MIN_DEMOS_TO_LEARN} takeovers to learn from "
                  f"(you have {len(episodes)})", "warn")
        return
    policy = KNNPolicy().fit(episodes, source="your takeovers")
    if not policy.ready:
        log_event("Your takeovers contain no steering to learn from", "warn")
        return
    learning["policy"] = policy
    log_event(f"Learned from {policy.meta['demos']} of your takeovers "
              f"({policy.meta['samples']} decisions)", "learn")


def handle(msg):
    global fleet, controlling, stats
    kind = msg["type"]
    if kind == "reset":
        cu = get_unit(controlling) if controlling else None
        if cu and cu.tid:
            db.end_takeover(cu.tid, "reset")
        fleet = make_fleet()
        controlling = None
        stats = new_stats()
        log_event("Demo restarted with new walls")
    elif kind == "takeover":
        u = get_unit(msg.get("robot"))
        if u and u.mode == "stuck" and controlling is None:
            u.mode = "manual"
            u.cmd = (0.0, 0.0)
            u.last_cmd_at = time.time()
            u.tid = db.start_takeover(u.id, u.robot.kind, u.robot.wall_x, u.robot.wall_half)
            controlling = u.id
            stats["takeovers"] += 1
            stats["waits"].append(time.time() - u.stuck_since)
            log_event(f"Operator took over {u.id}")
    elif kind == "cmd":
        cu = get_unit(controlling) if controlling else None
        if cu:
            cu.cmd = (msg["v"], msg["w"])
            cu.last_cmd_at = time.time()
    elif kind == "handback":
        cu = get_unit(controlling) if controlling else None
        if cu:
            db.end_takeover(cu.tid, "handed_back")
            cu.last_tid = cu.tid
            cu.tid = None
            cu.mode = "auto"
            cu.safety_stop = False
            cu.pilot.hist = []
            controlling = None
            log_event(f"{cu.id} handed back to the autopilot")
    elif kind == "net":
        net["name"] = msg["name"]
        net["delay"] = msg["delay"]
        net["loss"] = msg["loss"]
    elif kind == "assist":
        learning["assist"] = bool(msg["on"])
        log_event("Learned assist is " + ("ON" if learning["assist"] else "OFF"), "learn")
    elif kind == "learn":
        learn_from_takeovers()


def make_stats():
    elapsed = stats["ticks"] * DT
    robot_hours = len(fleet) * elapsed / 3600
    t_auto = sum(u.t_auto + u.t_assist for u in fleet)       # no human involved
    t_busy = t_auto + sum(u.t_stuck + u.t_manual for u in fleet)
    waits = stats["waits"]
    return {
        "robots": len(fleet),
        "takeovers": stats["takeovers"],
        "recoveries": stats["recoveries"],
        "assist_failures": stats["assist_failures"],
        "per_robot_hour": round(stats["takeovers"] / robot_hours, 1) if robot_hours else 0,
        "autonomous_pct": round(100 * t_auto / t_busy) if t_busy else 100,
        "operator_busy_pct": round(100 * stats["op_ticks"] / stats["ticks"]) if stats["ticks"] else 0,
        "avg_wait": round(sum(waits) / len(waits), 1) if waits else 0,
    }


def snapshot():
    now = time.time()
    robots = []
    for u in fleet:
        robots.append({
            "id": u.id,
            "kind": u.robot.kind,
            "wall_x": u.robot.wall_x,
            "wall_half": u.robot.wall_half,
            **u.robot.get_state(),
            "mode": u.mode,
            "safety": u.safety_stop,
            "native": {k: round(val, 2) for k, val in u.robot.cmd.items()},
            "waiting": round(now - u.stuck_since, 1) if u.mode == "stuck" else None,
        })
    waiting = [r for r in robots if r["mode"] == "stuck"]
    waiting.sort(key=lambda r: -r["waiting"])
    policy = learning["policy"]
    return json.dumps({
        "robots": robots,
        "queue": [r["id"] for r in waiting],
        "controlling": controlling,
        "net": net["name"],
        "stats": make_stats(),
        "assist": learning["assist"],
        "model": policy.meta if policy and policy.ready else None,
        "events": events[-8:],
    })


def spawn(coro):
    task = asyncio.create_task(coro)
    background.add(task)
    task.add_done_callback(background.discard)


async def send_later(ws, text, delay):
    if delay:
        await asyncio.sleep(delay)
    try:
        await ws.send_text(text)
    except Exception:
        clients.discard(ws)


async def broadcast(text):
    half = net["delay"] / 2000          # half of the delay on the way out
    for ws in list(clients):
        if half:
            spawn(send_later(ws, text, half))
        else:
            await send_later(ws, text, 0)


async def process(ws, msg):
    kind = msg["type"]
    if kind in ("cmd", "ping"):
        half = net["delay"] / 2000      # half of the delay on the way in
        if half:
            await asyncio.sleep(half)
        if random.random() < net["loss"]:
            return                      # message lost
        if kind == "ping":
            await send_later(ws, json.dumps({"type": "pong", "t": msg["t"]}), half)
            return
    handle(msg)


async def loop():
    while True:
        tick()
        await broadcast(snapshot())
        await asyncio.sleep(DT)


@asynccontextmanager
async def lifespan(app):
    load_model()
    task = asyncio.create_task(loop())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)


@app.get("/")
def home():
    return FileResponse(PAGE)


@app.get("/api/learning")
def learning_results():
    """Results of evaluate.py, shown as a chart in the console."""
    if RESULTS.exists():
        return JSONResponse(json.loads(RESULTS.read_text(encoding="utf-8")))
    return JSONResponse({"curve": []})


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)
    try:
        while True:
            spawn(process(websocket, json.loads(await websocket.receive_text())))
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(websocket)
