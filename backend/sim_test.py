from adapters.wheeled import WheeledRobot
from policy import AutoPilot

robot = WheeledRobot()
pilot = AutoPilot(goal=(10, 0))

for t in range(500):
    s = robot.get_state()
    if t % 20 == 0:
        print(t, "x =", round(s["x"], 2))
    if pilot.is_stuck(s):
        print(f"STUCK at step {t}, x = {round(s['x'], 2)}")
        break
    robot.send_command(pilot.act(s))
    robot.step(0.05)