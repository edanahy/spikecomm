# ===== Hub (robot car) — driven from a web page =====
# The web page (index.html in this folder) connects to this hub over Bluetooth
# and sends a move and a speed, like "forward;500", whenever you press a key:
#   W forward   A left   S back   D right   Space stop
#
# How to run:
#   1. Start this program from the REPL over USB, e.g. `mpremote run main.py`
#      (not with the SPIKE App's Run button: programs it starts can't use
#      Bluetooth). Once it says it's waiting you can unplug the cable.
#   2. Open index.html in Chrome or Edge, click Connect and pick your hub.
#      The list shows it as SPIKE or by the hub's own name (the one it has in
#      the SPIKE App): once a computer has connected to a hub, the browser
#      may keep using that name.
#   3. Press Ctrl-C in the REPL to stop: the car stops, the page is
#      disconnected and the hub stops advertising.
#
# Hub screen:
#   X       no web page connected (motors stopped)
#   check   connected, stopped
#   arrow   driving that way
from spikecomm import Peripheral, decode
from hub import port, light_matrix
import motor
import time

LEFT_MOTOR = port.A
RIGHT_MOTOR = port.B
# On most cars the two motors face opposite ways, so one turns backwards to
# drive forwards. If W drives the car backwards, swap the -1 and the 1.
# If W makes it spin on the spot, make both 1.
LEFT_DIRECTION = -1
RIGHT_DIRECTION = 1

# How fast each wheel turns for each move, as a share of the speed
MOVES = {
    "forward": (1, 1),
    "back":    (-1, -1),
    "left":    (-0.5, 0.5),     # turn on the spot, at half speed
    "right":   (0.5, -0.5),
    "stop":    (0, 0),
}
PICTURES = {
    "forward": light_matrix.IMAGE_ARROW_N,
    "back":    light_matrix.IMAGE_ARROW_S,
    "left":    light_matrix.IMAGE_ARROW_W,
    "right":   light_matrix.IMAGE_ARROW_E,
    "stop":    light_matrix.IMAGE_YES,
}

p = Peripheral()        # advertises as "SPIKE"
p.advertise()

latest = {"move": "stop", "speed": 0}


def on_command(msg):
    # msg looks like "forward;500": a move, then a speed in degrees per second
    values = decode(msg)
    if len(values) == 2 and values[0] in MOVES:
        speed = min(abs(int(values[1])), 1000)     # degrees per second, 0 to 1000
        latest["move"] = values[0]
        latest["speed"] = speed
        p.send(msg)     # echo it back so the page knows it arrived


p.listen(on_command)
print("Waiting for the web page to connect ...")


def drive(move, speed):
    if move == "stop":
        motor.stop(LEFT_MOTOR)
        motor.stop(RIGHT_MOTOR)
    else:
        left, right = MOVES[move]
        motor.run(LEFT_MOTOR, round(LEFT_DIRECTION * left * speed))
        motor.run(RIGHT_MOTOR, round(RIGHT_DIRECTION * right * speed))


shown = None            # what the motors and screen are doing now
try:
    while True:
        connected = p.is_connected
        if not connected:
            latest["move"] = "stop"     # page closed or out of range: stop the car
        now = (latest["move"], latest["speed"], connected)
        if now != shown:
            move, speed, connected = now
            drive(move, speed)
            if connected:
                light_matrix.show_image(PICTURES[move])
                print("Move:", move, "at", speed, "deg/s")
            else:
                light_matrix.show_image(light_matrix.IMAGE_NO)
                print("No web page connected")
            shown = now
        time.sleep_ms(20)
finally:
    # Ctrl-C (or an error) ends the loop, but Bluetooth would keep going:
    # stop the car, then stop advertising before disconnecting the page,
    # or the hub starts advertising again as soon as the page is gone.
    drive("stop", 0)
    p.stop_advertising()
    p.disconnect()
    light_matrix.clear()
    print("Stopped")
