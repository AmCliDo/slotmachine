#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import threading
import time
import random
from pathlib import Path
from flask import Flask, jsonify, render_template

try:
    from gpiozero import Button
    GPIO_AVAILABLE = True
except Exception:
    GPIO_AVAILABLE = False

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "slot_state.json"
BTN_ADD_PIN = 17
BTN_PLAY_PIN = 27
BOUNCE_SECS = 0.2

state_lock = threading.Lock()
state = {"balance": 0, "last_spin": [0,0,0], "win": False, "last_event": "System start"}

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
                    "last_event": loaded.get("last_event", "Restored from disk")
                })
        except Exception:
            pass

def add_credit(source="button"):
    with state_lock:
        state["balance"] += 1
        state["last_event"] = f"{time.strftime('%H:%M:%S')} – Guthaben +1 ({source})"
        save_state()

def play_once(source="button"):
    with state_lock:
        if state["balance"] < 1:
            state["last_event"] = f"{time.strftime('%H:%M:%S')} – Nicht genug Guthaben zum Spielen"
            save_state()
            return state["last_spin"], state["balance"], False

        state["balance"] -= 1
        a, b, c = (random.randint(1, 9) for _ in range(3))
        state["last_spin"] = [a, b, c]
        win = (a == b == c)
        if win:
            state["balance"] *= 2
        state["win"] = win
        evt = "GEWINN! Guthaben verdoppelt" if win else "kein Gewinn"
        state["last_event"] = f"{time.strftime('%H:%M:%S')} – Spin {a}-{b}-{c}, {evt} ({source})"
        save_state()
        return [a, b, c], state["balance"], win

btn_add = None
btn_play = None

def setup_gpio():
    global btn_add, btn_play
    if not GPIO_AVAILABLE:
        return
    try:
        btn_add = Button(BTN_ADD_PIN, pull_up=True, bounce_time=BOUNCE_SECS)
        btn_play = Button(BTN_PLAY_PIN, pull_up=True, bounce_time=BOUNCE_SECS)
        btn_add.when_pressed = lambda: add_credit(source="GPIO")
        btn_play.when_pressed = lambda: play_once(source="GPIO")
    except Exception as e:
        print("GPIO-Setup fehlgeschlagen:", e)

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
