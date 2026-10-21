"""
spikecomm.py — Bluetooth communication library for LEGO SPIKE Prime
=====================================================================
Version : 1.2.0
Platform: LEGO SPIKE Prime (SPIKE App 3 firmware) / MicroPython

Simple, student-friendly BLE communication between SPIKE Prime hubs.
Single file — copy to the hub, then:  from spikecomm import Beacon, Scanner

HOW TO RUN: start your program from the hub's REPL over USB (paste mode,
exec(open("/flash/program/00/program.py").read()), or `mpremote run`).
The SPIKE App's Run button and the hub's program menu can't use Bluetooth
on this firmware. After starting, you can unplug the USB cable.

──────────────────────────────────────────────────────────────────────
CHOOSING A MODE
──────────────────────────────────────────────────────────────────────
  Beacon / Scanner  (no connection needed — like a radio broadcast)
	· One hub broadcasts data; any number of hubs can receive it.
	· A hub can run a Beacon AND Scanners at the same time.
	· Great for: sensor sharing, one-to-many, groups of 3+ hubs.
	· Tradeoff: 26 chars max (prefix + data). Not guaranteed delivery.

  Peripheral / Central  (full BLE connection — like a phone call)
	· Two hubs connect and send messages back and forth reliably.
	· Great for: commands, responses, longer text, every message counts.
	· Tradeoff: one Central per Peripheral at a time.

──────────────────────────────────────────────────────────────────────
QUICK START — BEACON MODE
──────────────────────────────────────────────────────────────────────
  # Hub A — broadcasting sensor readings
  from spikecomm import Beacon
  b = Beacon("!A")                         # "!A" is Hub A's unique tag
  while True:
	  b.broadcast(distance, force)         # advertises e.g. "!A140;23"
	  time.sleep_ms(100)

  # Hub B — receiving those readings
  from spikecomm import Scanner
  s = Scanner("!A")
  def on_data(values):
	  print("Dist:", values[0], "  Force:", values[1])
  s.listen(on_data)                        # non-blocking; runs in background

──────────────────────────────────────────────────────────────────────
QUICK START — DIRECT MODE
──────────────────────────────────────────────────────────────────────
  # Hub A — Peripheral (server, waits for connection)
  from spikecomm import Peripheral
  p = Peripheral("HubA")
  p.advertise()
  def on_message(msg):
	  p.send("got it: " + msg)
  p.listen(on_message)

  # Hub B — Central (client, initiates connection)
  from spikecomm import Central
  c = Central("HubA")
  if c.connect():
	  c.listen(lambda msg: print("Reply:", msg))
	  c.send("hello")

──────────────────────────────────────────────────────────────────────
CALLBACK RULES
──────────────────────────────────────────────────────────────────────
  Callbacks run "in the background" between lines of your main code.
	· Keep them short: save values to a variable, update a motor, send a reply.
	· Never call blocking functions inside a callback (connect, read,
	  read_all, wait_for, time.sleep). Events can't arrive while a
	  callback is running, so these would stall.
	· If your callback raises an error, spikecomm prints it and keeps running.

──────────────────────────────────────────────────────────────────────
DEBUGGING
──────────────────────────────────────────────────────────────────────
  Pass verbose=True to any class to print what's happening:

  b = Beacon("!S", verbose=True)
  b.broadcast(42, 3.14)
  # [spikecomm Beacon] Broadcasting "!S42;3.14" (9 of 26 chars used)

  s = Scanner("!S", verbose=True)
  s.listen(my_callback)
  # [spikecomm Scanner] Listening for prefix "!S" ...
  # [spikecomm Scanner] Received "!S42;3.14" → [42, 3.14]  RSSI=-62

──────────────────────────────────────────────────────────────────────
ENCODING HELPERS  (standalone — useful anywhere)
──────────────────────────────────────────────────────────────────────
  from spikecomm import encode, decode
  s = encode(42, 3.14, True)   # -> "42;3.14;1"
  v = decode(s)                # -> [42, 3.14, 1]
"""

__version__ = "1.2.0"
__author__  = "Tufts CEEO"

try:
	import bluetooth
except OSError:
	# SPIKE App 3 firmware refuses Bluetooth (EPERM) to programs started from a
	# program slot or the SPIKE App's Run button: the hub OS owns the radio then.
	# (Importing it as "ubluetooth" gets past the check, but using it crashes the hub.)
	raise ImportError("spikecomm can't use Bluetooth in a program started from a "
					  "program slot or the SPIKE App's Run button. Start the program "
					  "from the REPL instead (README: 'Running spikecomm programs').")
import errno
import micropython
import struct
import sys
import time
from micropython import const


# ─── BLE event constants ──────────────────────────────────────────────────────

_IRQ_CENTRAL_CONNECT             = const(1)
_IRQ_CENTRAL_DISCONNECT          = const(2)
_IRQ_GATTS_WRITE                 = const(3)
_IRQ_SCAN_RESULT                 = const(5)
_IRQ_PERIPHERAL_CONNECT          = const(7)
_IRQ_PERIPHERAL_DISCONNECT       = const(8)
_IRQ_GATTC_SERVICE_RESULT        = const(9)
_IRQ_GATTC_SERVICE_DONE          = const(10)
_IRQ_GATTC_CHARACTERISTIC_RESULT = const(11)
_IRQ_GATTC_CHARACTERISTIC_DONE   = const(12)
_IRQ_GATTC_WRITE_DONE            = const(17)
_IRQ_GATTC_NOTIFY                = const(18)
_IRQ_MTU_EXCHANGED               = const(21)

# ─── BLE advertising type constants ──────────────────────────────────────────

_ADV_TYPE_FLAGS            = const(0x01)
_ADV_TYPE_NAME             = const(0x09)
_ADV_TYPE_UUID16_COMPLETE  = const(0x03)
_ADV_TYPE_UUID128_COMPLETE = const(0x07)

_ADV_IND        = const(0x00)   # connectable advertisement (a Peripheral)
_ADV_DIRECT_IND = const(0x01)

# An advertising packet holds 31 bytes: 3 for flags + 2 for the name header
# leaves 26 bytes for the name itself.
_MAX_NAME_BYTES = const(26)

# ─── GATT characteristic flags ────────────────────────────────────────────────

_FLAG_READ              = const(0x0002)
_FLAG_WRITE_NO_RESPONSE = const(0x0004)
_FLAG_WRITE             = const(0x0008)
_FLAG_NOTIFY            = const(0x0010)

# ─── Nordic UART Service UUIDs (industry-standard BLE serial) ─────────────────

_UART_SERVICE_UUID = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
_UART_RX_CHAR_UUID = bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")
_UART_TX_CHAR_UUID = bluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E")

