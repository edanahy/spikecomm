# ===== Hub A — read the tilt and broadcast which way the hub is leaning =====
# Hub A also shows the arrow on its own screen, so you can check the
# directions before looking at Hub B.
from spikecomm import Beacon
from hub import motion_sensor, light_matrix
import time

TILT = 15          # degrees of lean before it counts as "tilted"
FLIP_NS = False    # set True if the arrow points backwards when you tilt forward/back
FLIP_EW = False    # set True if the left/right arrows are swapped

ARROWS = {
    "N": light_matrix.IMAGE_ARROW_N,  "NE": light_matrix.IMAGE_ARROW_NE,
    "E": light_matrix.IMAGE_ARROW_E,  "SE": light_matrix.IMAGE_ARROW_SE,
    "S": light_matrix.IMAGE_ARROW_S,  "SW": light_matrix.IMAGE_ARROW_SW,
    "W": light_matrix.IMAGE_ARROW_W,  "NW": light_matrix.IMAGE_ARROW_NW,
    "C": light_matrix.IMAGE_SQUARE_SMALL,      # lying flat
}


def direction(pitch, roll):
    """Turn pitch/roll (degrees) into "N", "NE", "E", ... or "C" for flat."""
    if FLIP_NS:
        pitch = -pitch
    if FLIP_EW:
        roll = -roll
    ns = "N" if pitch > TILT else "S" if pitch < -TILT else ""
    ew = "E" if roll > TILT else "W" if roll < -TILT else ""
    return (ns + ew) or "C"


b = Beacon("!T")
print("Hub A: broadcasting tilt as !T<direction>;<pitch>;<roll>")

shown = None
while True:
    yaw, pitch, roll = motion_sensor.tilt_angles()   # tenths of a degree
    pitch = round(pitch / 10)                         # whole degrees
    roll = round(roll / 10)
    d = direction(pitch, roll)
    b.broadcast(d, pitch, roll)                       # e.g. "!TNE;23;-18"
    if d != shown:
        light_matrix.show_image(ARROWS[d])
        print("Tilting", d, "(pitch", pitch, "roll", roll, ")")
        shown = d
    time.sleep_ms(100)
