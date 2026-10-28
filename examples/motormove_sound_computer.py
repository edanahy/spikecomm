# ===== Computer — play a sound when the hub's motor turns =====
# This runs on a computer with ordinary Python 3, not on a hub. It listens for
# the broadcast from motormove_sound_hub.py and plays a sound file each time
# the hub's motor has turned 20 degrees or more since the sound last played.
#
# Setup (once):
#   pip install bleak          (bleak is a Bluetooth library for computers)
# Run:
#   python3 motormove_sound_computer.py          (Ctrl-C to stop)
#   The first time, macOS asks whether the app you run it from (Terminal,
#   VS Code, ...) may use Bluetooth: click Allow. If you clicked Don't Allow,
#   turn it on in System Settings > Privacy & Security > Bluetooth.
#
# How quickly: a Mac passes on the hub's broadcast only about twice a second,
# sometimes with a gap of a second or two, so the sound can come a second or so
# after the motor turns. (Another hub's Scanner hears it 10 times a second.)
#
# The sound is sound.mp3, in the same folder as this program. To use
# your own, put the file next to this program and change SOUND_FILE.
# Playing a sound works differently on each operating system, and this program
# does it the macOS way. On Windows, change play_sound() (see the note there).
import asyncio
import subprocess
import sys
import time
from pathlib import Path

from bleak import BleakScanner

PREFIX = "!M"                       # must match the hub's Beacon("!M")
DEGREES = 20                        # play the sound once the motor has turned this far
SOUND_FILE = "sound.mp3"            # on a Mac, .mp3, .wav, .m4a and .aiff all work

SOUND = Path(__file__).resolve().parent / SOUND_FILE     # next to this program


def play_sound():
    """Start playing SOUND and return at once, so the program keeps listening.

    macOS: `afplay` comes with every Mac. This returns the running player,
    so the main loop can tell when the sound has finished.

    WINDOWS: there's no afplay. Replace the `return` line with these two:
        import winsound
        winsound.PlaySound(str(SOUND), winsound.SND_FILENAME | winsound.SND_ASYNC)
    winsound comes with Python on Windows but plays only .wav files (so set
    SOUND_FILE to a .wav), and a new sound cuts off one that is still playing.
    """
    return subprocess.Popen(["afplay", str(SOUND)])


def decode(text, sep=";"):
    """Split a broadcast into values, like spikecomm's decode: "-725;ok" -> [-725, "ok"]."""
    values = []
    for token in text.split(sep):
        token = token.strip()
        try:
            values.append(int(token))
        except ValueError:
            try:
                values.append(float(token))
            except ValueError:
                values.append(token)
    return values


latest = {"degrees": None, "time": 0}


def on_advertisement(device, adv):
    # bleak calls this for every Bluetooth broadcast the computer hears.
    # Use adv.local_name (the name in this broadcast), not device.name: macOS
    # may show a hub by the name it had when the computer last connected to it.
    name = adv.local_name
    if name and name.startswith(PREFIX):
        values = decode(name[len(PREFIX):])
        if len(values) == 1 and isinstance(values[0], int):     # "!M-725" -> [-725]
            latest["degrees"] = values[0]
            latest["time"] = time.monotonic()


async def main():
    async with BleakScanner(on_advertisement):
        print("Listening for the hub's", PREFIX, "broadcast ... (Ctrl-C to stop)")
        start = None        # motor position when the sound last played
        player = None       # the sound that is playing, if any
        heard = False
        while True:
            await asyncio.sleep(0.05)       # bleak calls on_advertisement while this waits
            degrees = latest["degrees"]
            # macOS can go 2 seconds or more without passing on the hub's
            # broadcast, so wait 5 seconds before deciding the hub has gone.
            now_heard = degrees is not None and time.monotonic() - latest["time"] < 5
            if now_heard != heard:
                if now_heard:
                    print("Hub found: motor at", degrees, "degrees")
                else:
                    print("No signal from the hub")
                heard = now_heard
            if not heard:
                continue
            if start is None:
                start = degrees             # first reading: nothing to compare with yet
            turned = degrees - start
            # Play once the motor has turned far enough, either way, and the
            # last sound has finished (poll() is None while it's still playing)
            if abs(turned) >= DEGREES and (player is None or player.poll() is not None):
                print("Motor turned", turned, "degrees, now at", degrees, ": playing the sound")
                start = degrees
                player = play_sound()


if not SOUND.exists():
    sys.exit("Can't find the sound file " + str(SOUND))
try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("Stopped")
