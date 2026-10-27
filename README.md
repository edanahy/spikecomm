# spikecomm

**Bluetooth communication library for LEGO SPIKE Prime**
*Single-file MicroPython module — copy to hub, import, go.*

`spikecomm` makes it easy for LEGO SPIKE Prime hubs to talk to each other over Bluetooth. It supports two communication styles — **Beacon mode** (broadcast, no connection needed) and **Direct mode** (full BLE connection, two-way messaging) — with a consistent, student-friendly API across both. A hub can also talk to a **web page** in Chrome or Edge: see [Talking to a Web Page](#talking-to-a-web-page).

**Works with:** SPIKE Prime hubs running the **SPIKE App 3** firmware (the Python in the current LEGO Education SPIKE App). Tested hub-to-hub on firmware built 2025-03-27 (MicroPython 1.24 core, hub OS 1.8.149), and hub-to-web-page with Chrome 156 on macOS.

> **Important:** start spikecomm programs from the hub's **REPL** over USB, not with the SPIKE App's Run button or the hub's program menu — the firmware blocks Bluetooth for programs the hub starts itself. Once started, a program keeps running after you unplug the USB cable. See [Running spikecomm programs](#running-spikecomm-programs).

---

## Table of Contents

1. [Installation](#installation)
2. [Running spikecomm programs](#running-spikecomm-programs)
3. [Choosing a Mode](#choosing-a-mode)
4. [Beacon Mode](#beacon-mode) — `Beacon` and `Scanner`
5. [Direct Mode](#direct-mode) — `Peripheral` and `Central`
6. [Encoding and Decoding Multiple Values](#encoding-and-decoding-multiple-values)
7. [Waiting for a Condition — `wait_for`](#waiting-for-a-condition--wait_for)
8. [Callback Rules](#callback-rules)
9. [Debugging with `verbose=True`](#debugging-with-verbosetrue)
10. [Complete Examples](#complete-examples)
11. [Talking to a Web Page](#talking-to-a-web-page) — Web Bluetooth in Chrome or Edge
12. [API Quick Reference](#api-quick-reference)
13. [Limitations and Tips](#limitations-and-tips)

---

## Installation

`spikecomm.py` has to be copied onto each hub's file system (into `/flash`, next to the hub's own files). The SPIKE App can't do this, so use a MicroPython file tool over USB. One that works is **mpremote**:

1. Install it on your computer (once): `pip install mpremote`
2. Plug **one** hub into the computer with USB. Close the SPIKE App (or disconnect the hub in it) so the USB port is free.
3. Copy the file:
   ```
   mpremote cp spikecomm.py :spikecomm.py
   ```
4. Check it's there: `mpremote ls` should list `spikecomm.py`.
5. Repeat for every hub in your group.

If several hubs are plugged in at once, run `mpremote connect list` and pick one: `mpremote connect /dev/cu.usbmodemXXXX cp spikecomm.py :spikecomm.py` (on Windows the port looks like `COM5`).

Then, in your program, import what you need:

```python
from spikecomm import Beacon, Scanner          # for broadcast mode
from spikecomm import Peripheral, Central      # for direct connection mode
from spikecomm import encode, decode           # value helpers (optional)
```

To check the install, run `import spikecomm; print(spikecomm.__version__)` — it should print `1.2.0`.

**Keep only one copy on each hub.** The file works in either `/flash` or `/flash/lib`, but if both exist the hub loads the one in `/flash`, so updating the other copy would have no effect. `print(spikecomm.__file__)` shows which copy is being used; delete the extra one with `import os; os.remove("/flash/spikecomm.py")` (or `"/flash/lib/spikecomm.py"`).

---

## Running spikecomm programs

On the SPIKE App 3 firmware, a program **started by the hub itself** — with the SPIKE App's Run button, or from the hub's program menu — is not allowed to use Bluetooth, because the hub's own software is using the radio. spikecomm then stops with:

```
ImportError: spikecomm can't use Bluetooth in a program started from a program slot or the SPIKE App's Run button. ...
```

Instead, start the program from the hub's **REPL** (the `>>>` prompt you get over a USB serial connection). Any of these works:

- **Paste mode**, in a serial terminal or a web tool's USB-serial mode: press **Ctrl-C** (stop whatever is running), **Ctrl-E** (paste mode), paste the program, then press **Ctrl-D** to run it.
- **A program already saved in a slot** (for example downloaded to slot 0): at the `>>>` prompt type
  ```python
  exec(open("/flash/program/00/program.py").read())
  ```
  using the two-digit slot number (slot 3 is `03`).
- **From a computer terminal:** `mpremote run myprogram.py`.

Then you can **unplug the USB cable** — the program keeps running on the hub's battery, so robots can drive untethered.

To stop it, plug the cable back in and press **Ctrl-C**. When you're done, press **Ctrl-D** at the `>>>` prompt (or restart the hub) to return to normal, so the SPIKE App and the hub's menu work again.

---

## Choosing a Mode

| | Beacon / Scanner | Peripheral / Central |
|---|---|---|
| **Connection?** | No — passive broadcast | Yes — paired connection |
| **Direction** | One sender → many receivers (a hub can do both) | Two-way between two hubs |
| **Data limit** | 26 characters total (prefix + data), e.g. ~24 for data | Up to 1000 characters per message |
| **Delivery** | Best-effort (like radio); receivers see the *latest* value | Every message, in order, while connected |
| **How many hubs?** | Any number | One Central per Peripheral |
| **Setup** | `Beacon` on sender, `Scanner` on receiver | `Peripheral` on server, `Central` on client |
| **Best for** | Sensor broadcasts, groups of 3+ hubs | Commands, responses, text |

**Rule of thumb:** Use Beacon/Scanner when you're sharing sensor readings or status with any number of hubs (each hub can broadcast *and* listen at the same time). Use Peripheral/Central when two specific hubs need every message to arrive, like commands.

**Talking to a web page?** The hub runs a `Peripheral` and the page connects to it; a page can't use Beacon mode. See [Talking to a Web Page](#talking-to-a-web-page).

---

## Beacon Mode

A **Beacon** encodes values into this hub's BLE advertising name. Any **Scanner** nearby can read that name without connecting. Think of it like a radio transmitter and receiver.

### Beacon (sender)

```python
from spikecomm import Beacon

b = Beacon("!S")        # "!S" is a unique tag that identifies this hub's data
b.broadcast(42)         # advertises the name "!S42"
b.broadcast(42, 3.14)   # advertises "!S42;3.14"
b.stop()                # stop broadcasting
```

**Constructor:**
```python
Beacon(prefix="!S", interval_ms=100, verbose=False)
```
- `prefix` — a short unique tag (2–3 chars, max 5) prepended to every broadcast. Pick something unlikely to clash, like `"!A"`, `"!B"`, `"!C"`. Must match the Scanner's prefix. **One prefix must not be the start of another**: `"!S"` and `"!S1"` clash, because a `Scanner("!S")` also hears `"!S1..."`.
- `interval_ms` — how often to re-send the advertisement. Default 100 ms, which is also the minimum (smaller values are raised to 100).
- `verbose` — print debug output. See [Debugging](#debugging-with-verbosetrue).

**Methods:**

```python
b.broadcast(*values, sep=";", precision=2)
# Encodes values and starts (or updates) the BLE advertisement.
# Values can be numbers, booleans, or short strings.
# Raises ValueError if the encoded name exceeds 26 characters.
# If the data hasn't changed, the call does nothing — safe to call in a fast loop.

b.stop()                # stop advertising
b.is_broadcasting       # True if currently transmitting (property)
```

**Prefix and name length:** The full advertised name is `prefix + encoded_values`. BLE limits this to **26 characters total**. With a 2-character prefix like `"!S"`, that leaves 24 characters for data. Compact numbers (integers, short floats) work best.

```python
# These all fit within 26 chars with prefix "!S":
b.broadcast(42)                      # "!S42"             — 4 chars
b.broadcast(42, 3.14)                # "!S42;3.14"        — 9 chars
b.broadcast(255, 128, 64)            # "!S255;128;64"     — 12 chars
b.broadcast(1023, 37.5, -12)         # "!S1023;37.5;-12"  — 15 chars

# This will raise ValueError — too long:
b.broadcast(123456, 3.14159, 999999, 123456)  # "!S123456;3.14;999999;123456" — 27 chars
```

### Scanner (receiver)

```python
from spikecomm import Scanner

s = Scanner("!S")       # only picks up Beacons with the matching prefix
```

**Constructor:**
```python
Scanner(prefix="!S", verbose=False)
```

You can create several Scanners on one hub (one per prefix), and a hub can run a Beacon and Scanners at the same time.

**Three ways to receive data:**

#### 1. `listen(callback)` — continuous, non-blocking

Best for loops where you react to live data. The callback runs about 10 times per second per Beacon, even if the data hasn't changed:

```python
from hub import port
import motor
import time

def on_data(values):
    speed = values[0]
    motor.run(port.A, speed)

s.listen(on_data)

# Your main loop continues — on_data fires in the background
while True:
    time.sleep_ms(100)
```

#### 2. `read(timeout)` — one-shot, blocking

Best for sequential programs where you just need one reading (safe to use while `listen()` is running):

```python
data = s.read(timeout=2000)      # wait up to 2 seconds
if data:
    print("Got:", data)
else:
    print("Nothing received")
```

#### 3. `wait_for(condition, timeout)` — block until a specific value

See [Waiting for a Condition](#waiting-for-a-condition--wait_for) for full details.

```python
result = s.wait_for(lambda v: v[0] < 50)   # wait until the first value is below 50
```

**Other Scanner methods:**

```python
s.read_all(timeout=2000)
# Scans for the full duration and returns data from ALL matching Beacons.
# Returns: dict mapping each Beacon's Bluetooth address → its latest values.
# e.g. {"2C:AB:33:5D:C2:BC": [42, 3.14], "2C:AB:33:5D:C3:01": [99]}
# len(result) is the number of hubs heard.

s.stop()            # stop the listen() callback
s.is_listening      # True while listen() is active (property)
```

---

## Direct Mode

A **Peripheral** acts as the BLE server — it advertises and waits for connections. A **Central** is the client — it scans, connects, and initiates communication. Once connected, both sides can send and receive messages. Messages arrive complete and in order; long messages are split into packets and rejoined automatically.

### Peripheral (server hub)

```python
from spikecomm import Peripheral
import time

p = Peripheral("HubA")    # give this hub a unique name
p.advertise()             # start accepting connections

def on_message(msg):
    print("Received:", msg)
    p.send("got it!")     # reply

p.listen(on_message)

while True:
    time.sleep_ms(50)     # keep running — callbacks fire in the background
```

**Constructor:**
```python
Peripheral(name="SPIKE", verbose=False)
```
- `name` — BLE device name shown during scanning. Should be unique. Max 26 chars. Create only one Peripheral per hub.

**Methods:**

```python
p.advertise(interval_ms=100)   # start advertising; call once at startup
p.stop_advertising()            # stop accepting new connections
p.disconnect()                  # disconnect the connected Central
p.send(message)                 # send a string to the Central → True/False
p.listen(callback)              # register callback(msg: str) for incoming messages
p.on_connect(callback)          # register callback(conn_handle) on new connection
p.on_disconnect(callback)       # register callback(conn_handle) on disconnect
p.wait_for(condition, timeout)  # block until a message meets the condition
p.is_connected                  # True if a Central is connected (property)
p.connection_count              # number of connected Centrals (property)
```

**Auto re-advertise:** After a Central disconnects, the Peripheral automatically advertises again so a new connection is always possible. Call `stop_advertising()` to disable this.

**Welcome messages:** the `on_connect` callback runs once the connection is fully set up, so it can `p.send()` a greeting (see Example 7).

### Central (client hub)

```python
from spikecomm import Central

c = Central("HubA")      # name (or partial name) of the Peripheral to find

def on_reply(msg):
    print("Reply:", msg)

c.listen(on_reply)        # can be set up before connecting

if c.connect():           # scan + connect + service discovery — all in one call
    print("Connected!")
    c.send("hello")
else:
    print("Could not find HubA")
```

**Constructor:**
```python
Central(target="SPIKE", verbose=False)
```
- `target` — name (or partial name) of the Peripheral to connect to. Partial matching works: `"Hub"` will match `"HubA"` or `"HubB"`.

**Methods:**

```python
c.connect(timeout=10000)        # scan, connect, discover services; returns True/False
                                # (retries by itself if an attempt fails, until the timeout)
c.disconnect()                  # disconnect (finishes sending queued messages first)
c.send(message)                 # send a string to the Peripheral → True/False
c.listen(callback)              # register callback(msg: str) for incoming messages
c.on_connect(callback)          # register callback() when fully connected
c.on_disconnect(callback)       # register callback() when the connection is lost
c.wait_for(condition, timeout)  # block until a message meets the condition
c.is_connected                  # True if connected and ready to send (property)
```

**Messages:** `send()` takes a string (numbers are converted to text automatically) of up to 1000 characters. Don't put a newline (`"\n"`) inside a message — it marks the end of a message, so the text would arrive as two messages. To send several values, use `encode()` (next section).

**Messages that arrive before `listen()`:** on both Peripheral and Central, up to 10 messages that arrive before you call `listen()` are kept and passed to your callback as soon as you register it — nothing sent right after connecting is lost.

---

## Encoding and Decoding Multiple Values

`encode` and `decode` pack multiple values into a single compact string — useful for sending structured data through either communication mode.

```python
from spikecomm import encode, decode

# Encode values into a string
encode(42)                   # → "42"
encode(42, 3.14)             # → "42;3.14"
encode(1, 2, 3)              # → "1;2;3"
encode("go", 42)             # → "go;42"
encode(True, 99, 1.5)        # → "1;99;1.5"   (booleans become 0/1)
encode(3.14159, precision=4) # → "3.1416"
encode(1, 2, sep=",")        # → "1,2"

# Decode back into a list — auto-detects int, float, or string per token
decode("42;3.14;ok")         # → [42, 3.14, "ok"]
decode("1,2,3", sep=",")     # → [1, 2, 3]
decode("")                   # → []
```

**Types can change on the way:** `True` arrives as `1`, a float like `2.0` arrives as the integer `2`, and a string that looks like a number (`"007"`) arrives as a number (`7`).

**Using encode/decode with Direct mode:**

```python
# Peripheral sends multiple sensor values as one message
p.send(encode(distance, speed, heading))

# Central receives and unpacks them
def on_data(msg):
    dist, spd, hdg = decode(msg)
    print("Distance:", dist, "Speed:", spd, "Heading:", hdg)
c.listen(on_data)
```

**Using encode/decode with Beacon mode:**

```python
# Beacon — encode is applied automatically inside broadcast()
b.broadcast(distance, speed, heading)   # → "!S140;75;270"

# Scanner — decode is applied automatically; values come ready to use
def on_data(values):
    dist, spd, hdg = values[0], values[1], values[2]
s.listen(on_data)
```

---

## Waiting for a Condition — `wait_for`

`wait_for` blocks your program until a specific value or condition is met — without writing a polling loop yourself. Available on `Scanner`, `Peripheral`, and `Central`.

```python
result = obj.wait_for(condition, timeout=None)
```

- `condition` — either a **value** (exact match on first element / full message) or a **function** that returns `True` when the condition is satisfied. If the function raises an error for some message (e.g. `int("hello")`), that message just counts as "no match".
- `timeout` — max wait in milliseconds. `None` = wait forever. Returns `None` on timeout.
- **Only sees new data:** `wait_for` checks messages that arrive *while it's waiting*, not ones that came earlier.
- **Coexists with `listen()`** — if a `listen()` callback is active, both fire for every incoming event.
- `Peripheral.wait_for` also waits for a Central to connect first. `Central.wait_for` returns `None` if the connection is (or gets) lost.

### Value form — exact match

```python
# Scanner: wait until first broadcast value equals 3
result = scanner.wait_for(3)

# Peripheral: wait until Central sends exactly "start"
msg = p.wait_for("start")
motor.run(port.A, 500)

# Central: wait until Peripheral sends exactly "green_light"
msg = c.wait_for("green_light")
```

### Function (predicate) form — custom condition

The predicate is a function that receives the values (for Scanner) or the message string (for Peripheral/Central) and should return `True` when the condition is met.

```python
# Scanner: wait until distance drops below 50 (first value)
result = scanner.wait_for(lambda v: v[0] < 50)
print("Close! Distance =", result[0])

# Scanner: wait until BOTH conditions are true
result = scanner.wait_for(lambda v: v[0] < 50 and v[1] > 80)

# Scanner: wait until the value is between 100 and 200
result = scanner.wait_for(lambda v: 100 <= v[0] <= 200)

# Central: wait for any message that is a large number (sent as string)
msg = c.wait_for(lambda m: int(m) > 100)

# Central: wait for a multi-value message where distance < 50
msg = c.wait_for(lambda m: decode(m)[0] < 50)
values = decode(msg)

# Peripheral: wait for either of three trigger words
msg = p.wait_for(lambda m: m in ("go", "start", "run"))
```

### Timeout — giving up gracefully

```python
result = scanner.wait_for(lambda v: v[0] < 50, timeout=5000)
if result is None:
    print("Nothing came within 50 in 5 seconds")
else:
    print("Got close! Distance:", result[0])

msg = c.wait_for("ready", timeout=10000)
if msg is None:
    print("Peripheral never said ready — is it running?")
```

---

## Callback Rules

Functions you pass to `listen()`, `on_connect()`, and `on_disconnect()` are **callbacks**: spikecomm runs them "in the background", in between the lines of your main loop.

- **Keep callbacks short.** Save the values into a variable or dictionary, start/stop a motor, or `send()` a reply. Do the heavier work in your main loop.
- **Never call blocking functions inside a callback** — `connect()`, `read()`, `read_all()`, `wait_for()`, or `time.sleep_ms()`. New Bluetooth events can't arrive while a callback is running, so these stall (and `wait_for` with no timeout would wait forever).
- **Keep the program alive.** Callbacks only run while your program is running, so finish with a loop such as `while True: time.sleep_ms(50)`.
- **Errors are printed, not fatal.** If your callback raises an error (e.g. `values[1]` when only one value arrived), spikecomm prints the error and keeps listening — read the console!
- **Sharing data with the main loop:** the easiest way is a dictionary, which a callback can change without `global`:

  ```python
  latest = {"distance": None}

  def on_data(values):
      latest["distance"] = values[0]

  s.listen(on_data)

  while True:
      if latest["distance"] is not None and latest["distance"] < 100:
          print("Something is close!")
      time.sleep_ms(50)
  ```

---

## Debugging with `verbose=True`

Pass `verbose=True` to any class to print a trace of everything happening. Particularly helpful when students aren't sure if their hubs are finding each other, or if messages are being sent/received as expected.

```python
b = Beacon("!S", verbose=True)
b.broadcast(42, 3.14)
# [spikecomm Beacon] Ready. Prefix='!S', interval=100ms
# [spikecomm Beacon] Broadcasting "!S42;3.14" (9 of 26 chars used)
```

```python
s = Scanner("!S", verbose=True)
s.listen(my_callback)
# [spikecomm Scanner] Ready. Looking for prefix='!S'
# [spikecomm Scanner] Listening for prefix "!S" ...
# [spikecomm Scanner] Received "!S42;3.14" → [42, 3.14]  RSSI=-62
```

```python
p = Peripheral("HubA", verbose=True)
p.advertise()
# [spikecomm Peripheral] Ready. Name='HubA'
# [spikecomm Peripheral] Advertising as "HubA" ...
# [spikecomm Peripheral] Central connected  (handle=1025, total connected=1)
# [spikecomm Peripheral] Received: "hello"
# [spikecomm Peripheral] Sent: "got it"  (to 1 device(s))
```

```python
c = Central("HubA", verbose=True)
c.connect()
# [spikecomm Central] Ready. Looking for target='HubA'
# [spikecomm Central] Scanning for "HubA" (up to 10000ms) ...
# [spikecomm Central] Found "HubA" (RSSI=-55) — connecting ...
# [spikecomm Central] Connected. Discovering services ...
# [spikecomm Central] Ready ✓ (TX handle=9, RX handle=12)
```

**RSSI** (signal strength) shown in Scanner and Central verbose output is useful for diagnosing range issues — values around -50 to -70 are healthy; -90 or below is weak.

Turn verbose off in finished programs to keep console output clean.

---

## Complete Examples

The examples use the SPIKE App 3 hub API: `from hub import port` plus the `motor`, `distance_sensor`, `force_sensor`, and `color_sensor` modules. Change the ports to match how your robot is built. Units: motor speeds you set are degrees per second (but `motor.velocity()` reads back in other units, see [Limitations and Tips](#limitations-and-tips)), distances are millimetres (`-1` = nothing detected), force is 0–100.

### Example 1 — One hub broadcasts, another listens (non-blocking)

**Hub A — sensor broadcaster:**

```python
# Hub A: reads a distance sensor and continuously broadcasts it
from spikecomm import Beacon
from hub import port
import distance_sensor
import time

b = Beacon("!S")

while True:
    distance = distance_sensor.distance(port.A)   # mm, -1 if nothing detected
    b.broadcast(distance)
    time.sleep_ms(100)
```

**Hub B — motor controller reacting to live distance:**

```python
# Hub B: drives a motor faster when Hub A's sensor sees something closer
from spikecomm import Scanner
from hub import port
import motor
import time

s = Scanner("!S")

def on_reading(values):
    distance = values[0]
    if distance == -1 or distance > 1000:
        motor.stop(port.A)          # nothing close: stop
    elif distance < 300:
        motor.run(port.A, 800)      # fast when close
    else:
        motor.run(port.A, 300)      # slow when medium

s.listen(on_reading)

while True:
    time.sleep_ms(50)
```

---

### Example 2 — Collect readings from multiple hubs

Three hubs each broadcast a force-sensor reading. A fourth hub collects all of them.

**Hubs A, B, C — each a force sensor:**

```python
# Hub A  (on Hub B use "!B", on Hub C use "!C")
from spikecomm import Beacon
from hub import port
import force_sensor
import time

b = Beacon("!A")
while True:
    b.broadcast(force_sensor.force(port.A))   # 0–100
    time.sleep_ms(200)
```

**Hub D — collector:**

```python
# Hub D: listen to all three beacons and print a combined report
from spikecomm import Scanner
import time

latest = {}              # "A"/"B"/"C" -> latest force reading

def on_a(values):
    latest["A"] = values[0]

def on_b(values):
    latest["B"] = values[0]

def on_c(values):
    latest["C"] = values[0]

scanner_a = Scanner("!A")
scanner_b = Scanner("!B")
scanner_c = Scanner("!C")
scanner_a.listen(on_a)
scanner_b.listen(on_b)
scanner_c.listen(on_c)

while True:
    print("Forces:", latest)
    if len(latest) == 3:
        print("Average:", round(sum(latest.values()) / 3, 1))
    time.sleep_ms(1000)
```

(A sequential program can instead call `scanner_a.read(timeout=1000)`, `scanner_b.read(...)`, … one after another.)

---

### Example 3 — Wait for a trigger value before acting

Hub B drives a motor only after Hub A's distance sensor detects someone nearby.

**Hub A — proximity beacon:**

```python
from spikecomm import Beacon
from hub import port
import distance_sensor
import time

b = Beacon("!S")

while True:
    b.broadcast(distance_sensor.distance(port.A))
    time.sleep_ms(100)
```

**Hub B — waits for trigger, then acts:**

```python
from spikecomm import Scanner
from hub import port
import motor
import time

s = Scanner("!S")

print("Waiting for someone to come within 40 cm...")
result = s.wait_for(lambda v: 0 <= v[0] < 400, timeout=30000)   # -1 = nothing seen

if result:
    print("Detected at", result[0], "mm! Running motor.")
    motor.run(port.A, 500)
    time.sleep_ms(2000)
    motor.stop(port.A)
else:
    print("Nobody came close within 30 seconds.")
```

---

### Example 4 — Direct two-way connection: remote control

Hub B (controller) is tilted like a joystick and sends motor speeds to Hub A (robot). Hub A sends back its actual speeds (as `motor.velocity()` reports them: roughly percent of full speed, not degrees per second).

**Hub A — robot (Peripheral):**

```python
from spikecomm import Peripheral, encode, decode
from hub import port
import motor
import time

p = Peripheral("Robot1")
p.advertise()

def on_command(msg):
    left_speed, right_speed = decode(msg)        # e.g. "300;-200" -> [300, -200]
    motor.run(port.A, left_speed)
    motor.run(port.B, right_speed)
    p.send(encode(motor.velocity(port.A), motor.velocity(port.B)))   # feedback

def on_disconnect(handle):
    motor.stop(port.A)                           # safety: stop if the controller leaves
    motor.stop(port.B)

p.listen(on_command)
p.on_disconnect(on_disconnect)
print("Robot ready, waiting for controller...")

while True:
    time.sleep_ms(20)
```

**Hub B — controller (Central):**

```python
from spikecomm import Central, encode
from hub import motion_sensor
import time

c = Central("Robot1")
c.listen(lambda msg: print("Robot speed:", msg))

while True:
    if not c.is_connected:                       # (re)connect from the main loop
        print("Connecting to robot...")
        if not c.connect(timeout=5000):
            continue
        print("Connected!")

    yaw, pitch, roll = motion_sensor.tilt_angles()   # tenths of a degree
    speed = pitch * 2                            # tilt forward/back to drive
    turn = roll * 2                              # tilt left/right to turn
    c.send(encode(speed + turn, speed - turn))   # (flip signs to suit how you hold it)
    time.sleep_ms(50)                            # 20 commands per second
```

---

### Example 5 — Wait for a handshake before starting

Both hubs wait for each other to be ready before the experiment begins.

**Hub A — Peripheral that waits for "ready" signal:**

```python
from spikecomm import Peripheral
import time

p = Peripheral("HubA")
p.advertise()
print("Hub A: waiting for Hub B to connect and say ready...")

# Blocks until a Central connects AND sends "ready" (or 30 s pass)
msg = p.wait_for("ready", timeout=30000)

if msg:
    print("Hub A: Hub B is ready! Starting experiment.")
    p.send("go")
    # ... experiment code here (keep the program running) ...
    time.sleep_ms(5000)
else:
    print("Hub A: Hub B never responded. Check connection.")
```

**Hub B — Central that signals when ready:**

```python
from spikecomm import Central

c = Central("HubA")
print("Hub B: connecting to Hub A...")

if not c.connect(timeout=15000):
    print("Could not find Hub A")
    raise SystemExit

print("Hub B: connected! Signaling ready...")
c.send("ready")

# Now wait for Hub A to say "go"
msg = c.wait_for("go", timeout=10000)
if msg:
    print("Hub B: received go! Starting.")
    # ... experiment code here ...
else:
    print("Hub B: never received go from Hub A.")
```

---

### Example 6 — Broadcast multiple sensor values simultaneously

One hub broadcasts color, distance, and force readings as a single packet.

**Sender hub:**

```python
from spikecomm import Beacon
from hub import port
import color_sensor, distance_sensor, force_sensor
import time

b = Beacon("!S")

while True:
    color    = color_sensor.color(port.A)          # color number, -1 if none
    distance = distance_sensor.distance(port.B)    # mm, -1 if nothing detected
    force    = force_sensor.force(port.C)          # 0–100

    # All three values encoded together: e.g., "!S9;142;24"
    b.broadcast(color, distance, force)
    time.sleep_ms(100)
```

**Receiver hub:**

```python
from spikecomm import Scanner
import time

s = Scanner("!S")

def on_data(values):
    color, distance, force = values[0], values[1], values[2]
    print("Color: {}  Distance: {} mm  Force: {}".format(color, distance, force))

s.listen(on_data)

while True:
    time.sleep_ms(50)
```

---

### Example 7 — Peripheral with connect/disconnect lifecycle

```python
from spikecomm import Peripheral
import time

p = Peripheral("DataHub", verbose=True)
p.advertise()

def on_connect(handle):
    print("Central connected — sending welcome message")
    p.send("hello from DataHub")

def on_disconnect(handle):
    print("Central left — waiting for next connection")

def on_message(msg):
    if msg == "ping":
        p.send("pong")
    elif msg == "status":
        p.send("running")
    else:
        p.send("unknown command: " + msg)

p.on_connect(on_connect)
p.on_disconnect(on_disconnect)
p.listen(on_message)

while True:
    time.sleep_ms(100)
```

---

### Example 8 — Two hubs broadcast to each other

Each hub is a Beacon *and* a Scanner. Press the left button on one hub and the other hub shows a smiley.

```python
# Hub A  (on Hub B, swap "!A" and "!B")
from spikecomm import Beacon, Scanner
from hub import button, light_matrix
import time

me = Beacon("!A")
other = Scanner("!B")
state = {"other_pressed": 0}

def on_other(values):
    state["other_pressed"] = values[0]

other.listen(on_other)

while True:
    me.broadcast(1 if button.pressed(button.LEFT) else 0)
    if state["other_pressed"]:
        light_matrix.show_image(light_matrix.IMAGE_HAPPY)
    else:
        light_matrix.clear()
    time.sleep_ms(100)
```

---

### More examples

The `examples/` folder has complete Hub A / Hub B program pairs, tested on real hubs. Each hub shows on its screen what it is doing, so you can see the link working.

| Files | What it does |
|---|---|
| `tilt_arrow_hubA.py`, `tilt_arrow_hubB.py` | Tilt Hub A; Hub B's screen shows an arrow pointing the way Hub A leans. No sensors or motors needed. |
| `distance_spin_hubA.py`, `distance_spin_hubB.py` | Hub A broadcasts its distance-sensor reading (sensor on port A). When something comes closer than 50 cm, Hub B spins its motor (port A) 3 times, then waits for the object to move away before it can go again. Both screens show the distance as a bar; Hub B shows a turning arrow while it spins, a check mark when done, and an X if it loses Hub A. |
| `web_drive/simple.py` + `simple.html`, `web_drive/main.py` + `index.html` | A hub and a web page talking to each other; see [Talking to a Web Page](#talking-to-a-web-page). |

---

## Talking to a Web Page

A hub running a `Peripheral` can also talk to a **web page**, using the Web Bluetooth built into Chrome and Edge. The page plays the part of the `Central`: it connects to the hub, sends messages that arrive in the hub's `listen()` callback, and receives whatever the hub `send()`s. The hub program is ordinary Direct-mode code, started from the REPL as usual.

- **Browsers:** Chrome or Edge on a computer, Chromebook, or Android phone or tablet. Safari, Firefox, and browsers on iPhone/iPad don't have Web Bluetooth.
- **Opening the page:** double-clicking the `.html` file works in Chrome. A page on a website must use `https://` (or `http://localhost`).
- **Direct mode only:** a browser can't broadcast, so a page can't be a `Beacon`, and listening for Beacons isn't available in normal browsers.
- **Speed:** with Chrome on a Mac, a message plus the hub's reply took about 40–65 ms.

### Try it

The `examples/web_drive/` folder has two hub + page pairs, tested on a real hub with Chrome:

| Files | What it does |
|---|---|
| `simple.py` + `simple.html` | The smallest example. Type a message in the page; the hub prints it, replies, and smiles when the message is `smile`. Press the hub's left button and the page shows it. |
| `main.py` + `index.html` | Drive a car (motors on ports A and B) with W A S D or the arrow keys and Space to stop, with a speed slider (200 °/s to start), stopping when you let go of the key (can be turned off), and a message log. The hub stops the motors if the page disconnects. |

1. Start the hub program from the REPL, e.g. `mpremote run simple.py`. You can then unplug the USB cable.
2. Open `simple.html` in Chrome or Edge and click **Connect**. Pick your hub in the list.
3. Type a message and press **Send**.

### Writing your own page

spikecomm's `Peripheral` is a standard Bluetooth *Nordic UART Service*. A page needs:

| | |
|---|---|
| Service | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` |
| Page → hub | write to characteristic `6e400002-b5a3-f393-e0a9-e50e24dcca9e` |
| Hub → page | notifications from characteristic `6e400003-b5a3-f393-e0a9-e50e24dcca9e` |
| Messages | UTF-8 text, each ending with `"\n"` |

and three rules:

- **Write at most 20 bytes at a time.** Split longer messages; the hub joins the pieces up to the `"\n"`.
- **One write at a time.** Starting a write before the last one has finished fails with `NetworkError: GATT operation already in progress`, so queue them.
- **Collect what arrives until a `"\n"`.** A long message from the hub can come in several pieces.

This is the JavaScript from `simple.html`, which does all of that:

```js
const SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e";
const TO_HUB  = "6e400002-b5a3-f393-e0a9-e50e24dcca9e";   // write here: the hub's listen() callback gets it
const TO_PAGE = "6e400003-b5a3-f393-e0a9-e50e24dcca9e";   // the hub's send() arrives here

let toHub = null;    // set once connected

function show(text) {
  console.log(text);
  document.getElementById("output").textContent += text + "\n";
}

// Runs once for each message from the hub: react to it here
function onMessage(text) {
  show("Hub: " + text);
}

async function connect() {
  const device = await navigator.bluetooth.requestDevice({ filters: [{ services: [SERVICE] }] });
  device.addEventListener("gattserverdisconnected", () => { toHub = null; show("Disconnected"); });
  const server = await device.gatt.connect();
  const service = await server.getPrimaryService(SERVICE);
  const toPage = await service.getCharacteristic(TO_PAGE);
  toPage.addEventListener("characteristicvaluechanged", onData);
  await toPage.startNotifications();
  toHub = await service.getCharacteristic(TO_HUB);
  show("Connected to " + device.name);
}

// Every message ends with "\n". A long one can arrive in pieces,
// so collect text until a "\n" comes.
const decoder = new TextDecoder();
let partial = "";
function onData(event) {
  partial += decoder.decode(event.target.value, { stream: true });
  const lines = partial.split("\n");
  partial = lines.pop();     // an unfinished message waits for its next piece
  for (const line of lines) onMessage(line);
}

// Send text plus "\n" in writes of at most 20 bytes. The browser allows only
// one write at a time, so each send waits for the one before it.
let queue = Promise.resolve();
function send(text) {
  queue = queue.then(async () => {
    if (!toHub) return show("Not connected");
    show("Me: " + text);
    const bytes = new TextEncoder().encode(text + "\n");
    for (let i = 0; i < bytes.length; i += 20) {
      await toHub.writeValueWithResponse(bytes.slice(i, i + 20));
    }
  }).catch((e) => show("Error: " + e.message));
}
```

`requestDevice()` opens the browser's list of hubs, so call it from a button click (`connect` above is wired to the Connect button), not when the page loads. Filtering by `services` lists every hub running a spikecomm `Peripheral`. The list shows each hub by the name its `Peripheral` advertises, or, once the computer has connected to that hub before, possibly by the hub's own name (the one it has in the SPIKE App). So don't depend on the `Peripheral` name to find a hub. To narrow the list by name anyway, add it to the same filter: `{ filters: [{ services: [SERVICE], namePrefix: "Car" }] }`.

To send several values, use the same `"forward;500"` style as `encode()` and split it on the hub with `decode(msg)`.

Other programs that speak the Nordic UART Service, such as the `bleak` library for Python on a computer, can connect the same way, but only Chrome has been tested.

---

## API Quick Reference

### `Beacon`

```python
Beacon(prefix="!S", interval_ms=100, verbose=False)

b.broadcast(*values, sep=";", precision=2)   # start or update advertisement
b.stop()                                      # stop advertising
b.is_broadcasting                             # property: bool
```

### `Scanner`

```python
Scanner(prefix="!S", verbose=False)

s.listen(callback)                            # callback(values: list) — non-blocking
s.read(timeout=2000)                          # → list | None — blocking one-shot
s.read_all(timeout=2000)                      # → dict {address: values} — all beacons
s.wait_for(condition, timeout=None)           # → list | None — block until match
s.stop()                                      # stop listen()
s.is_listening                                # property: bool
```

### `Peripheral`

```python
Peripheral(name="SPIKE", verbose=False)

p.advertise(interval_ms=100)                  # start accepting connections
p.stop_advertising()                          # stop accepting new connections
p.send(message)                               # → bool — send string to the Central
p.listen(callback)                            # callback(msg: str) on receive
p.on_connect(callback)                        # callback(conn_handle: int)
p.on_disconnect(callback)                     # callback(conn_handle: int)
p.wait_for(condition, timeout=None)           # → str | None — block until match
p.disconnect()                                # disconnect the Central
p.is_connected                                # property: bool
p.connection_count                            # property: int
```

### `Central`

```python
Central(target="SPIKE", verbose=False)

c.connect(timeout=10000)                      # scan+connect+discover → bool
c.disconnect()                                # disconnect
c.send(message)                               # → bool — send string to Peripheral
c.listen(callback)                            # callback(msg: str) on receive
c.on_connect(callback)                        # callback() — no args
c.on_disconnect(callback)                     # callback() — no args
c.wait_for(condition, timeout=None)           # → str | None — block until match
c.is_connected                                # property: bool
```

### `encode` / `decode`

```python
encode(*values, sep=";", precision=2)         # → str
decode(data, sep=";")                         # → list
```

---

## Limitations and Tips

**BLE advertising name length (Beacon mode)**
The full advertised name — prefix plus encoded values — must fit within 26 characters. With a 2-character prefix, that leaves 24 characters for data. Integers and short floats are most compact. `broadcast()` raises a `ValueError` with a clear message if the limit is exceeded.

**Beacon mode is "latest value", not "every value"**
A Scanner hears each Beacon about 10 times per second. If a Beacon changes its value faster than that, some in-between values are never seen. When every message matters, use Direct mode.

**One advertisement per hub**
A hub can run a `Beacon` *or* a `Peripheral` (both advertise), but not both. A `Beacon` plus any number of `Scanner`s on one hub is fine.

**One Central per Peripheral**
A Peripheral talks to one Central at a time; when it disconnects, the Peripheral advertises again so another Central can connect. A web page counts as a Central. For groups of three or more hubs, Beacon mode is usually simpler.

**Message size and speed (Direct mode)**
Messages can be up to 1000 characters. Over the air they travel in 20-character packets, so short messages are fastest. In testing, a Central sent 100 short messages back-to-back in about a quarter of a second, all arriving in order — so sending a short message every 20–50 ms is fine. If you send faster than the radio can keep up, `send()` waits a moment for it. Messages sent from *inside a callback* are queued and go out more slowly (about 15 per second); if that queue fills up, `send()` drops the message, prints a warning, and returns `False`.

**`wait_for` coexists with `listen()`**
If you set up a `listen()` callback and later call `wait_for()`, both run simultaneously. The `listen()` callback continues to fire for every event; `wait_for` simply adds a temporary check on top and removes it when the condition is met.

**`wait_for` returns `None` on timeout**
Always check the return value if you passed a timeout:
```python
result = scanner.wait_for(lambda v: v[0] < 50, timeout=5000)
if result is None:
    print("timed out")   # handle timeout
```

**Partial name matching in `Central`**
`Central("Hub")` will connect to the first Peripheral whose name *contains* `"Hub"` — useful for flexibility, but make sure hub names are distinct enough to avoid ambiguity. (Centrals ignore Beacons, so a Beacon named `"!Hub5"` won't be picked by mistake.)

**Reconnection after disconnect**
`Peripheral` automatically re-advertises after a disconnect. `Central` does not auto-reconnect — check `c.is_connected` in your main loop and call `c.connect()` again (see Example 4). Don't call `connect()` inside the `on_disconnect` callback; it can't work from there (see [Callback Rules](#callback-rules)).

**Start order**
Start the Peripheral hub first, or give `connect()` a timeout long enough for the other hub to start (`connect(timeout=15000)`).

**`encode` / `decode` separator**
The default separator `;` works well for most numbers. If your data contains semicolons (e.g. text strings), choose a different separator: `encode(..., sep="|")` and `decode(..., sep="|")`. Both sides must use the same separator.

**Don't use the `bluetooth` module directly alongside spikecomm**
spikecomm manages the hub's single Bluetooth radio. Some low-level `bluetooth` calls can freeze or switch off a hub on this firmware, so stick to the spikecomm functions.

**`async` / `runloop` programs**
spikecomm also works in programs written with `async def main()` and `runloop.run(main())`: callbacks fire while your code is in `await runloop.sleep_ms(...)`. The blocking calls (`connect()`, `read()`, `read_all()`, `wait_for()`) work too, but they pause your other tasks while they wait.

**Motors and the light matrix in `while True` programs**
`motor.run_for_degrees()`, `motor.run_for_time()` and `light_matrix.write()` don't need `await` in a normal `while True` program: they start, return at once, and finish on their own, so your loop and callbacks keep running. To know when a motor move is done, watch `motor.relative_position()`; `motor.status()` reports wrong values on this firmware. `run_for_degrees` stops exactly on target, while `motor.run()` followed by `motor.stop()` coasts on a little (about 70° at 720 °/s). `motor.velocity()` is not in degrees per second: a medium motor running at 720 °/s reads about 65. See `examples/distance_spin_hubB.py`.

**Memory**
`import spikecomm` takes about 0.7 s and keeps about 18 KB of the hub's ~210 KB of program memory. While it is being loaded it briefly needs about 100 KB free, so import it at the top of your program, before creating large lists or strings.

**Programs started by the hub can't use Bluetooth**
The SPIKE App's Run button and the hub's program menu don't work with spikecomm (see [Running spikecomm programs](#running-spikecomm-programs)). Putting the program in `main.py` doesn't help either: with the SPIKE App firmware the hub doesn't run `main.py` at power-on.

**Not yet tested**
- Two Centrals or two Peripherals on the same hub.
- Web pages in Edge, or on Windows, Chromebooks or Android (tested: Chrome on macOS); other Nordic UART programs such as Python's `bleak`.

**Debugging workflow**
Start with `verbose=True` on all objects, confirm the correct data is being sent and received, then set `verbose=False` before running the final program.

---

*spikecomm v1.2.0 — Tufts CEEO*