_UART_SERVICE_DEF = (
	_UART_SERVICE_UUID,
	(
		(_UART_TX_CHAR_UUID, _FLAG_READ | _FLAG_NOTIFY),
		(_UART_RX_CHAR_UUID, _FLAG_WRITE | _FLAG_WRITE_NO_RESPONSE),
	),
)

# Direct-mode messages end with "\n" so long messages can be split into
# packets and rejoined. The Peripheral buffers this many incoming bytes.
_RX_BUFFER_SIZE = const(512)
_MAX_MESSAGE    = const(1000)   # longer messages are delivered in pieces
_DEFAULT_MTU    = const(23)     # each BLE packet carries MTU - 3 bytes of data
_MAX_OUTBOX     = const(20)     # packets a Central callback may queue before send() drops
_MAX_UNHEARD    = const(10)     # messages kept until listen() is called


# ─── Shared radio and event dispatch ──────────────────────────────────────────
# A hub has one Bluetooth radio and MicroPython allows one event handler for
# it. Every spikecomm object registers here and each event goes to all of
# them, so a Beacon, Scanners, etc. can share the radio on one hub.

_ble = None
_handlers = {}        # "Scanner:!A" etc. -> that object's _irq method
_scan_requests = 0    # how many things currently need the radio to scan
_in_event = False     # True while events (and student callbacks) are being handled


def _radio(key=None, handler=None):
	"""Return the hub's BLE radio (switched on), optionally registering a handler."""
	global _ble
	if _ble is None:
		_ble = bluetooth.BLE()
		_ble.active(True)
		_ble.irq(_dispatch)
	if key:
		_handlers[key] = handler   # re-creating the same object replaces the old one
	return _ble


def _dispatch(event, data):
	global _in_event
	_in_event = True
	try:
		for handler in list(_handlers.values()):
			try:
				handler(event, data)
			except Exception as e:
				# An uncaught error here would switch off all BLE events for good.
				print("[spikecomm] Internal error:")
				sys.print_exception(e)
	finally:
		_in_event = False


def _scan(start):
	"""Request (True) or release (False) scanning. The radio scans while any request is open."""
	global _scan_requests
	if start:
		_scan_requests += 1
		if _scan_requests == 1:
			_ble.gap_scan(0, 30000, 30000)   # 0 ms duration = scan until stopped
	elif _scan_requests > 0:
		_scan_requests -= 1
		if _scan_requests == 0:
			_ble.gap_scan(None)


def _retry(fn, *args):
	"""Call a BLE send function, retrying for up to 1 s while the radio is busy.
	Inside a callback the radio can't make progress, so it only tries once."""
	start = time.ticks_ms()
	while True:
		try:
			return fn(*args)
		except OSError as e:
			if _in_event or e.args[0] not in (errno.EALREADY, errno.ENOMEM) \
					or time.ticks_diff(time.ticks_ms(), start) > 1000:
				raise
		time.sleep_ms(2)


def _call(tag, fn, *args):
	"""Run a student's callback; print errors instead of letting them stop BLE."""
	try:
		fn(*args)
	except Exception as e:
		print("[spikecomm {}] Error inside your callback function:".format(tag))
		sys.print_exception(e)


def _later(fn, *args):
	"""Run fn(*args) just after the current Bluetooth event has been fully handled."""
	def run(_):
		global _in_event
		_in_event = True
		try:
			fn(*args)
		finally:
			_in_event = False
	try:
		micropython.schedule(run, None)
	except RuntimeError:     # scheduler queue full: run it now instead
		fn(*args)


def _wait_for(obj, tag, condition, timeout, first_value, give_up=None):
	"""Shared body of the wait_for() methods. `obj._callback` is wrapped while waiting."""
	if callable(condition):
		check = condition
	elif first_value:
		check = lambda v: bool(v) and v[0] == condition
	else:
		check = lambda m: m == condition

	result = [None, False, False]   # [matched value, found?, error reported?]
	old_callback = obj._callback

	def _intercept(value):
		if not result[1]:
			try:
				matched = check(value)
			except Exception as e:
				matched = False
				if not result[2]:
					result[2] = True
					print("[spikecomm {}] wait_for condition raised {!r} — treated as no match".format(tag, e))
			if matched:
				result[0] = value
				result[1] = True
		if old_callback:           # keep an existing listen() callback alive
			old_callback(value)

	obj._log("wait_for: condition={}, timeout={}ms".format(
		"callable" if callable(condition) else repr(condition), timeout))

	obj._callback = _intercept
	start = time.ticks_ms()
	try:
		while not result[1]:
			if timeout is not None and time.ticks_diff(time.ticks_ms(), start) >= timeout:
				break
			if give_up and give_up():
				obj._log("wait_for: connection lost — giving up.")
				break
			time.sleep_ms(10)
	finally:
		obj._callback = old_callback

	if result[1]:
		obj._log("wait_for: matched → {!r}".format(result[0]))
	elif timeout is not None:
		obj._log("wait_for: timed out after {}ms".format(timeout))
	return result[0]


# ─── Internal advertising and message helpers ────────────────────────────────

def _build_adv_payload(name=None, services=None, flags=True):
	"""Build a raw BLE advertising packet."""
	payload = bytearray()

	def _append(adv_type, value):
		payload.extend(struct.pack("BB", len(value) + 1, adv_type))
		payload.extend(value)

	if flags:
		_append(_ADV_TYPE_FLAGS, struct.pack("B", 0x06))  # general discoverable, no BR/EDR

	if name:
		if isinstance(name, str):
			name = name.encode("utf-8")
		_append(_ADV_TYPE_NAME, name)

	if services:
		for uuid in services:
			b = bytes(uuid)
			if len(b) == 2:
				_append(_ADV_TYPE_UUID16_COMPLETE, b)
			elif len(b) == 16:
				_append(_ADV_TYPE_UUID128_COMPLETE, b)

	return bytes(payload)


def _extract_name(adv_data):
	"""Extract the device name string from a raw advertising payload."""
	i = 0
	while i + 1 < len(adv_data):
		field_len = adv_data[i]
		if field_len == 0:
			break
		if adv_data[i + 1] == _ADV_TYPE_NAME:
			try:
				return adv_data[i + 2 : i + 1 + field_len].decode("utf-8")
			except Exception:
				return ""
		i += 1 + field_len
	return ""


def _check_name(kind, name):
	n = len(name.encode("utf-8"))
	if n > _MAX_NAME_BYTES:
		raise ValueError("{} '{}' is {} chars (max {}). Shorten it.".format(
			kind, name, n, _MAX_NAME_BYTES))


def _addr_str(addr):
	return ":".join("{:02X}".format(b) for b in addr)


