#!/usr/bin/env python3
import sys
import time
import argparse
import logging
import logging.handlers
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
        'angle': 340,
        'theta': 20,
        'offset_style': 'staggered',
        'update_delay': 30
        },
    'barn': {
        'name': 'Barn',
        'angle': 320,
        'theta': 20,
        'offset_style': 'staggered',
        'update_delay': 30
        },
    'mortalperil': {
        'name': 'Mortal Peril',
        'angle': 270,
        'theta': 50,
        'offset_style': 'distance'
        },
    'quidditch': {
        'name': 'Quidditch',
        'angle': 220,
        'theta': 50,
        'offset_style': 'distance'
        },
    'work': {
        'name': 'Work',
        'angle': 180,
        'theta': 40,
        'offset_style': 'staggered'
        },
    'school': {
        'name': 'School',
        'angle': 140,
        'theta': 40,
        'offset_style': 'staggered',
        'update_delay': 60,
        },
    'garden': {
        'name': 'Garden',
        'angle': 90,
        'theta': 50,
        'offset_style': 'staggered',
        'update_delay': 30
        },
    'intransit': {
        'name': 'In Transit',
        'angle': 40,
        'theta': 50,
        'offset_style': 'distance'
        },
    'lost': {
        'name': 'Lost',
        'angle': 5,      # leave 5 degrees, to avoid confusion w/ Home
        'theta': 35,
        'offset_style': 'distance'
        },
    'error': {
        'name': 'Error',
        'angle': 0,
        'theta': 0,
        'offset_style': 'none'
        },
    }

# Holds the current state of the clock hands
current_state = {}


def log_distance(distance):
    '''Map a distance to a log based scale.

    This formula creates a log scale of distance in the range [0.0,1.0]
       0.0  ->  0.00
       0.5  ->  0.07
       1.0  ->  0.12
       2.0  ->  0.18
       5.0  ->  0.28
      10.0  ->  0.36
      15.0  ->  0.41
      25.0  ->  0.47
      50.0  ->  0.56
     100.0  ->  0.65
     500.0  ->  0.85
    2500.0  ->  1.00  max distance that can be differentiated
    6000.0  ->  1.00
    9000.0  ->  1.00

    This scaling factor is used to place the hand within the given
    segment. A scale of zero, puts the hand closer to home while a
    scale of 1.0 puts the hand farthest from home.

    This provides much more resolution near home. Small changes of
    distances near home can be seen, while small and medium changes of
    distance when far from home are roughly identical.

    '''
    mult = 1.7
    max_dist = 2500
    scale = (np.log(mult * distance + 1.1) - np.log(1.1))/np.log(max_dist)
    if scale < 0.0:
        scale = 0.0
    elif scale > 1.0:
        scale = 1.0
    return scale


def angle_offset(state, angle, theta, distance, hand, style, config_data):
    '''
    Calculate where in the sector to point the clock hands.
    '''
    if style == 'distance':
        scale = log_distance(distance)
        if angle < 180:
            # left side of clock face
            return scale * theta
        else:
            return theta - (scale * theta)
    elif style == 'staggered' or style == 'home':
        # each hand 0-3 has it's own small offset, calculated based on how many hands are in each sector
        hands = hands_in_state(state, config_data)
        num_hands = len(hands)
        if num_hands < 2:
            # one hand, place in the middle of the sector
            scale = 0.5
        else:
            # evenly space the hands within the sector
            index = hands.index(hand)
            if num_hands == 2:
                scale = 0.5 * (float(index) / float(num_hands - 1.0)) + 0.25
            else:
                scale = 0.8 * (float(index) / float(num_hands - 1.0)) + 0.1
        return scale * theta
    # middle of the sector
    return (theta / 2.0)


def on_connect(client, clockdata, flags, rc):
    '''
    The callback for when the client receives a CONNACK response from the server.
    '''
    client.subscribe(clockdata['topic'])
    client.publish('weasleyclock/UPDATE', payload='{"update":"true"}', qos=0, retain=False)
    if rc != 0:
        clockdata['logger'].warning("subscribing to topic [" +
                                    clockdata['topic'] +
                                    "] result code " + str(rc))
    else:
        clockdata['logger'].debug("subscribing to topic [" +
                                  clockdata['topic'] +
                                  "] result code " + str(rc))


def on_message(client, clockdata, message):
    '''
    Callback for received MQTT messages.
    '''
    # wrap the on_message() processing in a try:
    try:
        _on_message(client, clockdata, message)
    except Exception as e:
        clockdata['logger'].error("on_message() failed: {}".format(e))


