#!/usr/bin/env python3
import sys
import os
import time
import argparse
import json
import paho.mqtt.client as mqtt

debug_p = False
dryrun = False

def run_script(config_file, script_file):
    '''
    config_file holds the address of the MQTT server and login credentials
    script_file JSON file with array of MQTT events to send
    '''
    config_data = {}
    script_data = {}

    # read config file
    with open(config_file) as json_data_file:
        try:
            config_data = json.load(json_data_file)
        except json.JSONDecodeError as parse_error:
            print("JSON decode failed. [" + parse_error.msg + "]")
            print("error in file [", config_file, "] at pos: ",
                  parse_error.pos, " line: ",  parse_error.lineno)
            sys.exit(1)

    # read config file
    with open(script_file) as json_data_file:
        try:
            script_data = json.load(json_data_file)
        except json.JSONDecodeError as parse_error:
            print("JSON decode failed. [" + parse_error.msg + "]")
            print("error in file [", script_file, "] at pos: ",
                  parse_error.pos, " line: ",  parse_error.lineno)
            sys.exit(1)

    # connect to MQTT server
    host = config_data['mqtt_host']
    port = config_data['mqtt_port'] if 'mqtt_port' in config_data else 8883
    topic = config_data['mqtt_topic'] if 'mqtt_topic' in config_data else 'weasleyclock/#'

    if debug_p:
        print("connecting to host " + host + ":" + str(port) +
              " topic " + topic)

    # how to mqtt in python see https://pypi.org/project/paho-mqtt/
    user_data = {"script": script_data, "topic": topic}
    mqttc = mqtt.Client(client_id='mqtt_script_play',
                        clean_session=True,
                        userdata=user_data)

    mqttc.username_pw_set(config_data['mqtt_user'],
                          config_data['mqtt_password'])

    # create callbacks
    mqttc.on_connect = on_connect
    mqttc.on_message = on_message
    mqttc.connected_flag = False

    if port == 4883 or port == 4884 or port == 8883 or port == 8884:
        mqttc.tls_set('/etc/ssl/certs/ca-certificates.crt')

    mqttc.loop_start()
    mqttc.connect(host, port, 60)
    while not mqttc.connected_flag:
        time.sleep(0.1)
    send_mqtt_messages(mqttc, userdata=user_data)
    time.sleep(2)
    mqttc.loop_stop()
    mqttc.disconnect()
    print("All Done.")


def on_connect(client, userdata, flags, rc):
    '''
    Connect to the MQTT server, then start sending MQTT messages from our script.
    '''
    client.connected_flag = True


def on_message(client, userdata, message):
    '''
    We don't care about incoming messages. We are only sending a set
    script of MQTT messages.
    '''
    return


def send_mqtt_messages(client, userdata):
    '''
    Iterate over the list of messages in the script and send them.
    '''
    script = userdata['script']
    if debug_p:
        print("send_mqtt_messages")
    for msg in script:
        topic = 'weasleyclock/susan'
        if 'topic' in msg:
            topic = msg['topic']
        if 'type' in msg:
            if msg['type'] == 'sleep':
                t = 1
                if 'time' in msg:
                    t = msg['time']
                if debug_p:
                    print("SLEEP for ", t, " seconds")
                time.sleep(t)
            elif msg['type'] == 'range':
                range_key = 'distance'
                if 'range_key' in msg:
                    range_key = msg['range_key']
                wait = 0.1
                if 'sleep' in msg:
                    wait = msg['sleep']
                (start, stop, inc) = (50, 0, -1)
                if 'range' in msg:
                    (start, stop, inc) = msg['range']
                if debug_p:
                    print("RANGE: ", range_key, "(", start, stop, inc, ")")
                for val in range(start, stop, inc):
                    m = msg['msg']
                    m[range_key] = val
                    send_message(client, topic, m)
                    time.sleep(wait)
            else:
                print("Unknown message type [", msg['type'], "]")
        else:
            send_message(client, topic, msg['msg'])


def send_message(client, topic, message):
    '''
    Send MQTT message
    '''
    if debug_p:
        print("send_message")
    json_msg = json.dumps(message)
    if debug_p:
        print(topic, json_msg)
    if not dryrun:
        client.publish(topic, payload=json_msg, qos=2, retain=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MQTT message script")
    parser.add_argument('-c', '--config-file', default='/home/pi/weasleyclockd/weasleyclockd.json')
    parser.add_argument('-s', '--script-file', default='/home/pi/weasleyclockd/demo_mqtt.json')
    parser.add_argument('-v', '--verbose', action="store_true")
    parser.add_argument('-d', '--dryrun', action="store_true")

    args = parser.parse_args()

    if args.verbose:
        debug_p = True

    if args.dryrun:
        dryrun = True

    run_script(config_file=args.config_file,
               script_file=args.script_file)