def _frame(message):
	"""Turn a message into bytes ending with the "\\n" end-of-message marker."""
	if isinstance(message, str):
		data = message.encode("utf-8")
	elif isinstance(message, (bytes, bytearray)):
		data = bytes(message)
	else:
		data = str(message).encode("utf-8")   # numbers etc. are sent as text
	return data + b"\n"


def _chunks(data, size):
	return [data[i : i + size] for i in range(0, len(data), size)]


def _unframe(pending, data):
	"""Add received bytes to `pending`. Returns (complete messages, new pending)."""
	pending += data
	parts = pending.split(b"\n")
	pending = parts.pop()
	if len(pending) > _MAX_MESSAGE:        # sender never sends "\n": don't grow forever
		parts.append(pending)
		pending = b""
	messages = []
	for raw in parts:
		try:
			messages.append(raw.decode("utf-8").rstrip("\r\x00"))
		except Exception:
			messages.append(raw)
	return messages, pending


def _show(message):
	return message if isinstance(message, str) else repr(message)


def _deliver(obj, tag, msg):
	"""Give a Direct-mode message to the listen() callback, or keep it until one is set."""
	obj._log('Received: "{}"'.format(_show(msg)))
	if obj._callback:
		_call(tag, obj._callback, msg)
	elif len(obj._unheard) < _MAX_UNHEARD:
		obj._unheard.append(msg)


def _set_listener(obj, tag, callback):
	"""listen() for Peripheral/Central: register, then hand over any kept messages."""
	obj._callback = callback
	obj._log("Listener registered.")
	kept, obj._unheard = obj._unheard, []
	for msg in kept:
		_call(tag, callback, msg)


# ═══════════════════════════════════════════════════════════════════════════════
#  PUBLIC ENCODING / DECODING UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

def encode(*values, sep=";", precision=2):
	"""
	Pack one or more values into a compact string for BLE name broadcasting.

	Rules:
	  · Integers   → written as-is                  (42     → "42")
	  · Floats     → rounded, trailing 0s removed    (3.14159 → "3.14", 2.0 → "2")
	  · Booleans   → "1" or "0"                     (True   → "1")
	  · Strings    → passed through as-is            ("go"   → "go")
	  · Anything else → str()

	Args:
		*values   : Values to encode (numbers, booleans, strings).
		sep       : Separator between values. Default ";".
		precision : Decimal places kept for floats. Default 2.

	Returns:
		A compact string.

	Examples:
		encode(42)                  → "42"
		encode(42, 3.14159)         → "42;3.14"
		encode(1, 2, 3)             → "1;2;3"
		encode("hello")             → "hello"
		encode(1, "go", 2.5)        → "1;go;2.5"
		encode(3.14159, precision=4) → "3.1416"
		encode(1, 2, sep=",")       → "1,2"
	"""
	parts = []
	for v in values:
		if isinstance(v, bool):
			parts.append("1" if v else "0")
		elif isinstance(v, float):
			s = "{:.{}f}".format(v, precision)
			if "." in s:
				s = s.rstrip("0").rstrip(".")
			parts.append(s)
		else:
			parts.append(str(v))
	return sep.join(parts)


def decode(data, sep=";"):
	"""
	Unpack a string (received from a BLE broadcast) back into Python values.

	Each token is auto-typed: tried as int first, then float, then left as str.
	So types can change on the way: True arrives as 1, 2.0 arrives as 2,
	and the string "7" arrives as the number 7.

	Args:
		data : Encoded string (or bytes), e.g. "42;3.14;hello".
		sep  : Separator character. Default ";".

	Returns:
		A list of values. Empty list if data is empty or None.

	Examples:
		decode("42;3.14;ok")      → [42, 3.14, "ok"]
		decode("1,2,3", sep=",")  → [1, 2, 3]
		decode("")                → []
	"""
	if not data:
		return []
	if isinstance(data, (bytes, bytearray)):
		data = data.decode("utf-8")
	result = []
	for token in data.split(sep):
		token = token.strip()
		try:
			result.append(int(token))
			continue
		except ValueError:
			pass
		try:
			result.append(float(token))
			continue
		except ValueError:
			pass
		result.append(token)
	return result


# ═══════════════════════════════════════════════════════════════════════════════
#  BEACON MODE  —  broadcast data without connecting
# ═══════════════════════════════════════════════════════════════════════════════

class Beacon:
	"""
	Broadcast one or more values by encoding them into this hub's BLE device name.
	Nearby Scanners can read that name without establishing any connection.

	Think of it like a radio transmitter — just broadcast and anyone nearby
	with the right "frequency" (prefix) can tune in.

	Hardware limit
	--------------
	BLE advertising names are capped at 26 characters total (prefix + data).
	Keep prefixes short (2–3 chars) and send compact numbers.
	A ValueError is raised if the encoded name is too long.

	A hub can run a Beacon and Scanner(s) at the same time, but only one
	Beacon OR Peripheral (both use the hub's single advertisement).

	Debugging
	---------
	Pass verbose=True to see exactly what's being broadcast:
		b = Beacon("!S", verbose=True)
		b.broadcast(42, 3.14)
		# [spikecomm Beacon] Broadcasting "!S42;3.14" (9 of 26 chars used)

	Example
	-------
		from spikecomm import Beacon
		b = Beacon("!S")

		# In your main loop:
		b.broadcast(motor.velocity(port.A), distance_sensor.distance(port.B))
		# Broadcasts e.g. "!S75;230" — any matching Scanner will receive [75, 230]

		# To stop broadcasting:
		b.stop()
	"""

	MAX_NAME_LEN = _MAX_NAME_BYTES

	def __init__(self, prefix="!S", interval_ms=100, verbose=False):
		"""
		Create a Beacon.

		Args:
			prefix      : Short unique tag prepended to every broadcast.
						  Pick something distinctive like "!A", "!B", "!C".
						  Must match the prefix used by your Scanner(s).
						  One prefix must not start another ("!S" and "!S1"
						  clash: a Scanner("!S") would also hear "!S1").
			interval_ms : How often to re-send the advertisement (milliseconds).
						  Default 100 ms, which is also the minimum: smaller
						  values are raised to 100.
			verbose     : Print debug info to the console. Default False.
						  Useful when testing — turn off for final code.
		"""
		if len(prefix) > 5:
			raise ValueError("Prefix '{}' is {} chars — keep it 5 or fewer.".format(
				prefix, len(prefix)))
		interval_ms = max(interval_ms, 100)   # BLE minimum for a non-connectable broadcast
		self._prefix = prefix
		self._interval_us = interval_ms * 1000
		self._verbose = verbose
		self._broadcasting = False
		self._last = None
		self._ble = _radio()
		if self._verbose:
			print("[spikecomm Beacon] Ready. Prefix='{}', interval={}ms".format(
				prefix, interval_ms))

	def _log(self, *args):
		if self._verbose:
			print("[spikecomm Beacon]", *args)

	def broadcast(self, *values, sep=";", precision=2):
		"""
		Encode `values` and start (or update) the BLE advertisement.
		Calling broadcast() again mid-loop updates the data on-the-fly.
		If the data hasn't changed, the call does nothing (cheap to repeat).

		Args:
			*values   : Values to send. Numbers, booleans, or short strings.
			sep       : Separator between values. Default ";".
			precision : Decimal places for floats. Default 2.

		Raises:
			ValueError : If the full encoded name exceeds MAX_NAME_LEN characters.

		Examples:
			b.broadcast(42)                     # "!S42"
			b.broadcast(42, 3.14)               # "!S42;3.14"
			b.broadcast(True, 99, 1.5)          # "!S1;99;1.5"
			b.broadcast("go", 42)               # "!Sgo;42"
			b.broadcast(3.14159, precision=4)   # "!S3.1416"
		"""
		name = self._prefix + encode(*values, sep=sep, precision=precision)
		_check_name("Encoded name", name)
		if self._broadcasting and name == self._last:
			return
		# connectable=False: a Beacon only broadcasts; Centrals can't connect to it.
		self._ble.gap_advertise(self._interval_us, adv_data=_build_adv_payload(name=name),
								connectable=False)
		self._last = name
		self._broadcasting = True
		self._log('Broadcasting "{}" ({} of {} chars used)'.format(
			name, len(name), self.MAX_NAME_LEN))

	def stop(self):
		"""Stop broadcasting."""
		self._ble.gap_advertise(None)
		self._broadcasting = False
		self._last = None
		self._log("Stopped.")

	@property
	def is_broadcasting(self):
		"""True if currently transmitting."""
		return self._broadcasting


