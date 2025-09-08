#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, threading, time, random
from pathlib import Path
from flask import Flask, jsonify, render_template

# ---- GPIO ----
try:
    from gpiozero import Button, LED, Buzzer
    GPIO_AVAILABLE = True
except Exception:
    GPIO_AVAILABLE = False

# ---- Konfiguration / Pins ----
BASE_DIR   = Path(__file__).resolve().parent
DATA_FILE  = BASE_DIR / "slot_state.json"

BTN_ADD_PIN   = 17   # GPIO17 (Pin 11)
BTN_PLAY_PIN  = 27   # GPIO27 (Pin 13)
BOUNCE_SECS   = 0.05

LED_GREEN_PIN = 22   # GPIO22 (Pin 15)
LED_RED_PIN   = 23   # GPIO23 (Pin 16)
BUZZER_PIN    = 18   # GPIO18 (Pin 12)

# ---- Zustand ----
state_lock = threading.Lock()
state = {
    "balance": 0,
    "last_spin": [0, 0, 0],
    "win": False,
    "last_event": "System start",
    "spinning": False
}

# ---- Funktionen für State ----
def save_state():
    try:
        DATA_FILE.write_text(json.dumps(state), encoding="utf-8")
    except Exception:
        pass

def load_state():
    if DATA_FILE.exists():
        try:
            loaded = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            with state_lock:
                state.update({
                    "balance": int(loaded.get("balance", 0)),
                    "last_spin": list(loaded.get("last_spin", [0, 0, 0])),
                    "win": bool(loaded.get("win", False)),
                    "last_event": loaded.get("last_event", "Restored from disk"),
                    "spinning": False
                })
        except Exception:
            pass

# ---- Spiellogik ----
def add_credit(source="button"):
    with state_lock:
        state["balance"] += 1
        state["last_event"] = f"{time.strftime('%H:%M:%S')} – Guthaben +1 ({source})"
        save_state()

def play_win_tone():
    if not buzzer:
        return
    for _ in range(3):     # dreimal kurz piepen
        buzzer.on()
        time.sleep(0.12)
        buzzer.off()
        time.sleep(0.08)

def play_lose_tone():
    if not buzzer:
        return
    buzzer.on()
    time.sleep(0.25)       # längerer Piepton
    buzzer.off()

def play_once(source="button"):
    # 1) Guthaben prüfen + „Drehphase“ markieren
    with state_lock:
        if state["balance"] < 1:
            state["last_event"] = f"{time.strftime('%H:%M:%S')} – Nicht genug Guthaben zum Spielen"
            save_state()
            return state["last_spin"], state["balance"], False
        state["spinning"] = True
        save_state()

    # 2) Startfeedback: LEDs 2 s blinken (außerhalb des Locks!)
    if led_green and led_red:
        led_green.blink(on_time=0.2, off_time=0.2, background=True)
        led_red.blink(on_time=0.2, off_time=0.2, background=True)

    time.sleep(2.0)  # sichtbare „Drehzeit“ für Web-Animation

    # 3) Ergebnis berechnen & Zustand speichern
    with state_lock:
        state["balance"] -= 1
        a, b, c = (random.randint(1, 9) for _ in range(3))
        win = (a == b == c)
        if win:
            state["balance"] *= 2

        state["last_spin"] = [a, b, c]
        state["win"] = win
        evt = "GEWINN! Guthaben verdoppelt" if win else "kein Gewinn"
        state["last_event"] = f"{time.strftime('%H:%M:%S')} – Spin {a}-{b}-{c}, {evt} ({source})"
        state["spinning"] = False
        save_state()

        last_spin = state["last_spin"]
        balance   = state["balance"]

    # 4) LEDs final setzen (außerhalb des Locks)
    if led_green and led_red:
        led_green.off(); led_red.off()
        if win:
            led_green.on()
        else:
            led_red.on()

    # 5) Sound abspielen (Buzzer)
    if win:
        play_win_tone()
    else:
        play_lose_tone()

    return last_spin, balance, win

# ---- GPIO Setup ----
btn_add = btn_play = None
led_green = led_red = None
buzzer = None

def setup_gpio():
    global btn_add, btn_play, led_green, led_red, buzzer
    if not GPIO_AVAILABLE:
        print("GPIO nicht verfügbar – laufe ohne Taster/LEDs/Buzzer.")
        return
    try:
        btn_add  = Button(BTN_ADD_PIN,  pull_up=True, bounce_time=BOUNCE_SECS)
        btn_play = Button(BTN_PLAY_PIN, pull_up=True, bounce_time=BOUNCE_SECS)
        led_green = LED(LED_GREEN_PIN)
        led_red   = LED(LED_RED_PIN)
        buzzer    = Buzzer(BUZZER_PIN)
        led_green.off(); led_red.off(); buzzer.off()

        btn_add.when_pressed  = lambda: add_credit(source="GPIO")
        btn_play.when_pressed = lambda: play_once(source="GPIO")
    except Exception as e:
        print("GPIO-Setup fehlgeschlagen:", e)

# ---- Flask ----
app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/state")
def get_state():
    with state_lock:
        return jsonify(state)

@app.route("/add", methods=["POST"])
def api_add():
    add_credit(source="web")
    with state_lock:
        return jsonify(state)

@app.route("/play", methods=["POST"])
def api_play():
    play_once(source="web")
    with state_lock:
        return jsonify(state)

if __name__ == "__main__":
    load_state()
    setup_gpio()
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
