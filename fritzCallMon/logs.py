import logging
import os
import sys
from logging import StreamHandler
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

# import root directory into python module search path
sys.path.insert(1, os.getcwd())  # noqa

from prefs import read_configuration


def is_docker():
    cgroup = Path('/proc/self/cgroup')
    return Path('/.dockerenv').is_file() or (cgroup.is_file() and 'docker' in cgroup.read.text())


def get_logger():
    logger = logging.getLogger()

    if logger.handlers:
        return logger

    prefs = read_configuration()

    logfile = os.path.abspath(prefs['logfile'])

    numeric_level = getattr(logging, prefs['loglevel'].upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {prefs['loglevel']}")
    logger.setLevel(numeric_level)

    if is_docker():
        handler = StreamHandler()
    else:
        handler = TimedRotatingFileHandler(
            logfile,
            when='midnight',
            backupCount=7
        )
    handler.setLevel(numeric_level)

    formatter = logging.Formatter(
        fmt='%(asctime)s %(module)s %(levelname)s [%(name)s:%(lineno)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    if not is_docker():
        # create also handler for displaying output in the stdout
        ch = StreamHandler()
        ch.setLevel(numeric_level)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    return logger
