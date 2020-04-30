#!/usr/bin/env python3
import sys
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


def log_distance(distance):
    scale = (np.log(distance + 1.1) - np.log(1.1))/np.log(10000)
    return scale


def angle_offset(angle, theta, distance, hand, style):
    '''
    Calculate where in the sector to point the clock hands.
    '''
    if style == 'distance':
        # this formula creates a log scale of distance in the range [0.0,1.0]
        # (ln(distance + 1.1) - ln(1.1))/ln(10000)
        scale = log_distance(distance)
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


def on_connect(client, userdata, flags, rc):
    '''
    The callback for when the client receives a CONNACK response from the server.
    '''
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


def on_message(client, userdata, message):
    '''
    Callback for recieved MQTT messages.
    '''
    # wrap the on_message() processing in a try:
    try:
        _on_message(client, userdata, message)
    except Exception as e:
        userdata['logger'].error("on_message() failed: {}".format(e))


def _on_message(client, userdata, message):
    '''
    Callback for recieved MQTT messages.
    '''
    topic = message.topic

    (prefix, name) = topic.split('/', 1)

    if name == "UPDATE":
        # this is an update request, ignore
        return

    m_decode = str(message.payload.decode("utf-8", "ignore"))
    if debug_p:
        print("Received message '" + m_decode +
              "' on topic '" + topic +
              "' with QoS " + str(message.qos))

    log_snippet = (m_decode[:15] + '..') if len(m_decode) > 17 else m_decode
    log_snippet = log_snippet.replace('\n', ' ')

    userdata['logger'].debug("Received message '" +
                             log_snippet +
                             "' on topic '" + topic +
                             "' with QoS " + str(message.qos))

    try:
        msg_data = json.loads(m_decode)
    except json.JSONDecodeError as parse_error:
        if debug_p:
            print("JSON decode failed. [" + parse_error.msg + "]")
            print("error at pos: " + parse_error.pos +
                  " line: " + parse_error.lineno)
        userdata['logger'].error("JSON decode failed.")

    # python <=3.4.* use ValueError
    # except ValueError as parse_error:
    #    if debug_p:
    #        print("JSON decode failed: " + str(parse_error))

    move_clock_hands(name, msg_data, userdata)


def move_clock_hands(name, message, userdata):
    '''
    Move Clock Hands. Move user hand to the indicated state and style.
    '''
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
    if 'distance' in message:
        distance = float(message['distance'])

    # distance overides lat/lon
    if distance == 0.0 and latitude and longitude:
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

    # Use hand style for Quidditch when still at home. This is to cover
    # the case when riding Zwift indoors.
    if state == 'quidditch' and distance < 0.2:
        style = 'hand'

    offset = angle_offset(base_angle, theta, distance, hand, style)
    # add 720 to keep servos closer to the center of their range
    servo_angle = int(2 * (base_angle + offset)) + 720
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
    '''
    Main routine.
    '''

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
        try:
            config_data = json.load(json_data_file)
        except json.JSONDecodeError as parse_error:
            print("JSON decode failed. [" + parse_error.msg + "]")
            print("error at pos: ", parse_error.pos,
                  " line: ",  parse_error.lineno)
            sys.exit(1)

    # connect to MQTT server
    host = config_data['mqtt_host']
    port = config_data['mqtt_port'] if 'mqtt_port' in config_data else 8883
    topic = config_data['mqtt_topic'] if 'mqtt_topic' in config_data else 'weasleyclock/#'

    logger.info("connecting to host " + host + ":" + str(port) +
                " topic " + topic)

    if debug_p:
        print("connecting to host " + host + ":" + str(port) +
              " topic " + topic)

    # configure servos and zero clock hands
    kit = ServoKit(channels=16)

    for (hand, servo) in config_data['channel'].items():
        # default (good starting point for hs785hb servo)
        pulsewidth_min = 685
        pulsewidth_max = 2070
        actuation_range = 2160

        # get per servo/channel configuration
        if 'channel_config' in config_data:
            if str(servo) in config_data['channel_config']:
                channel_config = config_data['channel_config'][str(servo)]
                if 'pulsewidth_min' in channel_config:
                    pulsewidth_min = int(channel_config['pulsewidth_min'])
                if 'pulsewidth_max' in channel_config:
                    pulsewidth_max = int(channel_config['pulsewidth_max'])
                if 'actuation_range' in channel_config:
                    actuation_range = int(channel_config['actuation_range'])

        kit.servo[servo].actuation_range = actuation_range
        kit.servo[servo].set_pulse_width_range(pulsewidth_min, pulsewidth_max)

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

    if port == 4883 or port == 4884 or port == 8883 or port == 8884:
        mqttc.tls_set('/etc/ssl/certs/ca-certificates.crt')

    mqttc.connect(host, port, 60)
    mqttc.loop_forever()


def start_daemon(pidf, logf, wdir, configf, nodaemon):
    '''
    Start the daemon.
    '''
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
    parser.add_argument('-p', '--pid-file', default='/home/pi/weasleyclockd/weasleyclock.pid')
    parser.add_argument('-l', '--log-file', default='/home/pi/weasleyclockd/weasleyclock.log')
    parser.add_argument('-d', '--working-dir', default='/home/pi/weasleyclockd')
    parser.add_argument('-c', '--config-file', default='/home/pi/weasleyclockd/weasleyclockd.json')
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
