#!/usr/bin/env python3
import sys
import os
import time
import argparse
import logging
import daemon
import json
import paho.mqtt.client as mqtt
import lockfile
import numpy as np
from geopy.distance import great_circle
from adafruit_servokit import ServoKit

debug_p = False

#
# Configuration of the Clock face
#   name:    pretty name
#   angle:   starting angle of the clock sector (degrees)
#   theta:   width of clock sector in degrees
#   offset_style:   type of sub-sector hand placement
#
# Angles are measured counter clockwise (CCW) starting at the top of
# the clock face. The servo measures angles CCW.
states = {
    'home': {
        'name': 'Home',
        'angle': 337.5,
        'theta': 22.5,
        'offset_style': 'home'
        },
    'barn': {
        'name': 'Barn',
        'angle': 315,
        'theta': 22.5,
        'offset_style': 'home'
        },
    'mortalperil': {
        'name': 'Mortal Peril',
        'angle': 270,
        'theta': 45,
        'offset_style': 'distance'
        },
    'quidditch': {
        'name': 'Quidditch',
        'angle': 225,
        'theta': 45,
        'offset_style': 'distance'
        },
    'work': {
        'name': 'Work',
        'angle': 180,
        'theta': 45,
        'offset_style': 'hand'
        },
    'school': {
        'name': 'School',
        'angle': 135,
        'theta': 45,
        'offset_style': 'hand'
        },
    'garden': {
        'name': 'Garden',
        'angle': 90,
        'theta': 45,
        'offset_style': 'hand'
        },
    'intransit': {
        'name': 'In Transit',
        'angle': 45,
        'theta': 45,
        'offset_style': 'distance'
        },
    'lost': {
        'name': 'Lost',
        'angle': 0,
        'theta': 45,
        'offset_style': 'distance'
        },
    'error': {
        'name': 'Error',
        'angle': 0,
        'theta': 0,
        'offset_style': 'hand'
        },
    }


# calculate where in the sector to point the clock hands
def angle_offset(angle, theta, distance, hand, style):
    if style == 'distance':
        # this formula creates a log scale of distance in the range [0.0,1.0]
        # (ln(distance + 1.1) - ln(1.1))/ln(10000)
        scale = (np.log(distance + 1.1) - np.log(1.1))/np.log(10000)
        if scale < 0.0:
            scale = 0.0
        elif scale > 1.0:
            scale = 1.0
        if angle < 180:
            # left side of clock face
            return scale * theta
        else:
            return theta - (scale * theta)
    elif style == 'hand':
        # each hand 0-3 has it's own small offset
        scale = 0.8 * (float(hand) / 3.0) + 0.1
        return scale * theta
    # middle of the sector
    return (theta / 2.0)


# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    client.subscribe(userdata['topic'])
    client.publish('weasleyclock/UPDATE', payload='{"update":"true"}', qos=0, retain=False)
    if rc != 0:
        userdata['logger'].warning("subscibing to topic [" +
                                   userdata['topic'] +
                                   "] result code " + str(rc))
    else:
        userdata['logger'].debug("subscibing to topic [" +
                                 userdata['topic'] +
                                 "] result code " + str(rc))


# Callback for MQTT messages
def on_message(client, userdata, message):
    # wrap the on_message() processing in a try:
    try:
        _on_message(client, userdata, message)
    except Exception as e:
        userdata['logger'].error("on_message() failed: {}".format(e))


def _on_message(client, userdata, message):
    topic = message.topic
    m_decode = str(message.payload.decode("utf-8", "ignore"))
    if debug_p:
        print("Received message '" + m_decode +
              "' on topic '" + topic +
              "' with QoS " + str(message.qos))

    log_snippet = (m_decode[:15] + '..') if len(m_decode) > 17 else m_decode
    log_snippet = log_snippet.replace('\n', ' ')

    (prefix, name) = topic.split('/', 1)

    if name == "UPDATE":
        # this is an update request, ignore
        return

    userdata['logger'].debug("Received message '" +
                             log_snippet +
                             "' on topic '" + topic +
                             "' with QoS " + str(message.qos))

    try:
        msg_data = json.loads(m_decode)
    except ValueError as parse_error:
        # python <=3.4.* use ValueError
        if debug_p:
            print("JSON decode failed: " + str(parse_error))
        userdata['logger'].error("JSON decode failed.")
        return

    # python >3.5 use:  except json.JSONDecodeError as parse_error:
    # print("JSON decode failed. [" + parse_error.msg + "]")
    # print("error at pos: " + parse_error.pos +
    #      " line: " + parse_error.lineno)

    move_clock_hands(name, msg_data, userdata)


