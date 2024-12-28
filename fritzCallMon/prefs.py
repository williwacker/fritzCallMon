import configparser
import os
import sys
import logging


# read configuration from the configuration file and prepare a preferences dict
def read_configuration():
    logger = logging.getLogger()

    filename = os.path.join(
        os.path.dirname(__file__),
        'config',
        'fritzBackwardSearch.ini',
    )
    if os.path.isfile(filename):
        cfg = configparser.ConfigParser()
        cfg.read(filename)
        preferences = {}
        for name, value in cfg.items('DEFAULT'):
            if name == 'status_to_terminal':
                preferences[name] = cfg.getboolean(
                    'DEFAULT', 'status_to_terminal')
            else:
                preferences[name] = value
        return preferences
    logger.error('%s not found', filename)
    sys.exit(1)


