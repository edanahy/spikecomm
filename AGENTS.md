# AGENTS.md — writing hub-to-hub (and web-page-to-hub) code with `spikecomm`

You are helping a student write MicroPython programs for **LEGO SPIKE Prime hubs** that talk to each other (or to a web page) over Bluetooth using the `spikecomm` library (v1.2.0). The student has already copied `spikecomm.py` onto each hub. Read this whole file before writing code.

## Environment

- Hardware: LEGO SPIKE Prime hubs, **SPIKE App 3 firmware** (MicroPython).
- **How programs must be started:** from the hub's REPL over USB (paste mode: Ctrl-C, Ctrl-E, paste, Ctrl-D; or `exec(open("/flash/program/00/program.py").read())` for a program saved in slot 0; or `mpremote run program.py`). The SPIKE App's Run button and the hub's program menu do **not** work — the firmware blocks Bluetooth for programs it starts, and spikecomm raises `ImportError: spikecomm can't use Bluetooth in a program started from a program slot...`. After starting, the USB cable can be unplugged and the program keeps running. Tell the student this when you give them code.
- Import the library with `from spikecomm import ...`. Do **not** paste the library into the program, and do not use `pip`, `asyncio` servers, Wi-Fi, sockets, threads, or `import bluetooth` — none of those are how this works. (This is about hub programs. A web page that talks to a hub is plain HTML + JavaScript using Web Bluetooth: see "Web pages" below.)
- **Each hub runs its own program.** When a project uses several hubs, write one separate, complete program per hub and label each clearly (e.g. `# ===== Hub A (robot) =====`). Make sure names/prefixes match between them.
- Use the SPIKE App 3 hub API (see the cheat sheet at the end). Do not use SPIKE 2 / Robot Inventor APIs (`from spike import PrimeHub`, `Motor('A')`, `motor.run_at_speed`, `get_distance_cm`), Pybricks APIs, or EV3 APIs.

## Pick the mode

| Need | Use |
|---|---|
| Share sensor values / status; 3 or more hubs; each hub both sends and receives | **Beacon + Scanner** (broadcast, no connection) |
| Exactly two hubs; every message must arrive (commands, text, handshakes) | **Peripheral + Central** (connection) |
| A web page (Chrome or Edge) talks to a hub | **Peripheral** on the hub; the page connects with Web Bluetooth (see "Web pages"). A page can't use Beacon + Scanner. |

If unsure between hubs, prefer Beacon + Scanner: it has fewer ways to fail.

## Hard rules (follow these in every program)

