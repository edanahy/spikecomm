# ===== Hub B — spin a motor 3 times when Hub A sees something closer than 50 cm =====
# Hub B's screen:
#   bar graph       watching Hub A's distance (the same bar Hub A shows)
#   turning arrow   the motor is spinning (the arrow follows the motor)
#   check mark      done; waiting for the object to move away before it can go again
#   X               no signal from Hub A
from spikecomm import Scanner
from hub import port, light_matrix
import motor
import time

MOTOR_PORT = port.A     # the port your motor is plugged into
TRIGGER_CM = 50         # spin when the object comes closer than this
REARM_CM = 55           # go again only after it moves back past this (a little farther,
                        # so a reading that wobbles around 50 cm doesn't retrigger)
TURNS = 3
SPEED = 720             # degrees per second (2 turns per second)

PICTURES = {
    "lost": light_matrix.IMAGE_NO,
    "done": light_matrix.IMAGE_YES,
    "N": light_matrix.IMAGE_ARROW_N,  "NE": light_matrix.IMAGE_ARROW_NE,
    "E": light_matrix.IMAGE_ARROW_E,  "SE": light_matrix.IMAGE_ARROW_SE,
    "S": light_matrix.IMAGE_ARROW_S,  "SW": light_matrix.IMAGE_ARROW_SW,
    "W": light_matrix.IMAGE_ARROW_W,  "NW": light_matrix.IMAGE_ARROW_NW,
}
SPIN = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]   # one arrow per 45 degrees turned


def bar_rows(cm):
    """How many rows to light: one more for every 25 cm closer than 125 cm."""
    if cm < 0:                      # -1 = nothing detected
        return 0
    return max(0, 5 - cm // 25)     # 0-24 cm: 5 rows, 25-49 cm: 4, ... 125+ cm: 0


def show_bar(rows):
    """Light `rows` rows from the bottom; the bottom row is always at least dim."""
    pixels = []
    for y in range(5):              # y = 0 is the top row
        if y >= 5 - rows:
            pixels += [100] * 5
        elif y == 4:
            pixels += [20] * 5
        else:
            pixels += [0] * 5
    light_matrix.show(pixels)       # 25 brightness values, 0-100


latest = {"cm": None, "time": 0}


def on_distance(values):
    # values looks like [42]; ignore anything else
    if len(values) == 1:
        latest["cm"] = values[0]
        latest["time"] = time.ticks_ms()


s = Scanner("!D")
s.listen(on_distance)
print("Hub B: waiting for Hub A ...")

state = "watching"      # "watching" -> "spinning" -> "done" -> "watching"
start = 0               # motor position when the spin started
turned = 0              # degrees turned so far in this spin
shown = None
while True:
    cm = latest["cm"]
    heard = cm is not None and time.ticks_diff(time.ticks_ms(), latest["time"]) < 1500

    if state == "watching":
        if heard and 0 <= cm < TRIGGER_CM:
            print("Object at", cm, "cm: spinning the motor", TURNS, "times")
            start = motor.relative_position(MOTOR_PORT)
            turned = 0
            motor.run_for_degrees(MOTOR_PORT, TURNS * 360, SPEED)   # starts the motor and
            state = "spinning"                                       # returns right away
    elif state == "spinning":
        turned = abs(motor.relative_position(MOTOR_PORT) - start)
        if turned >= TURNS * 360 - 5:       # the motor stops itself at the target
            print("Done. Move the object farther than", REARM_CM, "cm to go again")
            state = "done"
    elif state == "done":
        if heard and (cm < 0 or cm >= REARM_CM):
            print("Watching again")
            state = "watching"

    # Pick what the screen should show, and redraw only when it changes
    if state == "spinning":
        want = SPIN[(turned // 45) % 8]
    elif not heard:
        want = "lost"
    elif state == "done":
        want = "done"
    else:
        want = bar_rows(cm)         # a number of rows, 0-5
    if want != shown:
        if want in PICTURES:
            light_matrix.show_image(PICTURES[want])
        else:
            show_bar(want)
        if want == "lost":
            print("No signal from Hub A")
        elif state == "watching":
            print("Hub A sees:", "nothing" if cm < 0 else str(cm) + " cm")
        shown = want
    time.sleep_ms(20)
