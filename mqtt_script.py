#!/usr/bin/env python3
import sys
import os
import time
import argparse
import json
import paho.mqtt.client as mqtt

debug_p = True


def run_script(working_dir, config_file, script_file):
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
    port = config_data['mqtt_port'] if 'mqtt_port' in config_data else 4884
    topic = config_data['mqtt_topic'] if 'mqtt_topic' in config_data else 'weasleyclock/#'

    if debug_p:
        print("connecting to host " + host + ":" + str(port) +
              " topic " + topic)

    # how to mqtt in python see https://pypi.org/project/paho-mqtt/
    mqttc = mqtt.Client(client_id='mqtt_script_play',
                        clean_session=True,
                        userdata={"script": script_data, "topic": topic})

    mqttc.username_pw_set(config_data['mqtt_user'],
                          config_data['mqtt_password'])

    # create callbacks
    mqttc.on_connect = on_connect
    mqttc.on_message = on_message

    if port == 4883 or port == 4884:
        mqttc.tls_set('/etc/ssl/certs/ca-certificates.crt')

    mqttc.connect(host, port, 60)


def on_connect(client, userdata, flags, rc):
    '''
    Connect to the MQTT server, then start sending MQTT messages from our script.
    '''
    client.subscribe(userdata['topic'])
    print("subscibing to topic [" + userdata['topic'] +
          "] result code " + str(rc))
    # TODO: send MQTT messages

    # types of events: MSG, sleep, distance range
    
    # TODO: when done exit


def on_message(client, userdata, message):
    '''
    We don't care about incoming messages. We are only sending a set
    script of MQTT messages.
    '''
    return


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MQTT message script")
    parser.add_argument('-c', '--config-file', default='/home/pi/weasleyclockd/weasleyclockd.json')
    parser.add_argument('-s', '--script-file', default='/home/pi/weasleyclockd/demo_mqtt.json')
    parser.add_argument('-v', '--verbose', action="store_true")

    args = parser.parse_args()

    if args.verbose:
        debug_p = True

    run_script(configf=args.config_file,
               script=args.sctript_file)
