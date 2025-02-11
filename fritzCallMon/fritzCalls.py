# -*- coding: utf-8 -*-

import logging
import os
import sys

# import root directory into python module search path
sys.path.insert(1, os.getcwd())  # noqa


from fritzconnection import FritzConnection
from fritzconnection.lib.fritzcall import FritzCall

from logs import get_logger
from prefs import read_configuration

logger = logging.getLogger(__name__)


def get_names_not_found(path):
    try:
        with open(path, encoding='utf-8', mode='r') as file:
            namesNotFound = file.read().splitlines()
    except:
        with open(path, encoding='utf-8', mode='w+') as file:
            namesNotFound = file.read().splitlines()
    return namesNotFound


def set_names_not_found(path, new_list):
    nameNotFoundList_length = len(get_names_not_found(path))
    if len(new_list) > nameNotFoundList_length:
        with open(path, encoding='utf-8', mode="w") as outfile:
            outfile.write("\n".join(new_list))


class FritzCalls():
    """
    Returns a list of caller dicts not having a name and not being listed in the given namesNotFound list
    """

    def __init__(self, days_back=7, connection=None, namesNotFound=None):
        self.days_back = days_back
        self.logger = get_logger()
        self.prefs = read_configuration()
        if connection:
            self.connection = connection
        else:
            self.connection = FritzConnection(
                address=self.prefs['fritz_ip_address'],
                port=self.prefs['fritz_tcp_port'],
                user=self.prefs['fritz_username'],
                password=self.prefs['password']
            )
        if namesNotFound is not None:
            self.namesNotFound = namesNotFound
        else:
            self.namesNotFound = get_names_not_found(
                self.prefs['name_not_found_file'])
        self.calldict = []
        self.logger.info('%s has been started', __class__.__name__)
        self._get_unknown()

    def _get_unknown(self):  # get list of callers not listed with their name
        for call_dict in FritzCall(fc=self.connection).get_calls(days=self.days_back):
            if call_dict.Id is None or call_dict.Caller is None:
                continue
            if call_dict.Name and not call_dict.Name.isdigit() and not '(' in call_dict.Name:
                continue
            if call_dict.Caller and call_dict.Type in ('1', '2') and call_dict.Caller.isdigit():
                if call_dict.Name and '(' in call_dict.Name:
                    new = call_dict
                    startAlternate = call_dict.Name.find('(')
                    new.Name = ''.join(
                        filter(
                            str.isdigit, call_dict.Name[startAlternate + 1:len(call_dict.Name)-1])
                    )
                    if new.Name not in self.namesNotFound:
                        self.calldict.append(new)
                call_dict.Name = call_dict.Caller
            if call_dict.Called and call_dict.Type == '3' and call_dict.Called.isdigit():
                call_dict.Name = call_dict.Called
            if call_dict.Name in self.namesNotFound:
                continue
            self.calldict.append(call_dict)


if __name__ == '__main__':
    FC = FritzCalls(days_back=7, namesNotFound=[])
    for call in FC.calldict:
        print(call)
