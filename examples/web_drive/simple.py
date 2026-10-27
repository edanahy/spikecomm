# ===== Hub: send and receive messages with a web page (simple.html) =====
# 1. Start this program from the REPL over USB, e.g. `mpremote run simple.py`
#    (not with the SPIKE App's Run button: programs it starts can't use Bluetooth).
# 2. Open simple.html in Chrome or Edge, click Connect and pick this hub.
from spikecomm import Peripheral
from hub import button, light_matrix
import time

p = Peripheral("Hub1")      # the name the browser shows: give every hub its own
p.advertise()


def on_message(msg):
    # Runs each time the web page sends a message
    print("Received:", msg)
    if msg == "smile":
        light_matrix.show_image(light_matrix.IMAGE_HAPPY)
    p.send("Hub got: " + msg)       # reply to the page


p.listen(on_message)
print("Waiting for the web page ...")

while True:
    # The hub can send on its own too: tell the page when the left button is pressed
    if button.pressed(button.LEFT):
        p.send("Left button pressed")
        while button.pressed(button.LEFT):      # wait until it's let go
            time.sleep_ms(20)
    time.sleep_ms(20)
