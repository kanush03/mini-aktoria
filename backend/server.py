import asyncio
import json
import math
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from adapters.wheeled import WheeledRobot
from policy import AutoPilot
import db

app = FastAPI()
PAGE = Path(__file__).parent.parent / "frontend" / "index.html"

@app.get("/")
def home():
    return FileResponse(PAGE)

@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    robot = WheeledRobot()
    pilot = AutoPilot(goal=(10, 0), stuck_window=30)
    state = {"mode": "auto", "cmd": {"v": 0, "w": 0}, "tid": None, "last_tid": None}
    stop = {"v": 0, "w": 0}

    async def receive():
        try:
            while True:
                msg = json.loads(await websocket.receive_text())
                if msg["type"] == "takeover" and state["mode"] == "stuck":
                    state["mode"] = "manual"
                    state["tid"] = db.start_takeover()
                elif msg["type"] == "cmd" and state["mode"] == "manual":
                    state["cmd"] = {"v": msg["v"], "w": msg["w"]}
                elif msg["type"] == "handback" and state["mode"] == "manual":
                    db.end_takeover(state["tid"], "handed_back")
                    state["last_tid"] = state["tid"]
                    state["tid"] = None
                    state["mode"] = "auto"
                    pilot.hist = []
        except WebSocketDisconnect:
            pass

    task = asyncio.create_task(receive())
    try:
        while not task.done():
            s = robot.get_state()
            if state["mode"] == "auto":
                if math.dist((s["x"], s["y"]), pilot.goal) < 0.3:
                    state["mode"] = "done"
                    robot.send_command(stop)
                    if state["last_tid"]:
                        db.set_outcome(state["last_tid"], "success")
                elif pilot.is_stuck(s):
                    state["mode"] = "stuck"
                    robot.send_command(stop)
                    if state["last_tid"]:
                        db.set_outcome(state["last_tid"], "failed_stuck_again")
                else:
                    robot.send_command(pilot.act(s))
            elif state["mode"] == "manual":
                robot.send_command(state["cmd"])
                db.log_step(state["tid"], s, state["cmd"])
            else:
                robot.send_command(stop)
            robot.step(0.05)
            await websocket.send_text(json.dumps({**s, "mode": state["mode"]}))
            await asyncio.sleep(0.05)
    except Exception:
        pass
    finally:
        task.cancel()
        if state["tid"]:
            db.end_takeover(state["tid"], "disconnected")