class Scanner:
	"""
	Passively listen for Beacon devices and decode their broadcast data.
	No connection is made — works by reading BLE advertisements.

	Think of it like a radio receiver — tune to the right "frequency"
	(prefix) and pick up whatever the Beacon transmits.

	You can create several Scanners on one hub (e.g. one per prefix), and
	use them alongside a Beacon on the same hub.

	Debugging
	---------
	Pass verbose=True to see every packet received:
		s = Scanner("!S", verbose=True)
		s.listen(my_callback)
		# [spikecomm Scanner] Listening for prefix "!S" ...
		# [spikecomm Scanner] Received "!S42;3.14" → [42, 3.14]  RSSI=-62

	Example
	-------
		from spikecomm import Scanner
		s = Scanner("!S")

		# Option 1 — Non-blocking background listener (recommended for loops)
		def on_reading(values):
			motor.run(port.A, values[0])
		s.listen(on_reading)

		# Option 2 — One-shot blocking read
		values = s.read(timeout=2000)
		if values:
			print("Got:", values)

		# Option 3 — Collect from ALL matching beacons
		all_data = s.read_all(timeout=3000)
		for address, vals in all_data.items():
			print(address, "->", vals)
	"""

	def __init__(self, prefix="!S", verbose=False):
		"""
		Create a Scanner.

		Args:
			prefix  : The unique tag to filter on.
					  Must match the Beacon's prefix (e.g. "!S").
			verbose : Print debug info to the console. Default False.
					  Useful when testing — turn off for final code.
		"""
		self._prefix = prefix
		self._verbose = verbose
		self._callback = None
		self._listening = False
		self._found = {}   # device address -> (full_name, values, rssi)
		self._ble = _radio("Scanner:" + prefix, self._irq)
		if self._verbose:
			print("[spikecomm Scanner] Ready. Looking for prefix='{}'".format(prefix))

	def _log(self, *args):
		if self._verbose:
			print("[spikecomm Scanner]", *args)

	def _irq(self, event, data):
		if event == _IRQ_SCAN_RESULT:
			addr_type, addr, adv_type, rssi, adv_data = data
			name = _extract_name(bytes(adv_data))
			if name.startswith(self._prefix):
				values = decode(name[len(self._prefix):])
				key = _addr_str(addr)
				is_new = key not in self._found
				self._found[key] = (name, values, rssi)
				# In verbose mode, log every packet during one-shot reads,
				# but only log the first sighting of each device during
				# continuous listen() to avoid flooding the console.
				if self._verbose:
					if self._callback is None or is_new:
						self._log('Received "{}" → {}  RSSI={}'.format(name, values, rssi))
				if self._callback:
					_call("Scanner", self._callback, values)

	def listen(self, callback):
		"""
		Start continuous background listening. Calls `callback` every time a
		matching broadcast arrives (about 10 times per second per Beacon, even
		if the data hasn't changed). Returns immediately — non-blocking.

		Args:
			callback : Function called as  callback(values)
					   where values is a list of decoded numbers/strings.

		Example:
			def handle(values):
				speed = values[0]
				motor.run(port.A, speed)

			s.listen(handle)
			# Your main loop continues here — handle() fires in the background
		"""
		self._callback = callback
		if not self._listening:
			self._listening = True
			_scan(True)
		self._log('Listening for prefix "{}" ...'.format(self._prefix))

	def stop(self):
		"""Stop listening (turn off the listen() callback)."""
		self._callback = None
		if self._listening:
			self._listening = False
			_scan(False)
		self._log("Stopped.")

	def read(self, timeout=2000):
		"""
		Blocking one-shot read: scan until a matching Beacon is found, then return.
		Useful when you just need one value and can afford to wait.
		Safe to use while listen() is running.

		Args:
			timeout : Maximum wait time in milliseconds. Default 2000.

		Returns:
			A list of decoded values (e.g. [42, 3.14]), or None if nothing found.

		Example:
			data = s.read(timeout=3000)
			if data:
				distance, force = data[0], data[1]
			else:
				print("No beacon found.")
		"""
		self._found.clear()
		self._log('Scanning for "{}" (timeout {}ms) ...'.format(self._prefix, timeout))
		_scan(True)
		start = time.ticks_ms()
		try:
			while not self._found and time.ticks_diff(time.ticks_ms(), start) < timeout:
				time.sleep_ms(10)
		finally:
			_scan(False)
		if self._found:
			name, values, rssi = next(iter(self._found.values()))
			self._log('Done. Got "{}" → {}'.format(name, values))
			return values
		self._log("Done. Nothing found.")
		return None

	def read_all(self, timeout=2000):
		"""
		Scan for the full `timeout` duration and return data from EVERY
		matching Beacon found nearby (great when collecting from multiple hubs).

		Args:
			timeout : How long to scan in milliseconds. Default 2000.

		Returns:
			Dict mapping each Beacon's Bluetooth address → its latest values.
			e.g. {"2C:AB:33:5D:C2:BC": [42, 3.14], "2C:AB:33:5D:C3:01": [99, 1]}
			Empty dict if nothing found. len(result) = number of hubs heard.

		Example:
			all_hubs = s.read_all(timeout=3000)
			total = sum(v[0] for v in all_hubs.values())
			print("Sum of first values from", len(all_hubs), "hubs:", total)
		"""
		self._found.clear()
		self._log('Scanning all "{}" devices for {}ms ...'.format(self._prefix, timeout))
		_scan(True)
		try:
			time.sleep_ms(timeout)
		finally:
			_scan(False)
		result = {addr: values for addr, (name, values, rssi) in self._found.items()}
		self._log("Done. Found {} device(s): {}".format(
			len(result), [name for name, values, rssi in self._found.values()]))
		return result

	def wait_for(self, condition, timeout=None):
		"""
		Block until a broadcast meets `condition`, then return its values.

		Can be used standalone or alongside an active listen() — both fire.

		Args:
			condition : What to wait for. Two forms:
						  · A value    — waits until values[0] equals it exactly.
							e.g. wait_for(3)
						  · A function — waits until condition(values) returns True.
							e.g. wait_for(lambda v: v[0] < 50)
							If the function raises an error, that broadcast
							counts as "no match".
			timeout   : Max time to wait in milliseconds.
						Default None = wait forever.
						Returns None if the timeout expires before a match.

		Returns:
			The list of decoded values that triggered the match, or None on timeout.

		Examples:
			# Wait until any beacon broadcasts exactly the value 3
			result = scanner.wait_for(3)

			# Wait until a distance reading drops below 50
			result = scanner.wait_for(lambda v: v[0] < 50)
			if result:
				print("Someone nearby! Distance =", result[0])

			# Combine two conditions — wait for close AND pressed hard
			result = scanner.wait_for(lambda v: v[0] < 50 and v[1] > 80)

			# Wait up to 5 seconds, then give up
			result = scanner.wait_for(99, timeout=5000)
			if result is None:
				print("Never saw 99 within 5 seconds")
		"""
		_scan(True)
		try:
			return _wait_for(self, "Scanner", condition, timeout, True)
		finally:
			_scan(False)

	@property
	def is_listening(self):
		"""True while listen() is active."""
		return self._listening


