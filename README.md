# mini-aktoria
Simulated remote robot operation with human takeover and intervention logging
# Mini Aktoria

A small-scale simulation of **remote robot operation with human takeover**.

Robots drive themselves until they get stuck. When that happens, a remote human operator takes control through a web console, solves the problem, and hands control back. Every takeover is recorded as data that could later be used to improve the robot's autonomy.

> **Status: 🚧 In progress.** Actively being built. See the roadmap below for what works so far.

> Independent student project, inspired by the idea of a teleoperation layer for robots. Not affiliated with any company.

---

## Why this project

Autonomous robots still fail on edge cases: an unexpected obstacle, a situation they were never trained on. A common solution is to let a remote human step in. This project recreates that loop end to end, in simulation, so it can run on any laptop with no hardware.

It focuses on three problems:

1. **Remote control with low delay:** sending commands and receiving robot state in real time.
2. **Working with different robots:** one console that can operate robots with completely different controls.
3. **Learning from human help:** logging each takeover as structured data.

---

## How it works

```
 Simulated robots            Adapter layer              Operator console
┌───────────────┐        ┌─────────────────┐        ┌───────────────────┐
│ Wheeled robot │◄──────►│ common interface│◄──────►│ live view + keys  │
│ Robot arm     │        │ get_state()     │  WS    │ latency display   │
└───────────────┘        │ send_command()  │        │ "help needed" alert│
        ▲                └─────────────────┘        └───────────────────┘
        │                                                     │
  Autonomous policy                                           ▼
 (drives the robot,                              Takeover log (SQLite)
  detects "stuck")                               state · action · timestamp
                                                              │
                                                              ▼
                                                      Ops dashboard
```

- **Simulated robots:** 2–3 robots doing simple navigation tasks.
- **Autonomous policy:** a basic auto-pilot that drives toward a goal and flags when it is stuck.
- **Adapter layer:** a shared interface so different robot types plug into the same console.
- **Operator console:** a web page where a human watches and steers a robot over WebSockets.
- **Takeover logging:** each human intervention is saved as a structured episode.
- **Ops dashboard:** interventions per hour, latency, and operator workload.

---

## Planned tech stack

| Part | Tools |
|---|---|
| Backend | Python, FastAPI, WebSockets |
| Simulation | 2D simulation (browser or Python) |
| Frontend | React |
| Data | SQLite |

---

## What I'm learning

- Real-time communication with WebSockets
- Designing clean interfaces so different systems can work together
- Structuring human-in-the-loop data for robot learning

---

## Author

**Kanush Sachdeva**
[GitHub](https://github.com/kanush03) · [LinkedIn](https://linkedin.com/in/kanush-sachdeva-5b63a9274)
