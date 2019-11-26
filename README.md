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

Updates for hand positions are received via MQTT messages. I use Home
Assistant to determine the location of each person and update the
state. Home Assistant sends a MQTT message on the **weasleyclock**
topic for each person. The **weasleyclockd** sends a update request
message when it connects to Home Assistant using a
**weasleyclock/UPDATE** request.

## Hand Position

I have three different ways of positioning the hand withing the
designated sector on the clock face. For states that have a variable
distance component like **Lost** or **In Transit** I use a log scale
to pick where within the sector. As the person move closer to **Home**
their clock hand moves ever so slightly closer to the **Home** sector
on the clock face.

For sectors that have a fixed distance from **Home** like **School**
or **Work**, I divide the sector into four sub-positions, one for each
hand. So that even if the whole family is at **School* all the hands
won't be stacked up on top of each other. This makes them more
readable.

The last way is to just place the hand in the middle of the
sector. This method is not currently used, I wrote this one first for
testing.

## Installation

The daemon is started on boot by systemd service.

```bash
pip3 install -r requirements.txt
mkdir /home/pi/weasleyclockd/
cp weasleyclockd.py weasleyclockd.json /home/pi/weasleyclockd/
sudo cp weasleyclockd.service /lib/systemd/system/
sudo chmod 644 /lib/systemd/system/weasleyclockd.service
sudo systemctl daemon-reload
sudo systemctl enable weasleyclockd.service
sudo systemctl start weasleyclockd.service
tail -f /home/pi/weasleyclockd/weasleyclock.log
```

## Server Hat

Follow these instructions to setup your servo HAT and install the
necessary
software. https://learn.adafruit.com/adafruit-16-channel-pwm-servo-hat-for-raspberry-pi

## Utilities

I wrote a python program to control HS-785HB servos with the Servo
HAT. [hs785hb_servo.py](https://github.com/randomstring/weasleyclockd/blob/master/hs785hb_servo.py) This
was useful for calibrating the servos and mapping the pulse range for
the servos to the servo's physical range.
