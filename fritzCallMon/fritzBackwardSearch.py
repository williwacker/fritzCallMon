# -*- coding: utf-8 -*-

import argparse
import logging
import os
import re
import sys

# import root directory into python module search path
sys.path.insert(1, os.getcwd())  # noqa

from fritzconnection import FritzConnection
from fritzconnection.lib.fritzcall import Call

from dasOertliche import DasOertliche
from fritzCalls import FritzCalls, get_names_not_found, set_names_not_found
from fritzPhonebook import MyFritzPhonebook
from logs import get_logger
from prefs import read_configuration

logger = logging.getLogger(__name__)


args = argparse.Namespace()
args.logfile = ''


class FritzBackwardSearch():

    def __init__(self, connection=None):
        self.logger = get_logger()
        self.prefs = read_configuration()
        self.namesNotFound = []
        self.calldict = []
        global args
        args = self._get_cli_arguments()
        if connection:
            self.connection = connection
        else:
            self.connection = FritzConnection(
                address=args.address,
                port=args.port,
                user=args.username,
                password=args.password)
        self.phonebook = MyFritzPhonebook(
            connection=self.connection,
            name=self.prefs['fritz_phone_book'],
        )
        self.areaCode = self._get_area_code()
        self.onkz = self._read_ONKz(self.prefs['area_code_file'])
        self.logger.info('%s has been started', __class__.__name__)

    def _get_names(self):
        foundlist = {}
        for call in self.calldict:
            number = self._only_numerics(call.Name)
            origNumber = number
            # remove international numbers
            if number.startswith("00"):
                fullNumber = ""
                logger.info("Ignoring international number %s", number)
                self.namesNotFound.append(number)
            # remove pre-dial number for mobile
            elif number.startswith("010"):
                m = re.search(r"^010\d*?(01(5|6|7)\d+)", number)
                if m:
                    number = m.group(1)
                fullNumber = number
            else:
                # add the area code for local numbers
                m = re.search(r'^[1-9][0-9]+', number)
                if m:
                    fullNumber = '{}{}'.format(self.areaCode, number)
                else:
                    fullNumber = number
            name = None
            numberLogged = False
            numberSaved = False
            l_onkz = self._get_ONKz_length(fullNumber)
            while (name is None and len(fullNumber) >= (l_onkz + 3)):
                name = DasOertliche(lookup_number=fullNumber).name
                if not name:
                    logger.info('%s not found', fullNumber)
                    self.namesNotFound.append(fullNumber)
                    if fullNumber != number and not numberLogged:
                        self.namesNotFound.append(number)
                    if origNumber != number and not numberLogged:
                        self.namesNotFound.append(origNumber)
                    numberLogged = True
                    # don't do fuzzy search for mobile numbers and 0800
                    if fullNumber[0:3] in ("015", "016", "017") or fullNumber[0:4] in ("0800"):
                        fullNumber = ""
                    elif fullNumber[-1] == "0":
                        fullNumber = fullNumber[:-2]+"0"
                    else:
                        fullNumber = fullNumber[:-2]+"0"
                else:
                    foundlist[fullNumber] = name
                    if fullNumber != number and not numberSaved:
                        foundlist[number] = name
                    numberSaved = True
        return foundlist

    def _only_numerics(self, seq):
        if seq:
            seq_type = type(seq)
            return seq_type().join(filter(seq_type.isdigit, seq))
        return ''

    def _read_ONKz(self, areacodefile):  # read area code numbers
        onkz = []
        fname = os.path.join(
            os.path.dirname(__file__),
            'data',
            areacodefile,
        )
        if os.path.isfile(fname):
            with open(fname, encoding='utf-8', mode='r') as csvfile:
                for row in csvfile:
                    onkz.append(row.strip().split('\t'))
        else:
            logger.error('%s not found', fname)
        return onkz

    def _get_ONKz_length(self, phone_number):
        for row in self.onkz:
            if phone_number[0:len(row[0])] == row[0]:
                return len(row[0])
        # return 4 as default length if not found (e.g. 0800)
        return 4

    def _get_area_code(self):
        return (
            self.connection.call_action(
                'X_VoIP', 'GetVoIPCommonAreaCode')
        )['NewVoIPAreaCode']

    def _runSearch(self, s=''):
        searchnumber = []
        self.namesNotFound = get_names_not_found(
            self.prefs['name_not_found_file'])
        self.calldict = FritzCalls(
            days_back=7, namesNotFound=self.namesNotFound).calldict
        # add search numbers provided via cli
        if args.searchnumber:
            if isinstance(args.searchnumber, tuple):
                searchnumber += args.searchnumber
            else:
                searchnumber.append(args.searchnumber)
        # add search numbers provided via parameter
        if s:
            if isinstance(s, tuple):
                searchnumber += s
            else:
                searchnumber.append(s)
        if searchnumber:
            for number in searchnumber:
                logger.info("Searching for %s", number)
                contact = self.phonebook.get_entry(number=number)
                if not contact:
                    if number in self.namesNotFound:
                        logger.info(
                            '%s already in nameNotFoundList', number)
                    else:
                        new = Call()
                        new.Name = number
                        self.calldict.append(new)
                else:
                    for realName in contact['contact'].iter('realName'):
                        logger.info(
                            '%s = %s(%s)',
                            number,
                            args.phonebook,
                            realName.text.replace('&amp;', '&'),
                        )
        else:
            logger.error("Searchnumber nicht gesetzt")

        knownCallers = self._get_names()
        set_names_not_found(
            self.prefs['name_not_found_file'], self.namesNotFound)
        self.phonebook.add_entry_list(knownCallers)

    # ---------------------------------------------------------
    # cli-section:
    # ---------------------------------------------------------

    def _get_cli_arguments(self):
        parser = argparse.ArgumentParser(
            description='Update phonebook with caller list')
        parser.add_argument('-p', '--password',
                            nargs=1, default=self.prefs['password'],
                            help='Fritzbox authentication password')
        parser.add_argument('-u', '--username',
                            nargs=1, default=self.prefs['fritz_username'],
                            help='Fritzbox authentication username')
        parser.add_argument('-i', '--ip-address',
                            nargs=1, default=self.prefs['fritz_ip_address'],
                            dest='address',
                            help='IP-address of the FritzBox to connect to. '
                            'Default: %s' % self.prefs['fritz_ip_address'])
        parser.add_argument('--port',
                            nargs=1, default=self.prefs['fritz_tcp_port'],
                            help='Port of the FritzBox to connect to. '
                            'Default: %s' % self.prefs['fritz_tcp_port'])
        parser.add_argument('--phonebook',
                            nargs=1, default=self.prefs['fritz_phone_book'],
                            help='Existing phone book the numbers should be added to. '
                            'Default: %s' % self.prefs['fritz_phone_book'])
        parser.add_argument('-l', '--logfile',
                            nargs=1, default=self.prefs['logfile'],
                            help='Path/Log file name. '
                            'Default: %s' % self.prefs['logfile'])
        parser.add_argument('-a', '--areacodefile',
                            nargs=1, default=self.prefs['area_code_file'],
                            help='Path/file name where the area codes are listed. '
                            'Default: %s' % self.prefs['area_code_file'])
        parser.add_argument(
            '-n', '--notfoundfile', nargs=1, default=self.prefs['name_not_found_file'],
            help='Path/file name where the numbers not found during backward search are saved to in order to prevent further unnessessary searches. '
            'Default: %s' % self.prefs['name_not_found_file'])
        parser.add_argument('-s', '--searchnumber',
                            nargs='?', default='',
                            help='Phone number(s) to search for.')

        return parser.parse_args()


if __name__ == '__main__':
    FBS = FritzBackwardSearch()
#   to search for a number specify it in here:
#    FBS._runSearch(s=('765', ))
    FBS._runSearch()