1. **Create spikecomm objects once, at the top level** of the program — never inside a loop or a callback.
2. **Keep the program alive** with a main loop, e.g. `while True: ... time.sleep_ms(50)`. Callbacks only fire while the program runs. Always `import time`.
3. **Callbacks must be short and non-blocking.** Inside a callback, never call `connect()`, `read()`, `read_all()`, `wait_for()`, or `time.sleep_ms()` (events can't arrive while a callback runs, so these stall). Do the work in the main loop.
4. **Share data from callbacks through a dictionary** (`latest["x"] = values[0]`), which avoids `global` mistakes. Initialize it before the loop and handle the "nothing received yet" case.
5. **Check lengths before indexing** received data if the sender might send a different number of values. An error inside a callback is printed and the callback keeps being called, but that reading is lost.
6. **Beacon names are tiny:** prefix + encoded data ≤ **26 characters**. Use a 2–3 character prefix (`"!A"`, `"!B"`). Send integers (round floats, e.g. `round(x)` or `round(x, 1)`). One prefix must never be the start of another (`"!S"` and `"!S1"` clash).
7. **One advertiser per hub:** a hub can have a `Beacon` *or* a `Peripheral`, not both. A `Beacon` plus any number of `Scanner`s is fine. Only one `Peripheral` per hub.
8. **Direct-mode messages are strings** (numbers are auto-converted to text), up to 1000 characters, and must not contain `"\n"`. Use `encode(...)` / `decode(msg)` for several values.
9. **`wait_for` only sees new data** — anything that arrived before the call is not checked. Always pass a `timeout` and handle `None`.
10. **Reconnect from the main loop:** check `c.is_connected` and call `c.connect(timeout=...)` again. Never call `connect()` inside `on_disconnect`.
11. Start the **Peripheral first**, or give `Central.connect()` a long timeout (e.g. 15000 ms).
12. Plain `while True` + `time.sleep_ms()` programs are simplest. `async def main()` + `runloop.run(main())` programs also work: callbacks fire during `await runloop.sleep_ms(...)`, but the blocking calls (`connect`, `read`, `read_all`, `wait_for`) pause every other task while they wait. Don't mix in `time.sleep_ms()` inside async code; use `await runloop.sleep_ms()`.

## API reference

```python
from spikecomm import Beacon, Scanner, Peripheral, Central, encode, decode

# ── Beacon: broadcast values (no connection) ────────────────────────────────
b = Beacon(prefix="!S", interval_ms=100, verbose=False)
b.broadcast(*values, sep=";", precision=2)   # advertise prefix+encoded values; ValueError if > 26 chars
                                             # repeating identical data is free; call it every loop
b.stop()
b.is_broadcasting                            # bool

# ── Scanner: receive broadcasts with a matching prefix ──────────────────────
s = Scanner(prefix="!S", verbose=False)      # several Scanners per hub are fine
s.listen(callback)          # callback(values: list); ~10 calls/second per Beacon; non-blocking
s.stop()                    # stop listen()
s.read(timeout=2000)        # -> list | None   (blocking; first matching Beacon)
s.read_all(timeout=2000)    # -> {address_str: list}  (blocking for the whole timeout; one entry per hub)
s.wait_for(condition, timeout=None)  # -> list | None; condition = value (matches values[0]) or function(values)
s.is_listening              # bool

# ── Peripheral: server; waits for one Central ────────────────────────────────
p = Peripheral(name="SPIKE", verbose=False)  # name ≤ 26 chars, unique
p.advertise(interval_ms=100)                 # call once; re-advertises automatically after a disconnect
p.listen(callback)          # callback(msg: str); up to 10 earlier messages are delivered on registering
p.send(message)             # -> bool (False if no Central connected)
p.wait_for(condition, timeout=None)  # -> str | None; also waits for a Central to connect
p.on_connect(callback)      # callback(conn_handle); runs after setup, so p.send("welcome") here works
p.on_disconnect(callback)   # callback(conn_handle)
p.disconnect()
p.stop_advertising()
p.is_connected              # bool
p.connection_count          # int

# ── Central: client; finds a Peripheral by (partial) name ────────────────────
c = Central(target="SPIKE", verbose=False)   # "Robot" matches "Robot1"; Beacons are ignored
c.listen(callback)          # callback(msg: str); register before or after connect; survives reconnects
                            # (up to 10 messages that arrived earlier are delivered on registering)
c.connect(timeout=10000)    # -> bool (blocking: scan + connect + discover; retries itself until timeout)
c.send(message)             # -> bool (False if not connected)
c.wait_for(condition, timeout=None)  # -> str | None; returns None at once if not connected / on link loss
c.on_connect(callback)      # callback()
c.on_disconnect(callback)   # callback() — only for unexpected loss, not for c.disconnect()
c.disconnect()              # sends anything still queued first
c.is_connected              # bool

# ── Helpers ──────────────────────────────────────────────────────────────────
encode(42, 3.14159, True)   # -> "42;3.14;1"
decode("42;3.14;ok")        # -> [42, 3.14, "ok"]
```

`decode` auto-types each token: `True` arrives as `1`, `2.0` arrives as `2`, and numeric-looking strings become numbers.

`verbose=True` on any object prints a trace (`[spikecomm Scanner] Received "!S42" → [42]  RSSI=-60`). Suggest it whenever the student is debugging.

## Templates

Adapt these; keep their structure. Fuller pairs, tested on real hubs, are in the `examples/` folder if the student has it: `tilt_arrow_hubA.py` / `tilt_arrow_hubB.py` (Hub B's screen shows an arrow for the way Hub A is tilted) and `distance_spin_hubA.py` / `distance_spin_hubB.py` (Template 6 with light-matrix status indicators and signal-loss handling). Hub + web page pairs are in `examples/web_drive/` (see "Web pages").

### 1. Share a sensor value (Beacon → Scanner)

```python
# ===== Hub A (sender) =====
from spikecomm import Beacon
from hub import port
import distance_sensor
import time

b = Beacon("!A")
while True:
    b.broadcast(distance_sensor.distance(port.A))   # mm, -1 if nothing detected
    time.sleep_ms(100)
```

```python
# ===== Hub B (receiver) =====
from spikecomm import Scanner
from hub import port
import motor
import time

latest = {"dist": None}

def on_data(values):
    if values:
        latest["dist"] = values[0]

s = Scanner("!A")
s.listen(on_data)

while True:
    d = latest["dist"]
    if d is None or d == -1:
        motor.stop(port.A)
    elif d < 200:
        motor.run(port.A, 600)
    else:
        motor.stop(port.A)
    time.sleep_ms(50)
```

### 2. Every hub broadcasts and listens (groups of 2+ hubs)

Give each hub its own prefix; each hub scans the others.

```python
# ===== Hub A ===== (Hub B: MY = "!B", OTHERS = ["!A", "!C"]; Hub C likewise)
from spikecomm import Beacon, Scanner
from hub import button
import time

MY = "!A"
OTHERS = ["!B", "!C"]

me = Beacon(MY)
latest = {}                      # prefix -> latest values list

def make_handler(prefix):
    def handler(values):
        latest[prefix] = values
    return handler

scanners = []
for prefix in OTHERS:
    s = Scanner(prefix)
    s.listen(make_handler(prefix))
    scanners.append(s)

while True:
    me.broadcast(1 if button.pressed(button.LEFT) else 0)
    pressed = [p for p, v in latest.items() if v and v[0] == 1]
    print("Hubs pressing:", pressed)
    time.sleep_ms(100)
```

Alternative for many identical hubs: all use the same prefix and put an ID first — `b.broadcast(MY_ID, value)` — and the collector uses one `Scanner` whose callback stores `latest[values[0]] = values[1:]`.

### 3. Remote control (Central sends commands, Peripheral obeys)

```python
# ===== Hub A (robot, Peripheral) =====
from spikecomm import Peripheral, decode
from hub import port
import motor
import time

p = Peripheral("Robot1")
p.advertise()

def on_command(msg):
    values = decode(msg)
    if len(values) == 2:
        motor.run(port.A, values[0])
        motor.run(port.B, values[1])

def on_lost(handle):
    motor.stop(port.A)
    motor.stop(port.B)

p.listen(on_command)
p.on_disconnect(on_lost)

while True:
    time.sleep_ms(20)
```

```python
# ===== Hub B (controller, Central) =====
from spikecomm import Central, encode
from hub import motion_sensor
import time

c = Central("Robot1")

while True:
    if not c.is_connected:
        print("Connecting...")
        if not c.connect(timeout=5000):
            continue
        print("Connected")
    yaw, pitch, roll = motion_sensor.tilt_angles()   # tenths of a degree
    speed, turn = pitch * 2, roll * 2
    c.send(encode(speed + turn, speed - turn))
    time.sleep_ms(50)
```

### 4. Request / reply

```python
# Peripheral side: answer inside the callback (send() is fine in callbacks)
def on_message(msg):
    if msg == "distance?":
        p.send(distance_sensor.distance(port.A))
p.listen(on_message)
```

```python
# Central side: ask, then wait for the answer (in the main loop, not a callback)
c.send("distance?")
reply = c.wait_for(lambda m: True, timeout=2000)     # next message
if reply is not None:
    print("Distance:", int(reply))
```

### 5. Start signal / handshake

```python
# Peripheral: blocks until a Central connects and sends "ready"
msg = p.wait_for("ready", timeout=30000)
if msg:
    p.send("go")
```

```python
# Central
if c.connect(timeout=15000):
    c.send("ready")
    if c.wait_for("go", timeout=10000):
        print("Starting!")
```

### 6. Do something once when a value crosses a threshold

Hub A is Template 1's sender (distance in mm, prefix `"!A"`). Hub B spins a motor 3 times when something comes closer than 50 cm, then waits for it to move away before it can go again. The action runs from the main loop as a small state machine, never inside the callback.

```python
# ===== Hub B (receiver) =====
from spikecomm import Scanner
from hub import port
import motor
import time

latest = {"mm": None}

def on_data(values):
    if values:
        latest["mm"] = values[0]

s = Scanner("!A")
s.listen(on_data)

state = "watching"          # "watching" -> "spinning" -> "done" -> "watching"
start = 0
while True:
    d = latest["mm"]
    close = d is not None and 0 <= d < 500        # -1 = nothing detected
    if state == "watching" and close:
        start = motor.relative_position(port.A)
        motor.run_for_degrees(port.A, 3 * 360, 720)   # starts and returns at once
        state = "spinning"
    elif state == "spinning":
        if abs(motor.relative_position(port.A) - start) >= 3 * 360 - 5:
            state = "done"                             # the motor stopped itself
    elif state == "done" and not close:
        state = "watching"                             # re-arm once the object leaves
    time.sleep_ms(20)
```

## Web pages (Web Bluetooth)

A web page in **Chrome or Edge** (on a computer, Chromebook or Android; not Safari, Firefox, or any browser on iPhone/iPad) can talk to a hub that runs a `Peripheral`: the page plays the Central. The hub program is ordinary spikecomm code, started from the REPL as usual. The page is one `.html` file with plain JavaScript: no libraries, no build step, no server. Give the student both, labeled `# ===== Hub =====` and `<!-- ===== Web page ===== -->`, and tell them to open the page in Chrome or Edge and click Connect. Tested on a real hub with Chrome. Complete examples in `examples/web_drive/`: `simple.py` + `simple.html` (Template 7) and `main.py` + `index.html` (drive a car with W A S D, Space to stop, a speed slider, motors stop if the page disconnects).

Rules for the page:

1. **Direct mode only.** The hub uses `Peripheral`. A browser can't advertise or (normally) scan, so never use `Beacon` or `Scanner` with a web page.
2. **The protocol** (spikecomm's `Peripheral` is a Nordic UART Service): service `6e400001-b5a3-f393-e0a9-e50e24dcca9e`. The page **writes** to characteristic `6e400002-b5a3-f393-e0a9-e50e24dcca9e` (it arrives in the hub's `listen()` callback) and gets **notifications** from `6e400003-b5a3-f393-e0a9-e50e24dcca9e` (whatever the hub `send()`s). Every message is UTF-8 text ending in `"\n"`.
3. **At most 20 bytes per write.** Encode `text + "\n"` and write it in 20-byte slices; the hub joins them up to the `"\n"`.
4. **One write at a time.** Starting a write before the previous one finished fails with `NetworkError: GATT operation already in progress`. Chain sends on a promise queue as in Template 7. When keys drive the hub, send only when the command changes (skip `keydown` events with `event.repeat`).
5. **Collect notifications until a `"\n"`:** decode with one `TextDecoder` using `{ stream: true }`, split on `"\n"`, and keep the last, unfinished piece for next time.
6. **Call `navigator.bluetooth.requestDevice()` from a click handler**, never when the page loads. Filter with `{ services: [SERVICE] }` (lists every spikecomm `Peripheral` nearby). Don't rely on the `Peripheral` name: once a computer has connected to a hub, the browser may list (and filter) it by the hub's own name, the one it has in the SPIKE App. A name filter, if wanted, goes in the same filter object as the service: `{ services: [SERVICE], namePrefix: "Car" }`.
7. **Opening the file directly works** (double-click; Chrome allows Bluetooth for `file://` pages). On a website the page must be `https://` (or `http://localhost`).
8. **Make the hub safe when the page goes away** (tab closed, out of range): stop motors when `p.is_connected` is `False` in the main loop, or in `on_disconnect`. If holding a key drives the robot, also send a stop on `keyup` and on the window's `blur`.

### 7. A web page sends and receives messages

The hub prints each message, replies, and reacts to `"smile"`; it also sends on its own when its left button is pressed. The page shows everything (and logs it to the browser console).

```python
# ===== Hub ===== (examples/web_drive/simple.py)
from spikecomm import Peripheral
from hub import button, light_matrix
import time

p = Peripheral("Hub1")      # the browser lists it as Hub1 or by the hub's own name
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
```

```html
<!-- ===== Web page ===== (examples/web_drive/simple.html) -->
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>SPIKE Simple Messages</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 600px; margin: 2em auto; padding: 0 16px; }
  pre { border: 1px solid #8888; padding: 8px; min-height: 10em; white-space: pre-wrap; }
</style>
</head>
<body>
  <h1>Talk to a SPIKE hub</h1>
  <button id="connect">Connect</button>
  <form id="form">
    <p><input id="message" value="smile"> <button>Send</button></p>
  </form>
  <pre id="output"></pre>

<script>
// spikecomm's Peripheral is a Nordic UART Service (NUS)
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

document.getElementById("connect").onclick = () => connect().catch((e) => show("Error: " + e.message));
document.getElementById("form").onsubmit = (event) => {
  event.preventDefault();    // stay on this page
  send(document.getElementById("message").value);
};
</script>
</body>
</html>
```

To control the hub, call `send(...)` from buttons or keys, e.g. `send("forward;500")`, and split the message on the hub with `decode(msg)` (→ `["forward", 500]`). React to the hub's messages inside `onMessage`.

## Common problems → fixes

| Symptom | Likely cause / fix |
|---|---|
| `ImportError: no module named 'spikecomm'` | File not on that hub. Copy it with `mpremote cp spikecomm.py :spikecomm.py` (see README). |
| `ImportError: spikecomm can't use Bluetooth in a program started from a program slot or the SPIKE App's Run button` (or `OSError: [Errno 1] EPERM` at `import bluetooth`) | The program was started with the Run button / hub menu. Start it from the REPL instead (see "How programs must be started" above). Don't try to work around it with `import ubluetooth` — that crashes the hub. |
| An updated spikecomm seems to have no effect | Two copies on the hub; `/flash/spikecomm.py` wins over `/flash/lib/spikecomm.py`. Check `spikecomm.__file__` and delete the extra copy. |
| Scanner never receives anything | Prefix mismatch (case-sensitive); sender program not running; sender's loop ended. Add `verbose=True` on both. |
| Receiver gets odd values like `["1;42"]` | One prefix is the start of another (`"!S"` vs `"!S1"`). Use distinct prefixes. |
| `ValueError: Encoded name ... is 27 chars (max 26)` | Shorter prefix, fewer values, or round floats. |
| `connect()` returns `False` | Peripheral not running/advertising, names don't match, or Peripheral already has a Central. Start the Peripheral first; use a longer timeout. |
| Program stops receiving after a few seconds | Main loop missing — the program ended. Add `while True: time.sleep_ms(50)`. |
| Callback error printed repeatedly (`IndexError`, `TypeError`) | Message format differs from what the callback expects; check `len(values)` / use `decode`. |
| One message arrives as two | It contained `"\n"`. Remove newlines; use `encode(...)` for several values. |
| `wait_for` hangs | Called inside a callback, or no timeout and the message came before the call. |
| Robot keeps driving after the controller stops | Add `on_disconnect` on the Peripheral that stops the motors. |
| Hub isn't in the browser's device list | Hub program not running, or started with the Run button; another page or hub is already connected to it (one Central at a time); the page filters by a name the browser doesn't know the hub by (it may use the hub's own name from the SPIKE App): filter by service only. |
| `navigator.bluetooth` is `undefined` | Safari, Firefox, or a browser on iPhone/iPad: use Chrome or Edge. On a website the page must be `https://`. |
| `SecurityError: Failed to execute 'requestDevice' on 'Bluetooth': Must be handling a user gesture to show a permission request.` | `requestDevice()` ran when the page loaded; call it from a button's click handler. |
| `SecurityError: Origin is not allowed to access any service.` | The page filters by name only: put `services: [SERVICE]` in the same filter object (or add `optionalServices: [SERVICE]` to `requestDevice()`). |
| `NetworkError: GATT operation already in progress.` | Two writes at once: queue them (Template 7's `send`). |
| `NotFoundError: User cancelled the requestDevice() chooser.` | The device list was closed without picking a hub. |

## SPIKE App 3 hub API cheat sheet (names verified on the hub)

```python
from hub import port, button, light_matrix, motion_sensor   # port.A … port.F
import motor, distance_sensor, color_sensor, force_sensor, color
import time

motor.run(port.A, 500)              # run at 500 degrees/second (negative = reverse)
motor.stop(port.A)                  # (after motor.run the motor coasts on a little: ~70° at 720 °/s)
motor.relative_position(port.A)     # degrees
motor.run_for_degrees(port.A, 1080, 720)   # 3 turns at 720 °/s, stops exactly at the target
motor.run_for_time(port.A, 1000, 500)      # 1000 ms at 500 °/s
# Both start the motor and return at once: no await needed in a while-True program, and
# callbacks keep firing. Watch relative_position to know when the move is done.
# (In async programs, `await motor.run_for_degrees(...)` waits until it's done.)
motor.velocity(port.A)              # NOT degrees/second: a medium motor at 720 °/s reads about 65
# Don't use motor.status(): it reports wrong values on this firmware.

distance_sensor.distance(port.B)    # millimetres; -1 if nothing detected
color_sensor.color(port.C)          # color number (compare with color.RED, color.GREEN, ...); -1 if none
color_sensor.reflection(port.C)     # 0–100
force_sensor.force(port.D)          # 0–100
force_sensor.pressed(port.D)        # bool

button.pressed(button.LEFT)         # > 0 while pressed (also button.RIGHT)
motion_sensor.tilt_angles()         # (yaw, pitch, roll) in tenths of a degree
light_matrix.show_image(light_matrix.IMAGE_HAPPY)   # also IMAGE_YES, IMAGE_NO, IMAGE_ARROW_N … _NW
light_matrix.show([100] * 5 + [0] * 20)   # 25 brightnesses (0–100), row by row from the top
light_matrix.write("HI")            # scrolls in the background; a later show/show_image replaces it
light_matrix.clear()

time.sleep_ms(100)
time.ticks_ms(); time.ticks_diff(a, b)
```

Reading a sensor on a port with nothing plugged in raises `OSError` — make sure the ports in the code match the robot.
