#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, threading, time, random
from pathlib import Path
from flask import Flask, jsonify, render_template
import RPi.GPIO as GPIO

# ---- Konfiguration / Pins ----
BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "slot_state.json"

BTN_PLAY_PIN = 17   # GPIO17 (Pin 11)
BTN_ADD_PIN = 27    # GPIO27 (Pin 13)
LED_GREEN_PIN = 22  # GPIO22 (Pin 15)
LED_RED_PIN = 23    # GPIO23 (Pin 16)
BUZZER_PIN = 18     # GPIO18 (Pin 12)
BOUNCE_SECS = 0.1

COST_PER_PLAY = 5
WIN_PROBABILITY = 0.2

# ---- Zustand ----
state_lock = threading.Lock()
state = {
    "balance": 0,
    "last_spin": [0, 0, 0],
    "win": False,
    "last_event": "System start",
    "spinning": False
}

# ---- Geräte ----
buzzer = None

# ---- Helper-Funktionen ----
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

def blink_leds_alternating(pin1, pin2, times=5, interval=0.2):
    for _ in range(times):
        GPIO.output(pin1, GPIO.HIGH)
        GPIO.output(pin2, GPIO.LOW)
        time.sleep(interval)
        GPIO.output(pin1, GPIO.LOW)
        GPIO.output(pin2, GPIO.HIGH)
        time.sleep(interval)
    GPIO.output(pin1, GPIO.LOW)
    GPIO.output(pin2, GPIO.LOW)

# ---- Buzzer-Musik ----
def play_win_tone():
    if not buzzer:
        return
    NOTES = {
        'REST': 0, 'C5': 523, 'E5': 659, 'G5': 784, 'C6': 1047
    }
    melody = [
        ('C5', 8), ('E5', 8), ('G5', 8), ('C6', 4),
        ('REST', 8),
        ('G5', 8), ('C6', 4)
    ]
    tempo = 200
    wholenote = (60000 * 4) / tempo
    for note, duration_fraction in melody:
        duration_ms = wholenote / abs(duration_fraction)
        if duration_fraction < 0:
            duration_ms *= 1.5
        frequency = NOTES.get(note, 0)
        if frequency == 0:
            time.sleep(duration_ms / 1000)
        else:
            buzzer.ChangeFrequency(frequency)
            buzzer.ChangeDutyCycle(20)
            time.sleep(duration_ms * 0.9 / 1000)
            buzzer.ChangeDutyCycle(0)
            time.sleep(duration_ms * 0.1 / 1000)

def play_lose_tone():
    if not buzzer:
        return
    buzzer.ChangeFrequency(200)
    buzzer.ChangeDutyCycle(10)
    time.sleep(0.3)
    buzzer.ChangeDutyCycle(0)

# ---- Spielmechanik ----
def add_credit(source="button"):
    with state_lock:
        state["balance"] += 1
        state["last_event"] = f"{time.strftime('%H:%M:%S')} – Guthaben +1 ({source})"
        save_state()

def try_play():
    with state_lock:
        if state["spinning"]:
            return
    play_once(source="GPIO")

def play_once(source="button"):
    with state_lock:
        if state["spinning"]:
            return state["last_spin"], state["balance"], False
        if state["balance"] < COST_PER_PLAY:
            state["last_event"] = f"{time.strftime('%H:%M:%S')} – Nicht genug Guthaben zum Spielen"
            save_state()
            return state["last_spin"], state["balance"], False
        state["spinning"] = True
        save_state()

    blink_leds_alternating(LED_GREEN_PIN, LED_RED_PIN, times=5, interval=0.2)
    time.sleep(0.5)

    with state_lock:
        state["balance"] -= COST_PER_PLAY
        if random.random() < WIN_PROBABILITY:
            a = b = c = random.randint(1, 9)
            win = True
        else:
            while True:
                a, b, c = (random.randint(1, 9) for _ in range(3))
                if not (a == b == c):
                    break
            win = False
        if win:
            state["balance"] *= 2
        state["last_spin"] = [a, b, c]
        state["win"] = win
        evt = "GEWINN! Guthaben verdoppelt" if win else "kein Gewinn"
        state["last_event"] = f"{time.strftime('%H:%M:%S')} – Spin {a}-{b}-{c}, {evt} ({source})"
        state["spinning"] = False
        save_state()
        last_spin = state["last_spin"]
        balance = state["balance"]

    GPIO.output(LED_GREEN_PIN, GPIO.LOW)
    GPIO.output(LED_RED_PIN, GPIO.LOW)
    GPIO.output(LED_GREEN_PIN if win else LED_RED_PIN, GPIO.HIGH)

    if win:
        play_win_tone()
    else:
        play_lose_tone()

    return last_spin, balance, win

# ---- GPIO Setup ----
def setup_gpio():
    global buzzer
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(BTN_ADD_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(BTN_PLAY_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(LED_GREEN_PIN, GPIO.OUT)
    GPIO.setup(LED_RED_PIN, GPIO.OUT)
    GPIO.output(LED_GREEN_PIN, GPIO.LOW)
    GPIO.output(LED_RED_PIN, GPIO.LOW)
    GPIO.setup(BUZZER_PIN, GPIO.OUT)
    buzzer_pwm = GPIO.PWM(BUZZER_PIN, 440)
    buzzer_pwm.start(0)
    buzzer = buzzer_pwm
    GPIO.add_event_detect(BTN_ADD_PIN, GPIO.FALLING, callback=lambda x: add_credit("GPIO"), bouncetime=int(BOUNCE_SECS * 1000))
    GPIO.add_event_detect(BTN_PLAY_PIN, GPIO.FALLING, callback=lambda x: try_play(), bouncetime=int(BOUNCE_SECS * 1000))

# ---- Flask ----
app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html", cost_per_play=COST_PER_PLAY)

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

@app.route("/test/buzzer")
def test_buzzer():
    if buzzer:
        buzzer.ChangeFrequency(440)
        buzzer.ChangeDutyCycle(20)
        time.sleep(0.5)
        buzzer.ChangeDutyCycle(0)
        return "Buzzer getestet (0.5s Ton)"
    else:
        return "Buzzer nicht verfügbar"

if __name__ == "__main__":
    load_state()
    setup_gpio()
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
