#!/usr/bin/env python3.7
import sys
import os
import time
import argparse
import logging
import daemon
import json
import paho.mqtt.client as mqtt
import daemon
import lockfile

debug_p = True


# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    client.subscribe(userdata['topic'])
    print("subscibing to topic [" + userdata['topic'] + "]")
    userdata['logger'].info("subscibing to topic [" + userdata['topic'] + "]")
    userdata['logger'].info("Connected with result code "+str(rc))


def on_message(client, userdata, message):
    print("Received message '" + str(message.payload.decode()) +
          "' on topic '" + message.topic +
          "' with QoS " + str(message.qos))
    userdata['logger'].info("Received message '" + str(message.payload.decode()) +
                         "' on topic '" + message.topic +
                         "' with QoS " + str(message.qos))


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

    logger.info("Weasley Clock: connecting to host " + host + ":" + str(port) +
                " topic " + topic)

    if debug_p:
        print("Weasley Clock: connecting to host " + host + ":" + str(port) +
              " topic " + topic)

    print(logger)
        
    clockdata = {
        'logger': logger,
        'host': host,
        'port': port,
        'topic': topic,
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

    # intitialize clock hands

    mqttc.connect(host, port, 60)

    print("after connect")

    # loop
    mqttc.loop_forever()

    print("after loop_forever")

#    while True:
#        logger.info("this is an INFO message")
#        time.sleep(5)


def start_daemon(pidf, logf, wdir, configf):
    # This launches the daemon in its context

    global debug_p

    if debug_p:
        print("weasleyclock: entered run()")
        print("weasleyclock: pidf = {}    logf = {}".format(pidf, logf))
        print("weasleyclock: about to start daemonization")

    # pidfile is a context
#    with daemon.DaemonContext(
#            working_directory=wdir,
#            umask=0o002,
#            pidfile=lockfile.FileLock(pidf),
#         ) as context:
#        print("do something!")
#        do_something(logf, configf)

    print("really do something")
    do_something(logf, configf)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Weasley Clock Deamon")
    parser.add_argument('-p', '--pid-file', default='/var/run/weasleyclock.pid')
    parser.add_argument('-l', '--log-file', default='/var/log/weasleyclock.log')
    parser.add_argument('-d', '--working-dir', default='/var/lib/weasleyclock')
    parser.add_argument('-c', '--config-file', default='/etc/weasleyclock.json')

    args = parser.parse_args()

    start_daemon(pidf=args.pid_file,
                 logf=args.log_file,
                 wdir=args.working_dir,
                 configf=args.config_file)