def move_clock_hands(name, message, userdata):
    config_data = userdata['config_data']
    state = None
    latitude = None
    longitude = None
    distance = 0.0
    if 'state' in message:
        state = message['state']
    if 'latitude' in message:
        latitude = float(message['latitude'])
    if 'longitude' in message:
        longitude = float(message['longitude'])

    distance = 0.0
    if latitude and longitude:
        latitude_home = float(config_data['latitude'])
        longitude_home = float(config_data['longitude'])
        distance = great_circle((latitude_home, longitude_home),
                                (latitude, longitude)).miles

    if debug_p:
        print("Move " + name + " hand to " + state +
              " ({0:.1f} miles away)".format(distance))

    if name not in config_data['hand']:
        if debug_p:
            print("Person " + name + " is not tracked by a clock hand")
        return
    hand = config_data['hand'][name]

    if hand not in config_data['channel']:
        userdata['logger'].error("Hand " + hand +
                                 " does not have a specified PWM channel")
        return
    channel = config_data['channel'][hand]

    if state not in states:
        userdata['logger'].error("Unknown target state [" + state + "]")
        return

    target_state = states[state]
    base_angle = float(target_state['angle'])
    theta = float(target_state['theta'])
    style = target_state['offset_style']

    offset = angle_offset(base_angle, theta, distance, hand, style)
    servo_angle = int(2 * (base_angle + offset))
    userdata['kit'].servo[channel].angle = servo_angle

    userdata['logger'].info("Move [" + name +
                            "] hand to [" + state +
                            "] ({0:.1f} miles away)".format(distance))

    if debug_p:
        print("base_angle [" + str(base_angle) + "] theta [" + str(theta) +
              "] style [" + style + "]")
        print("distance [", distance, "]  offset [", offset, "]")
        print("servo angle: ", servo_angle)


def do_something(logf, configf):

    #
    # setup logging
    #
    logger = logging.getLogger('weasleyclock')
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(logf)
    fh.setLevel(logging.INFO)
    formatstr = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    formatter = logging.Formatter(formatstr)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # read config file
    with open(configf) as json_data_file:
        config_data = json.load(json_data_file)

    # connect to MQTT server
    host = config_data['mqtt_host']
    port = config_data['mqtt_port'] if 'mqtt_port' in config_data else 4884
    topic = config_data['mqtt_topic'] if 'mqtt_topic' in config_data else 'weasleyclock/#'

    logger.info("connecting to host " + host + ":" + str(port) +
                " topic " + topic)

    if debug_p:
        print("connecting to host " + host + ":" + str(port) +
              " topic " + topic)

    # configure servos and zero clock hands
    kit = ServoKit(channels=16)
    pulsewidth_min = 685
    pulsewidth_max = 2070
    actuation_range = 2160
    if 'pulsewidth_min' in config_data:
        pulsewidth_min = int(config_data['pulsewidth_min'])
    if 'pulsewidth_max' in config_data:
        pulsewidth_max = int(config_data['pulsewidth_max'])
    if 'actuation_range' in config_data:
        actuation_range = int(config_data['actuation_range'])

    for (hand, servo) in config_data['channel'].items():
        kit.servo[servo].actuation_range = actuation_range
        kit.servo[servo].set_pulse_width_range(pulsewidth_min, pulsewidth_max)
        # kit.servo[servo].angle = 0

    clockdata = {
        'logger': logger,
        'host': host,
        'port': port,
        'topic': topic,
        'kit': kit,
        'config_data': config_data,
        }

    # how to mqtt in python see https://pypi.org/project/paho-mqtt/
    mqttc = mqtt.Client(client_id='weasleyclockd',
                        clean_session=True,
                        userdata=clockdata)

    mqttc.username_pw_set(config_data['mqtt_user'],
                          config_data['mqtt_password'])

    # create callbacks
    mqttc.on_connect = on_connect
    mqttc.on_message = on_message


    # if port == 4884:
    #     mqtt_client.tls_set(ca_certs=TLS_CERT_PATH, certfile=None,
    #                    keyfile=None, cert_reqs=ssl.CERT_REQUIRED,
    #                    tls_version=ssl.PROTOCOL_TLSv1_2, ciphers=None)
    #     mqtt_client.tls_insecure_set(False)

    mqttc.connect(host, port, 60)
    mqttc.loop_forever()


def start_daemon(pidf, logf, wdir, configf, nodaemon):
    global debug_p

    if nodaemon:
        # non-daemon mode, for debugging.
        print("Non-Daemon mode.")
        do_something(logf, configf)
    else:
        # daemon mode
        if debug_p:
            print("weasleyclock: entered run()")
            print("weasleyclock: pidf = {}    logf = {}".format(pidf, logf))
            print("weasleyclock: about to start daemonization")

        with daemon.DaemonContext(working_directory=wdir,
                                  umask=0o002,
                                  pidfile=lockfile.FileLock(pidf),) as context:
            do_something(logf, configf)



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Weasley Clock Deamon")
    parser.add_argument('-p', '--pid-file', default='/var/run/weasleyclock.pid')
    parser.add_argument('-l', '--log-file', default='/var/log/weasleyclock.log')
    parser.add_argument('-d', '--working-dir', default='/var/lib/weasleyclock')
    parser.add_argument('-c', '--config-file', default='/etc/weasleyclock.json')
    parser.add_argument('-n', '--no-daemon', action="store_true")
    parser.add_argument('-v', '--verbose', action="store_true")

    args = parser.parse_args()

    if args.verbose:
        debug_p = True

    start_daemon(pidf=args.pid_file,
                 logf=args.log_file,
                 wdir=args.working_dir,
                 configf=args.config_file,
                 nodaemon=args.no_daemon)
