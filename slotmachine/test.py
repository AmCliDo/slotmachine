from gpiozero import LED
from time import sleep

# LED hängt an GPIO22 (Pin 15)
led = LED(22)

while True:
    led.on()      # LED an
    sleep(1)
    led.off()     # LED aus
    sleep(1)
