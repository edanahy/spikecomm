# ===== Hub A — measure distance with the ultrasonic sensor and broadcast it =====
# Hub A shows the distance as a bar on its own screen: the closer the object,
# the more rows light up from the bottom (4 or more rows = closer than 50 cm).
# A dim bottom row means the program is running but nothing is close.
from spikecomm import Beacon
from hub import port, light_matrix
import distance_sensor
import time

SENSOR_PORT = port.A    # the port your distance (ultrasonic) sensor is plugged into


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


b = Beacon("!D")
print("Hub A: broadcasting distance as !D<cm> (-1 = nothing detected)")

shown = None
while True:
    mm = distance_sensor.distance(SENSOR_PORT)   # millimetres; -1 if nothing detected
    cm = -1 if mm < 0 else round(mm / 10)
    b.broadcast(cm)                              # e.g. "!D42"
    rows = bar_rows(cm)
    if rows != shown:
        show_bar(rows)
        print("Distance:", "nothing detected" if cm < 0 else str(cm) + " cm")
        shown = rows
    time.sleep_ms(100)
