# ===== Hub B — show an arrow for the way Hub A is tilting =====
from spikecomm import Scanner
from hub import light_matrix
import time

ARROWS = {
    "N": light_matrix.IMAGE_ARROW_N,  "NE": light_matrix.IMAGE_ARROW_NE,
    "E": light_matrix.IMAGE_ARROW_E,  "SE": light_matrix.IMAGE_ARROW_SE,
    "S": light_matrix.IMAGE_ARROW_S,  "SW": light_matrix.IMAGE_ARROW_SW,
    "W": light_matrix.IMAGE_ARROW_W,  "NW": light_matrix.IMAGE_ARROW_NW,
    "C": light_matrix.IMAGE_SQUARE_SMALL,      # Hub A is lying flat
}

latest = {"dir": None, "pitch": 0, "roll": 0, "time": 0}


def on_tilt(values):
    # values looks like ["NE", 23, -18]; ignore anything else
    if len(values) == 3:
        latest["dir"], latest["pitch"], latest["roll"] = values
        latest["time"] = time.ticks_ms()


s = Scanner("!T")
s.listen(on_tilt)
print("Hub B: waiting for Hub A ...")

shown = None
while True:
    if time.ticks_diff(time.ticks_ms(), latest["time"]) > 1500:
        want = "lost"                  # nothing heard from Hub A for 1.5 s
    else:
        want = latest["dir"]
    if want != shown:
        if want == "lost":
            light_matrix.show_image(light_matrix.IMAGE_NO)
            print("No signal from Hub A")
        else:
            light_matrix.show_image(ARROWS.get(want, light_matrix.IMAGE_CONFUSED))
            print("Hub A is tilting", want, "(pitch", latest["pitch"], "roll", latest["roll"], ")")
        shown = want
    time.sleep_ms(50)
