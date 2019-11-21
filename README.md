# weasleyclockd

Python daemon listening for MQTT updates and controlling the motion of a Weasley Clock.

This is part of my larger project to create a fully working [Weasley
Clock](https://github.com/randomstring/WeasleyClock) like in Harry Potter.

## Weasley Clock Daemon

This daemon runs on a raspberry pi, subscribes to MQTT messages on the
topic **weaseleyclock/#**, and updates the hand positions of the
Weasley Clock. Hand position is controlled using [HS-785HB
servos](https://www.servocity.com/hs-785hb-servo) controlled by a
[Servo Hat](https://www.adafruit.com/product/2327).

## Server Hat

Follow these instructions to setup your servo HAT and install the
necessary
software. https://learn.adafruit.com/adafruit-16-channel-pwm-servo-hat-for-raspberry-pi

## Utilities

I wrote a python program to control HS-785HB servos with the Servo
HAT. [hs785hb_servo.py](https://github.com/randomstring/weasleyclockd/blob/master/hs785hb_servo.py) This
was useful for calibrating the servos and mapping the pulse range for
the servos to the servo's physical range.
