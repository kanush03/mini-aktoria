import asyncio
import json
import math
import random
import time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from adapters.wheeled import WheeledRobot
from adapters.diffdrive import DiffDriveRobot
from policy import AutoPilot
import db

PAGE = Path(__file__).parent.parent / "frontend" / "index.html"
GOAL = (10, 0)
DT = 0.05
SAFETY_TIMEOUT = 0.5   # seconds without operator commands -> robot stops


class Unit:
    def __init__(self, uid, robot):
        self.id = uid
        self.robot = robot
        self.pilot = AutoPilot(goal=GOAL, stuck_window=30)
        self.mode = "auto"          # auto, stuck, manual, done
        self.stuck_since = None
        self.tid = None
        self.last_tid = None
        self.cmd = (0.0, 0.0)       # operator command: (v, w)
        self.last_cmd_at = 0.0
        self.safety_stop = False


def make_fleet():
    return [
        Unit("R1", WheeledRobot(wall_x=5.0)),
        Unit("R2", DiffDriveRobot(wall_x=4.0)),
        Unit("R3", WheeledRobot(wall_x=6.0)),
    ]


fleet = make_fleet()
controlling = None
clients = set()
background = set()
net = {"name": "Good", "delay": 0, "loss": 0.0}   # simulated network


def get_unit(uid):
    return next((u for u in fleet if u.id == uid), None)


def tick():
    for u in fleet:
        s = u.robot.get_state()
        stop = u.robot.from_drive(0, 0)
        if u.mode == "auto":
            if math.dist((s["x"], s["y"]), GOAL) < 0.3:
                u.mode = "done"
                u.robot.send_command(stop)
                if u.last_tid:
                    db.set_outcome(u.last_tid, "success")
                    u.last_tid = None
            elif u.pilot.is_stuck(s):
                u.mode = "stuck"
                u.stuck_since = time.time()
                u.robot.send_command(stop)
                if u.last_tid:
                    db.set_outcome(u.last_tid, "failed_stuck_again")
                    u.last_tid = None
            else:
                a = u.pilot.act(s)
                u.robot.send_command(u.robot.from_drive(a["v"], a["w"]))
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


def handle(msg):
    global fleet, controlling
    kind = msg["type"]
    if kind == "reset":
        cu = get_unit(controlling) if controlling else None
        if cu and cu.tid:
            db.end_takeover(cu.tid, "reset")
        fleet = make_fleet()
        controlling = None
    elif kind == "takeover":
        u = get_unit(msg.get("robot"))
        if u and u.mode == "stuck" and controlling is None:
            u.mode = "manual"
            u.cmd = (0.0, 0.0)
            u.last_cmd_at = time.time()
            u.tid = db.start_takeover(u.id, u.robot.kind)
            controlling = u.id
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
    elif kind == "net":
        net["name"] = msg["name"]
        net["delay"] = msg["delay"]
        net["loss"] = msg["loss"]


def snapshot():
    now = time.time()
    robots = []
    for u in fleet:
        robots.append({
            "id": u.id,
            "kind": u.robot.kind,
            "wall_x": u.robot.wall_x,
            **u.robot.get_state(),
            "mode": u.mode,
            "safety": u.safety_stop,
            "native": {k: round(val, 2) for k, val in u.robot.cmd.items()},
            "waiting": round(now - u.stuck_since, 1) if u.mode == "stuck" else None,
        })
    waiting = [r for r in robots if r["mode"] == "stuck"]
    waiting.sort(key=lambda r: -r["waiting"])
    return json.dumps({
        "robots": robots,
        "queue": [r["id"] for r in waiting],
        "controlling": controlling,
        "net": net["name"],
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
    task = asyncio.create_task(loop())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)


@app.get("/")
def home():
    return FileResponse(PAGE)


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