# ═══════════════════════════════════════════════════════════════════════════════
#  DIRECT MODE  —  full BLE connection for two-way messaging
# ═══════════════════════════════════════════════════════════════════════════════

class Peripheral:
	"""
	Set up this hub as a BLE server. Another hub running Central can find and
	connect to it for reliable two-way communication.

	Uses the Nordic UART Service — the standard for BLE serial data.

	Think of it like a server waiting for a client to call it. Once connected,
	both sides can send and receive messages freely. Messages arrive complete
	and in order; long messages are split into packets and rejoined for you.

	One Central can be connected at a time. When it disconnects, the
	Peripheral starts advertising again automatically.

	Debugging
	---------
	Pass verbose=True to trace the full connection and message lifecycle:
		p = Peripheral("HubA", verbose=True)
		p.advertise()
		# [spikecomm Peripheral] Advertising as "HubA" ...
		# [spikecomm Peripheral] Central connected  (handle=1025, total connected=1)
		# [spikecomm Peripheral] Received: "hello"
		# [spikecomm Peripheral] Sent: "got it"  (to 1 device(s))

	Example
	-------
		from spikecomm import Peripheral
		p = Peripheral("RobotA")
		p.advertise()          # start broadcasting so others can find us

		def on_command(msg):
			print("Received:", msg)
			if msg == "status":
				p.send("running")

		p.listen(on_command)

		while True:
			# Your main code here — callbacks fire in the background
			time.sleep_ms(50)
	"""

	def __init__(self, name="SPIKE", verbose=False):
		"""
		Create a Peripheral. Create only one per hub.

		Args:
			name    : This hub's BLE display name — what Central devices look for.
					  Should be unique among your hubs (e.g. "HubA", "Sensor1").
					  Max 26 characters.
			verbose : Print debug info to the console. Default False.
					  Useful when testing — turn off for final code.
		"""
		_check_name("Peripheral name", name)
		self._name = name
		self._verbose = verbose
		self._connections = {}     # conn_handle -> MTU (packet size) for that link
		self._unheard     = []     # messages that arrived before listen() was called
		self._callback            = None
		self._connect_callback    = None
		self._disconnect_callback = None
		self._auto_readvertise    = True
		self._interval_us         = 100000
		self._rx_pending          = b""
		self._ble = _radio("Peripheral", self._irq)
		((self._tx_handle, self._rx_handle),) = self._ble.gatts_register_services(
			(_UART_SERVICE_DEF,)
		)
		# Append mode: if several packets arrive before we read them, none are lost.
		self._ble.gatts_set_buffer(self._rx_handle, _RX_BUFFER_SIZE, True)
		if self._verbose:
			print("[spikecomm Peripheral] Ready. Name='{}'".format(name))

	def _log(self, *args):
		if self._verbose:
			print("[spikecomm Peripheral]", *args)

	def _irq(self, event, data):
		if event == _IRQ_CENTRAL_CONNECT:
			conn_handle, _, _ = data
			self._connections[conn_handle] = _DEFAULT_MTU
			self._rx_pending = b""
			self._log("Central connected  (handle={}, total connected={})".format(
				conn_handle, len(self._connections)))
			if self._connect_callback:
				# The hub's Bluetooth stack finishes setting up the connection only
				# after this event returns; a send() inside it would be lost.
				_later(_call, "Peripheral", self._connect_callback, conn_handle)

		elif event == _IRQ_CENTRAL_DISCONNECT:
			conn_handle, _, _ = data
			if conn_handle not in self._connections:
				return
			del self._connections[conn_handle]
			self._log("Central disconnected  (handle={}, total connected={})".format(
				conn_handle, len(self._connections)))
			if self._disconnect_callback:
				_call("Peripheral", self._disconnect_callback, conn_handle)
			if self._auto_readvertise:
				self.advertise(self._interval_us // 1000)   # re-open for new connections

		elif event == _IRQ_GATTS_WRITE:
			conn_handle, value_handle = data
			if value_handle == self._rx_handle:
				messages, self._rx_pending = _unframe(
					self._rx_pending, self._ble.gatts_read(value_handle))
				for msg in messages:
					_deliver(self, "Peripheral", msg)

		elif event == _IRQ_MTU_EXCHANGED:
			conn_handle, mtu = data
			if conn_handle in self._connections:
				self._connections[conn_handle] = mtu

	# ── Connection management ────────────────────────────────────────────────

	def advertise(self, interval_ms=100):
		"""
		Start advertising so Central devices can discover and connect.
		Call this once at startup; it restarts automatically after disconnects.

		Args:
			interval_ms : How often to broadcast the advertisement (ms). Default 100.

		Example:
			p.advertise()
		"""
		self._auto_readvertise = True
		self._interval_us = interval_ms * 1000
		self._ble.gap_advertise(
			self._interval_us,
			adv_data=_build_adv_payload(name=self._name),
			resp_data=_build_adv_payload(services=[_UART_SERVICE_UUID], flags=False),
		)
		self._log('Advertising as "{}" ...'.format(self._name))

	def stop_advertising(self):
		"""
		Stop accepting new connections (existing connections are unaffected).
		Advertising will NOT restart automatically after a disconnect.
		"""
		self._auto_readvertise = False
		self._ble.gap_advertise(None)
		self._log("Stopped advertising.")

	def disconnect(self):
		"""
		Disconnect the connected Central.
		Advertising restarts automatically (unless stop_advertising() was called).
		"""
		for conn_handle in list(self._connections):
			try:
				self._ble.gap_disconnect(conn_handle)
			except Exception:
				pass
		self._log("Disconnected all.")

	# ── Sending and receiving ────────────────────────────────────────────────

	def send(self, message):
		"""
		Send a message to the connected Central.

		Args:
			message : A string (numbers are converted to text), up to 1000 chars;
					  must not contain "\\n" (that marks the end of a message).

		Returns:
			True if sent, False if no Central is connected or sending failed.

		Examples:
			p.send("ready")
			p.send(distance_sensor.distance(port.A))
			p.send(encode(x, y, heading))   # send multiple values
		"""
		if not self._connections:
			self._log('send("{}") called but no Central is connected — message dropped.'.format(
				_show(message)))
			return False
		data = _frame(message)
		ok = True
		for conn_handle, mtu in list(self._connections.items()):
			try:
				for chunk in _chunks(data, mtu - 3):
					_retry(self._ble.gatts_notify, conn_handle, self._tx_handle, chunk)
			except Exception as e:
				ok = False
				print("[spikecomm Peripheral] send error:", e)
		self._log('Sent: "{}"  (to {} device(s))'.format(_show(message), len(self._connections)))
		return ok

	def listen(self, callback):
		"""
		Register a function to call whenever a message is received.
		Messages that arrived before listen() was called (up to 10) are
		passed to it right away.

		Args:
			callback : Function called as  callback(message: str)

		Example:
			def on_message(msg):
				print("Got:", msg)
				if msg == "stop":
					motor.stop(port.A)
			p.listen(on_message)
		"""
		_set_listener(self, "Peripheral", callback)

	def wait_for(self, condition, timeout=None):
		"""
		Block until a received message meets `condition`, then return it.
		Works before a Central has connected: it waits for the connection too.

		Can be used alongside an active listen() — both callbacks fire.

		Args:
			condition : What to wait for. Two forms:
						  · A string   — waits until the message equals it exactly.
							e.g. wait_for("go")
						  · A function — waits until condition(message) returns True.
							e.g. wait_for(lambda msg: int(msg) > 100)
							If the function raises an error, that message
							counts as "no match".
			timeout   : Max time to wait in milliseconds.
						Default None = wait forever.
						Returns None if the timeout expires before a match.

		Returns:
			The message string that triggered the match, or None on timeout.

		Examples:
			# Wait until the Central sends exactly "start"
			p.wait_for("start")
			motor.run(port.A, 500)

			# Wait for a message that is a large number
			msg = p.wait_for(lambda m: int(m) > 100)
			print("Got big number:", msg)

			# Use decode() to inspect multi-value messages
			msg = p.wait_for(lambda m: decode(m)[0] < 50)
			print("Distance is close:", decode(msg)[0])

			# Wait at most 10 seconds
			msg = p.wait_for("ready", timeout=10000)
			if msg is None:
				print("Central never sent 'ready' — check the connection")
		"""
		return _wait_for(self, "Peripheral", condition, timeout, False)

	def on_connect(self, callback):
		"""
		Register a function to call when a Central connects.
		It runs once the connection is fully set up, so it may send() a
		welcome message.

		Args:
			callback : Function called as  callback(conn_handle: int)

		Example:
			p.on_connect(lambda h: p.send("welcome!"))
		"""
		self._connect_callback = callback

	def on_disconnect(self, callback):
		"""
		Register a function to call when a Central disconnects.

		Args:
			callback : Function called as  callback(conn_handle: int)
		"""
		self._disconnect_callback = callback

	# ── Status ───────────────────────────────────────────────────────────────

	@property
	def is_connected(self):
		"""True if a Central is currently connected."""
		return len(self._connections) > 0

	@property
	def connection_count(self):
		"""Number of Centrals currently connected."""
		return len(self._connections)


class Central:
	"""
	Connect this hub to a Peripheral for reliable two-way communication.
	Scans for a named hub, connects, and exchanges messages.

	Think of it like a phone: you dial (connect), talk (send/listen), and hang up.
	Messages arrive complete and in order; long messages are split into
	packets and rejoined for you.

	Debugging
	---------
	Pass verbose=True to trace every step of the connection process:
		c = Central("HubA", verbose=True)
		c.connect()
		# [spikecomm Central] Scanning for "HubA" (up to 10000ms) ...
		# [spikecomm Central] Found "HubA" (RSSI=-55) — connecting ...
		# [spikecomm Central] Connected. Discovering services ...
		# [spikecomm Central] Ready ✓ (TX handle=9, RX handle=12)
		# [spikecomm Central] Sent: "hello"
		# [spikecomm Central] Received: "got it"

	Example
	-------
		from spikecomm import Central
		c = Central("RobotA")    # name of the hub to connect to

		def on_reply(msg):
			print("Status:", msg)
		c.listen(on_reply)

		if c.connect():
			print("Connected to RobotA!")
			c.send("status")
		else:
			print("Could not find RobotA. Is it advertising?")
	"""

	def __init__(self, target="SPIKE", verbose=False):
		"""
		Create a Central.

		Args:
			target  : Name (or partial name) of the Peripheral hub to find.
					  Partial names work: "Hub" matches "HubA", "HubB", etc.
			verbose : Print debug info to the console. Default False.
					  Useful when testing — turn off for final code.
		"""
		self._target = target
		self._verbose = verbose
		self._unheard             = []   # messages that arrived before listen() was called
		self._callback            = None
		self._connect_callback    = None
		self._disconnect_callback = None
		self._reset()
		self._ble = _radio("Central:" + target, self._irq)
		if self._verbose:
			print("[spikecomm Central] Ready. Looking for target='{}'".format(target))

	def _reset(self):
		# Connection state only — callbacks registered by the student are kept.
		self._addr_type   = None
		self._addr        = None
		self._conn_handle = None
		self._tx_handle   = None    # notify handle (incoming messages)
		self._rx_handle   = None    # write handle  (outgoing messages)
		self._svc_range   = None
		self._mtu         = _DEFAULT_MTU
		self._searching   = False   # scanning for the target's name
		self._connecting  = False   # connecting + discovering services
		self._rx_pending  = b""
		self._early       = []      # (handle, data) notified before setup finished
		self._outbox      = []      # packets waiting to be written, oldest first
		self._writing     = False   # True while a write waits for its acknowledgement

	def _log(self, *args):
		if self._verbose:
			print("[spikecomm Central]", *args)

	def _irq(self, event, data):
		if event == _IRQ_SCAN_RESULT:
			if self._searching and self._addr is None:
				addr_type, addr, adv_type, rssi, adv_data = data
				if adv_type in (_ADV_IND, _ADV_DIRECT_IND):   # skip Beacons
					name = _extract_name(bytes(adv_data))
					if self._target in name:
						self._log('Found "{}" (RSSI={}) — connecting ...'.format(name, rssi))
						self._addr_type = addr_type
						self._addr = bytes(addr)

		elif event == _IRQ_PERIPHERAL_CONNECT:
			conn_handle, addr_type, addr = data
			if self._connecting and self._conn_handle is None:
				if conn_handle == 0xFFFF:   # how this firmware reports a cancelled attempt
					self._connecting = False
				elif bytes(addr) == self._addr:
					self._conn_handle = conn_handle
					self._log("Connected. Discovering services ...")
					self._ble.gattc_discover_services(conn_handle)

		elif event == _IRQ_PERIPHERAL_DISCONNECT:
			conn_handle, _, addr = data
			if self._conn_handle is None:
				if self._connecting and bytes(addr) == self._addr:
					self._log("Connection attempt failed.")
					self._connecting = False
			elif conn_handle == self._conn_handle:
				self._log("Disconnected.")
				self._reset()
				if self._disconnect_callback:
					_call("Central", self._disconnect_callback)

		elif event == _IRQ_GATTC_SERVICE_RESULT:
			conn_handle, start_handle, end_handle, uuid = data
			if conn_handle == self._conn_handle and uuid == _UART_SERVICE_UUID:
				self._svc_range = (start_handle, end_handle)

		elif event == _IRQ_GATTC_SERVICE_DONE:
			conn_handle, status = data
			if conn_handle == self._conn_handle and self._connecting:
				if self._svc_range:
					self._ble.gattc_discover_characteristics(conn_handle, *self._svc_range)
				else:
					self._log("Warning: no UART service found — is that hub running Peripheral?")
					self._connecting = False

		elif event == _IRQ_GATTC_CHARACTERISTIC_RESULT:
			conn_handle, end_handle, value_handle, properties, uuid = data
			if conn_handle == self._conn_handle:
				if uuid == _UART_TX_CHAR_UUID:
					self._tx_handle = value_handle
				elif uuid == _UART_RX_CHAR_UUID:
					self._rx_handle = value_handle

		elif event == _IRQ_GATTC_CHARACTERISTIC_DONE:
			conn_handle, status = data
			if conn_handle == self._conn_handle and self._connecting:
				self._connecting = False
				if self._tx_handle and self._rx_handle:
					# Note: no gattc_exchange_mtu() here — on SPIKE App 3 firmware it
					# has crashed the hub. Messages are split into 20-byte packets instead.
					self._log("Ready ✓ (TX handle={}, RX handle={})".format(
						self._tx_handle, self._rx_handle))
					if self._connect_callback:
						_call("Central", self._connect_callback)
					for value_handle, early in self._early:
						if value_handle == self._tx_handle:
							self._receive(early)
					self._early = []
				else:
					self._log("Warning: could not find TX/RX handles — send/receive won't work.")

		elif event == _IRQ_MTU_EXCHANGED:   # only if the Peripheral asks for it
			conn_handle, mtu = data
			if conn_handle == self._conn_handle:
				self._mtu = mtu
				self._pump()

		elif event == _IRQ_GATTC_WRITE_DONE:
			conn_handle, value_handle, status = data
			if conn_handle == self._conn_handle and self._writing:
				self._writing = False
				if self._outbox:
					self._outbox.pop(0)
				if status != 0:
					print("[spikecomm Central] Peripheral rejected a packet (status {})".format(status))
				self._pump()

		elif event == _IRQ_GATTC_NOTIFY:
			conn_handle, value_handle, notify_data = data
			if conn_handle == self._conn_handle:
				if self._connecting:
					# Arrived before setup finished (e.g. a welcome message sent
					# from the Peripheral's on_connect): keep it until ready.
					self._early.append((value_handle, bytes(notify_data)))
				elif value_handle == self._tx_handle:
					self._receive(bytes(notify_data))
				self._pump()   # also a chance to send anything a callback queued

	def _receive(self, data):
		messages, self._rx_pending = _unframe(self._rx_pending, data)
		for msg in messages:
			_deliver(self, "Central", msg)

	# ── Connection management ────────────────────────────────────────────────

	def connect(self, timeout=10000):
		"""
		Scan for and connect to the target Peripheral hub.
		Blocks until fully connected (including service discovery) or timeout.
		If an attempt fails or stalls, it scans and tries again until the
		timeout runs out. Start the Peripheral first, or give connect() a
		timeout long enough for the other hub to start.

		Args:
			timeout : Maximum total time in milliseconds. Default 10000 (10 s).

		Returns:
			True  if connected and ready to send/receive (or already connected).
			False if the hub was not found or connection timed out.

		Example:
			if c.connect(timeout=5000):
				c.send("hello!")
			else:
				print("Connection failed — is the other hub advertising?")
		"""
		if self.is_connected:
			return True
		start = time.ticks_ms()

		while True:
			self._reset()

			# Phase 1: scan for the target's name
			self._log('Scanning for "{}" (up to {}ms) ...'.format(
				self._target, timeout - time.ticks_diff(time.ticks_ms(), start)))
			self._searching = True
			_scan(True)
			try:
				while self._addr is None and time.ticks_diff(time.ticks_ms(), start) < timeout:
					time.sleep_ms(10)
			finally:
				self._searching = False
				_scan(False)

			if self._addr is None:
				self._log('"{}" not found. Is it advertising?'.format(self._target))
				return False

			# Phase 2: connect + service discovery (normally well under a second)
			self._connecting = True
			try:
				self._ble.gap_connect(self._addr_type, self._addr)
			except OSError:
				# An earlier attempt is still pending (e.g. the program was stopped
				# mid-connect). Cancel it and try again.
				self._log("Cancelling an earlier connection attempt ...")
				self._abandon()
				continue
			attempt = time.ticks_ms()
			while self._connecting \
					and time.ticks_diff(time.ticks_ms(), start) < timeout \
					and time.ticks_diff(time.ticks_ms(), attempt) < 4000:
				time.sleep_ms(10)

			if self.is_connected:
				return True
			self._abandon()
			if time.ticks_diff(time.ticks_ms(), start) >= timeout:
				self._log("Timed out while connecting.")
				return False
			self._log("Connection attempt failed — trying again ...")

	def _abandon(self):
		"""Drop the connection, or cancel a pending connection attempt (on this
		firmware an attempt never times out by itself). Connection state is
		forgotten first, so this doesn't trigger the on_disconnect callback."""
		conn_handle = self._conn_handle
		pending = self._connecting and conn_handle is None
		self._reset()
		try:
			if conn_handle is not None:
				self._ble.gap_disconnect(conn_handle)
			elif pending:
				self._ble.gap_connect(None)
			else:
				return
		except Exception:
			pass
		if not _in_event:
			time.sleep_ms(100)   # let the resulting event arrive before going on

	def disconnect(self):
		"""
		Disconnect from the Peripheral hub. Messages still being sent are
		delivered first (waits up to 2 s).
		(The on_disconnect callback is only for connections lost unexpectedly.)

		Example:
			c.disconnect()
		"""
		if self.is_connected and not _in_event:
			self._drain(2000)
			time.sleep_ms(100)   # let the last packets leave the radio
		self._log("Disconnecting ...")
		self._abandon()

	# ── Sending and receiving ────────────────────────────────────────────────

	def send(self, message):
		"""
		Send a message to the connected Peripheral hub.

		Args:
			message : A string (numbers are converted to text), up to 1000 chars;
					  must not contain "\\n" (that marks the end of a message).

		Returns:
			True if the message is on its way (messages are delivered in order).
			False if not connected or sending failed.

		If you send faster than the radio can deliver, send() waits a moment
		for it to catch up.

		Examples:
			c.send("start")
			c.send(motion_sensor.tilt_angles()[1])
			c.send(encode(x, y, heading))   # multiple values
		"""
		if not self.is_connected:
			self._log('send("{}") called but not connected — message dropped.'.format(
				_show(message)))
			return False
		chunks = _chunks(_frame(message), self._mtu - 3)
		if _in_event:
			# Inside a callback the radio can't make progress, so queue the packets.
			# Each acknowledged write starts the next one (see _pump).
			if self._outbox and len(self._outbox) + len(chunks) > _MAX_OUTBOX:
				print('[spikecomm Central] send queue full — "{}" dropped. Send less often.'.format(
					_show(message)))
				return False
			self._outbox.extend(chunks)
			self._pump()
		else:
			self._drain(2000)   # messages queued by a callback go first
			try:
				for chunk in chunks:
					_retry(self._ble.gattc_write, self._conn_handle, self._rx_handle, chunk, 0)
			except Exception as e:
				print("[spikecomm Central] send error:", e)
				return False
		self._log('Sent: "{}"'.format(_show(message)))
		return True

	def _drain(self, timeout):
		"""Wait (outside callbacks only) until packets queued by callbacks have been sent."""
		start = time.ticks_ms()
		while (self._outbox or self._writing) and self.is_connected \
				and time.ticks_diff(time.ticks_ms(), start) < timeout:
			self._pump()
			time.sleep_ms(2)

	def _pump(self):
		"""Write the next packet queued by a callback. One acknowledged write is in
		flight at a time; its acknowledgement (_IRQ_GATTC_WRITE_DONE) starts the next."""
		if self._writing or not self._outbox or self._conn_handle is None or self._rx_handle is None:
			return
		try:
			self._ble.gattc_write(self._conn_handle, self._rx_handle, self._outbox[0], 1)
			self._writing = True
		except OSError as e:
			if e.args[0] != errno.EALREADY:   # EALREADY = radio busy; retried on the next event
				print("[spikecomm Central] send error:", e)
				self._outbox.clear()

	def listen(self, callback):
		"""
		Register a function to call when a message arrives from the Peripheral.
		Can be called before connect(); stays registered across reconnects.
		Messages that arrived before listen() was called (up to 10) are
		passed to it right away.

		Args:
			callback : Function called as  callback(message: str)

		Example:
			def on_reply(msg):
				print("Peripheral says:", msg)
				values = decode(msg)   # if the message is encoded numbers
			c.listen(on_reply)
		"""
		_set_listener(self, "Central", callback)

	def wait_for(self, condition, timeout=None):
		"""
		Block until a received message meets `condition`, then return it.
		Returns None right away if not connected, or as soon as the
		connection is lost.

		Can be used alongside an active listen() — both callbacks fire.

		Args:
			condition : What to wait for. Two forms:
						  · A string   — waits until the message equals it exactly.
							e.g. wait_for("go")
						  · A function — waits until condition(message) returns True.
							e.g. wait_for(lambda msg: int(msg) > 100)
							If the function raises an error, that message
							counts as "no match".
			timeout   : Max time to wait in milliseconds.
						Default None = wait forever.
						Returns None if the timeout expires before a match.

		Returns:
			The message string that triggered the match, or None on timeout.

		Examples:
			# Wait until the Peripheral sends exactly "start"
			c.wait_for("start")
			motor.run(port.A, 500)

			# Wait for a sensor reading below a threshold
			msg = c.wait_for(lambda m: decode(m)[0] < 50)
			print("Nearby! Distance:", decode(msg)[0])

			# Wait for either of two messages
			msg = c.wait_for(lambda m: m in ("go", "ready"))

			# Wait at most 5 seconds, then handle the miss
			msg = c.wait_for("green_light", timeout=5000)
			if msg is None:
				print("Light never turned green — stopping")
			else:
				motor.run(port.A, 500)
		"""
		if not self.is_connected:
			self._log("wait_for: not connected — returning None immediately.")
			return None
		return _wait_for(self, "Central", condition, timeout, False,
						 lambda: not self.is_connected)

	def on_connect(self, callback):
		"""
		Register a function to call once the connection is fully established.

		Args:
			callback : Function called as  callback()  (no arguments)

		Example:
			c.on_connect(lambda: print("Connected!"))
		"""
		self._connect_callback = callback

	def on_disconnect(self, callback):
		"""
		Register a function to call when the connection is lost.
		Don't call connect() inside it — set a flag and reconnect from your
		main loop instead (see is_connected).

		Args:
			callback : Function called as  callback()  (no arguments)

		Example:
			c.on_disconnect(lambda: print("Lost connection!"))
		"""
		self._disconnect_callback = callback

	# ── Status ───────────────────────────────────────────────────────────────

	@property
	def is_connected(self):
		"""True if connected and service discovery is complete (ready to send)."""
		return (
			self._conn_handle is not None
			and self._tx_handle is not None
			and self._rx_handle is not None
			and not self._connecting
		)
