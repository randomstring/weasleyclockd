#!/usr/bin/env python
#
# Test script for controlling a set of HiTec HS-785HB Servos.
#
# See:
# https://learn.adafruit.com/adafruit-16-channel-pwm-servo-hat-for-raspberry-pi/overview
#

import sys
import getopt
from adafruit_servokit import ServoKit
from time import sleep

# HiTec HS-785HB Servo
# https://www.servocity.com/hs-785hb-servo
# set_puse_range(685, 2070)
# actuation_range = 2160 (6 * 360)
# gets 6 full rotations, rated for up to 8 full rotations

def main(argv):
    kit = ServoKit(channels=16)

    servos = []
    angle = 0

    # defaults for hs-785hb-servo
    pw_min = 685
    pw_max = 2070
    actuation_range = 2160   #  6 full rotations

    try:
        opts, args = getopt.getopt(argv,"hs:a:m:M:r:",["servos=","angle=","min=","max=","range="])
    except getopt.GetoptError:
        print('test_servohat.py -s <servos_list> -a <angle> -m <min_pw> -M <max_pw> -r <actuator_range>')
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            print('test_servohat.py -s <servo> -a <angle> -m <min_pw> -M <max_pw> -r <actuator_range>')
            print('  -s <servos>  comma seperated servo list of id numbers (0-15) on the servo hat')
            print('  -a <angle>   angle to drive servo to')
            print('  -m <min_pw>  minimum pulse width in microseconds (default ', pw_min, ')')
            print('  -M <max_pw>  minimum pulse width in microseconds (default ', pw_max, ')')
            print('  -r <range>   range of motion in degrees (default ', actuation_range, ')')
            sys.exit()
        elif opt in ("-s", "--servo"):
            servos = [ int(a) for a in arg.split(',') ]
        elif opt in ("-a", "--angle"):
            angle = int(arg)
        elif opt in ("-m", "--min"):
            pw_min = int(arg)
        elif opt in ("-M", "--max"):
            pw_max = int(arg)
        elif opt in ("-r", "--range"):
            actuation_range = int(arg)

    print('Servos: ', servos)
    print('Angle: ', angle)

    for servo in servos:
        print('servo: ', servo, ' to agle: ', angle, ' range: ', actuation_range)
        kit.servo[servo].actuation_range = actuation_range
        kit.servo[servo].set_pulse_width_range(pw_min, pw_max)
        kit.servo[servo].angle = angle

if __name__ == "__main__":
    main(sys.argv[1:])
