#!/usr/bin/env python3.7
import sys
import os
import time
import argparse
import logging
import daemon
import json
import paho.mqtt.client as mqtt
from daemon import pidfile

debug_p = True


# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    userdata.logger.INFO("Connected with result code "+str(rc))

    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe(userdata['topic')


def on_message(client, userdata, message):
    userdata.logger.INFO("Received message '" + str(message.payload) +
                         "' on topic '" + message.topic +
                         "' with QoS " + str(message.qos))


def do_something(logf, configf):
    # This does the "work" of the daemon

    #
    # setup logging
    #
    logger = logging.getLogger('eg_daemon')
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

    logger.info("Weasley Clock: connecting to host " + host + ":" + port +
                " topic " + topic)

    clockdata = {
        'logger': logger,
        'host': host,
        'port': port,
        'topc': topic,
        'config_data': config_data,
        }

    mqttc = mqtt.Client(client_id='',
                        clean_session=True,
                        userdata=clockdata)
    mqttc.subscribe(topic)

    # create callbacks
    # https://pypi.org/project/paho-mqtt/
    mqttc.on_connect = on_connect
    mqttc.on_message = on_message

    # intitialize clock hands

    mqttc.connect(host, port, 60)

    # loop
    mqttc.loop_forever()

#    while True:
#        logger.info("this is an INFO message")
#        time.sleep(5)


def start_daemon(pidf, logf, configf):
    # This launches the daemon in its context

    global debug_p

    if debug_p:
        print("weasleyclock: entered run()")
        print("weasleyclock: pidf = {}    logf = {}".format(pidf, logf))
        print("weasleyclock: about to start daemonization")

    # pidfile is a context
    with daemon.DaemonContext(
        working_directory='/var/lib/weasleyclock',
        umask=0o002,
        pidfile=pidfile.TimeoutPIDLockFile(pidf),
        ) as context:
        do_something(logf, configf)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Weasley Clock Deamon")
    parser.add_argument('-p', '--pid-file', default='/var/run/weasleyclock.pid')
    parser.add_argument('-l', '--log-file', default='/var/log/weasleyclock.log')
    parser.add_argument('-c', '--config-file', default='/etc/weasleyclock.json')

    args = parser.parse_args()

    start_daemon(pidf=args.pid_file, logf=args.log_file, configf=args.config_file)
