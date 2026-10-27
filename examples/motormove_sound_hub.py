# ===== Hub — broadcast the motor's position, so a computer can play a sound when it turns =====
# Turn the motor by hand (or drive it from your program). The hub broadcasts
# the motor's position in degrees about 10 times a second, and
# motormove_sound_computer.py, running on a computer, plays a sound each time
# the motor has turned 20 degrees or more. It's a broadcast, so any number of
# computers and hubs can listen at once (a hub listens with Scanner("!M")).
#
# How to run: start this program from the REPL over USB, e.g.
# `mpremote run motormove_sound_hub.py` (not with the SPIKE App's Run button:
# programs it starts can't use Bluetooth). Once it says it's broadcasting you
# can unplug the cable. Press Ctrl-C in the REPL to stop.
#
# Hub screen: an arrow that turns with the motor.
from spikecomm import Beacon
from hub import port, light_matrix
import motor
import time

MOTOR_PORT = port.A     # the port your motor is plugged into

# One arrow for every 45 degrees the motor turns
ARROWS = [
    light_matrix.IMAGE_ARROW_N, light_matrix.IMAGE_ARROW_NE,
    light_matrix.IMAGE_ARROW_E, light_matrix.IMAGE_ARROW_SE,
    light_matrix.IMAGE_ARROW_S, light_matrix.IMAGE_ARROW_SW,
    light_matrix.IMAGE_ARROW_W, light_matrix.IMAGE_ARROW_NW,
]

b = Beacon("!M")
print("Hub: broadcasting the motor position as !M<degrees>")

shown = None
try:
    while True:
        # relative_position keeps counting past a full turn (360, 370, 720, ...)
        # and goes negative backwards, so the computer can simply subtract two
        # readings. (absolute_position jumps from 179 to -180 halfway round.)
        degrees = motor.relative_position(MOTOR_PORT)
        b.broadcast(degrees)                # e.g. "!M-725"
        arrow = round(degrees / 45) % 8
        if arrow != shown:
            light_matrix.show_image(ARROWS[arrow])
            print("Motor at", degrees, "degrees")
            shown = arrow
        time.sleep_ms(100)
finally:
    # Ctrl-C ends the loop, but the Beacon would keep broadcasting the last
    # position: stop it, so listeners can tell the hub has gone.
    b.stop()
    light_matrix.clear()
    print("Stopped")
