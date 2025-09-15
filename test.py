from gpiozero import LED
from time import sleep

# LED hängt an GPIO23 (Pin 16)
led = LED(23)

print("Die LED an GPIO23 (Pin 16) blinkt nun im Sekundentakt.")

while True:
    led.on()
    sleep(1)
    led.off()
    sleep(1)
