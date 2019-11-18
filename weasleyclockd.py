#!/usr/bin/env python3.7
import sys
import os
import time
import argparse
import logging
import daemon
import json
from daemon import pidfile

debug_p = False


def do_something(logf):
    # This does the "work" of the daemon

    logger = logging.getLogger('eg_daemon')
    logger.setLevel(logging.INFO)

    fh = logging.FileHandler(logf)
    fh.setLevel(logging.INFO)

    formatstr = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    formatter = logging.Formatter(formatstr)

    fh.setFormatter(formatter)

    logger.addHandler(fh)

    while True:
        logger.debug("this is a DEBUG message")
        logger.info("this is an INFO message")
        logger.error("this is an ERROR message")
        time.sleep(5)


def start_daemon(pidf, logf):
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
        do_something(logf)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Weasley Clock Deamon")
    parser.add_argument('-p', '--pid-file', default='/var/run/weasleyclock.pid')
    parser.add_argument('-l', '--log-file', default='/var/log/weasleyclock.log')
    parser.add_argument('-c', '--config-file', default='/etc/weasleyclock.json')

    args = parser.parse_args()

    start_daemon(pidf=args.pid_file, logf=args.log_file)