def _on_message(client, clockdata, message):
    '''
    Callback for received MQTT messages.
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

    clockdata['logger'].debug("Received message '" +
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
        clockdata['logger'].error("JSON decode failed.")

    # python <=3.4.* use ValueError
    # except ValueError as parse_error:
    #    if debug_p:
    #        print("JSON decode failed: " + str(parse_error))

    update_clock_state(name, msg_data, clockdata)


def update_hand_state(name, state, distance):
    '''
    Set the clock hand position in the global state.
    '''
    current_state[name] = {
        'name': name,
        'state': state,
        'distance': distance,
        'updated': time.time(),
        'hand_moved': False
        }


def hands_in_state(state, config_data):
    '''
    return a sorted list of all the hands in the given state
    '''
    hands = []
    for name in current_state:
        # only count hands that have already been moved.
        # TODO: BUG: the count will be off for hands that haven't moved yet.
        if current_state[name]['state'] == state:  # < and current_state[name]['hand_moved']:
            if name in config_data['hand']:
                hand = config_data['hand'][name]
                hands.append(hand)
    hands.sort()
    return hands


def update_all_hands(clockdata):
    '''
    Iterate over all the hands and update the current physical position to match the current state.
    '''
    now = time.time()
    for name in current_state:
        state = current_state[name]['state']
        if state == 'unavailable' or state == 'unknown':
            if debug_p:
                print("State for [" + name + "] is " + state)
            state = "lost"
            continue
        if 'update_delay' in states[state]:
            update_delay = states[state]['update_delay']
        else:
            update_delay = 0
        if 'updated' not in current_state[name]:
            print("no updated entry for " + name)
            current_state[name]['updated'] = 0
        if current_state[name]['updated'] + update_delay <= now:
            move_clock_hand(current_state[name], clockdata)
            current_state[name]['hand_moved'] = True
        else:
            if debug_p:
                print("delay update of [" + name + "] to state [" + state + "] for " + str(update_delay))


def move_clock_hand(userstate, clockdata):
    '''
    Physically move a single hand given its state.
    '''
    name = userstate['name']
    state = userstate['state']
    distance = userstate['distance']
    config_data = clockdata['config_data']
    if debug_p:
        print("Move " + name + " hand to " + state +
              " ({0:.1f} miles away)".format(distance))

    if name not in config_data['hand']:
        if debug_p:
            print("Person " + name + " is not tracked by a clock hand")
        return
    hand = config_data['hand'][name]

    if hand not in config_data['channel']:
        clockdata['logger'].error("Hand " + hand +
                                  " does not have a specified PWM channel")
        return
    channel = config_data['channel'][hand]

    if state not in states:
        clockdata['logger'].error("Unknown target state [" + state + "]")
        return

    target_state = states[state]
    base_angle = float(target_state['angle'])
    theta = float(target_state['theta'])
    style = target_state['offset_style']

    # Use hand style for Quidditch when still at home. This is to cover
    # the case when riding Zwift indoors.
    if state == 'quidditch' and distance < 0.2:
        style = 'staggered'

    offset = angle_offset(state, base_angle, theta, distance, hand, style, config_data)
    # add 720 to keep servos closer to the center of their range
    servo_angle = int(2 * (base_angle + offset)) + 720
    clockdata['kit'].servo[channel].angle = servo_angle

    if not current_state[name]['hand_moved']:
        clockdata['logger'].info("Move [" + name +
                                 "] hand to [" + state +
                                 "] ({0:.1f} miles away)".format(distance))

    if debug_p:
        print("base_angle [" + str(base_angle) + "] theta [" + str(theta) +
              "] style [" + style + "]")
        print("distance [", distance, "]  offset [", offset, "]")
        print("servo angle: ", servo_angle)


def string2float(str):
    '''
    Convert a string to a float. Detect "None" string.
    '''
    # TODO: this could do better error handling and even catch the exception
    if str == 'None':
        return 0.0
    return float(str)


def update_clock_state(name, message, clockdata):
    '''
    Parse message data and set the person's clock hand state. Position is updated separately.
    '''
    config_data = clockdata['config_data']
    state = None
    latitude = None
    longitude = None
    distance = 0.0
    if 'state' in message:
        state = message['state']
    if 'latitude' in message:
        latitude = string2float(message['latitude'])
    if 'longitude' in message:
        longitude = string2float(message['longitude'])
    if 'distance' in message:
        distance = string2float(message['distance'])

    # distance overrides lat/lon
    if distance == 0.0 and latitude and longitude:
        latitude_home = float(config_data['latitude'])
        longitude_home = float(config_data['longitude'])
        distance = great_circle((latitude_home, longitude_home),
                                (latitude, longitude)).miles

    update_hand_state(name, state, distance)
#    update_all_hands(clockdata)


def do_something(logf, configf):
    '''
    Main routine.
    '''

    #
    # setup logging
    #
    logger = logging.getLogger('weasleyclock')
    logger.setLevel(logging.INFO)

    formatstr = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    formatter = logging.Formatter(formatstr)

    handler = logging.handlers.RotatingFileHandler(
              logf, maxBytes=1049600, backupCount=10)

    handler.setLevel(logging.INFO)
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Old logger, without log rotation
    # fh = logging.FileHandler(logf)
    # fh.setLevel(logging.INFO)
    # fh.setFormatter(formatter)
    # logger.addHandler(fh)

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

    m_clockdata = {
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
                        userdata=m_clockdata)

    mqttc.username_pw_set(config_data['mqtt_user'],
                          config_data['mqtt_password'])

    # create callbacks
    mqttc.on_connect = on_connect
    mqttc.on_message = on_message

    if port == 4883 or port == 4884 or port == 8883 or port == 8884:
        mqttc.tls_set('/etc/ssl/certs/ca-certificates.crt')

    while (True):
        try:
            mqttc.connect(host, port, 60)
            break
        except Exception as e:
            # Connection failure.
            logger.error("connect() failed: {}".format(e))
            time.sleep(60)

# If we don't run our own loop, then loop forever
#    mqttc.loop_forever()

    mqttc.loop_start()

    while True:
        update_all_hands(m_clockdata)
        time.sleep(1)

# no Try, only do. So that things actually crash if there's a bug.
#    while True:
#        try:
#            update_all_hands(m_clockdata)
#            time.sleep(1)
#        except Exception as e:
#            print(e)
#            if debug_p:
#               print("update_all_hands() failed: {}".format(e))
#            logger.error("update_all_hands() failed: {}".format(e))
#            time.sleep(60)

    mqttc.disconnect()
    mqttc.loop_stop()


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
            context.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Weasley Clock Daemon")
    parser.add_argument('-p', '--pid-file', default='/run/lock/weasleyclockd.pid')
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
