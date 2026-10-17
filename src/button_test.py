#!/usr/bin/env python3
"""Check the arcade buttons on the Pi: prints every press/release. Ctrl+C to quit.

Run with the system python (not uv/.venv):  /usr/bin/python3 src/button_test.py
Stop the game first (sudo systemctl stop qlik-or-treat), it holds the pins.
"""
import os
import signal

from gpiozero import Button

PINS = {"LEFT": int(os.environ.get("PIN_LEFT", 17)),
        "FIRE": int(os.environ.get("PIN_FIRE", 27)),
        "RIGHT": int(os.environ.get("PIN_RIGHT", 22))}

buttons = []
for name, pin in PINS.items():
    b = Button(pin, pull_up=True, bounce_time=0.01)
    b.when_pressed = lambda n=name, p=pin: print("%-5s (GPIO%d) pressed" % (n, p), flush=True)
    b.when_released = lambda n=name, p=pin: print("%-5s (GPIO%d) released" % (n, p), flush=True)
    print("%-5s GPIO%-2d now %s" % (name, pin, "PRESSED (stuck? check wiring)" if b.is_pressed else "up"))
    buttons.append(b)
print("pin factory:", buttons[0].pin_factory.__class__.__name__)
print("Press the buttons... (Ctrl+C to quit)")
signal.pause()
