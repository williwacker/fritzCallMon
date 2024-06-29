#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""

Read the phone calls list and extract the ones that have no phonebook entry
Do a backward search with the used number and if a name has been found add the entry to the given phonebook

@Werner Kuehn - Use at your own risk
29.01.2016           Add alternate number search
09.02.2016           Fixed duplicate phonebook entries. Handling of type 2 calls
17.02.2016           Append numbers to existing phonebook entries
18.02.2016           Remove quickdial entry
17.03.2016           Changed html.parser to html.parser.HTMLParser()
21.03.2016           Added config file
23.03.2016           Fixed phone book entry names handling for html special characters
08.04.2016 0.2.0 WK  Added fritzCallMon.py, made fritzBackwardSearch module callable
27.04.2016 0.2.2 WK  Enhanced search by removing numbers at the end in case someone has dialed more numbers
03.08.2016 0.2.3 WK  Fix duplicate phonebook entries caused by following call of Type 10
27.12.2016 0.2.4 WK  Improve search by adding zero at the end
25.07.2017 0.2.5 WK  Correct html conversion in dastelefonbuch
09.08.2017 0.2.6 WK  Add area code length into suzzy search. Avoid adding pre-dial numbers into the phone book
27.08.2017 0.2.7 WK  Replace & in phonebook name with u. as AVM hasn't fixed this problem yet
02.03.2023 0.3.3 WK  Adopt to latest dasoertliche output


"""

__version__ = '0.3.0'

import argparse
import configparser
import copy
import datetime
import html.parser
import logging
import os
import re
import sys
from xml.etree.ElementTree import fromstring, tostring

import certifi
import urllib3
from bs4 import BeautifulSoup
from fritzconnection import FritzConnection
from fritzconnection.lib.fritzcall import Call, FritzCall
from fritzconnection.lib.fritzphonebook import FritzPhonebook

logger = logging.getLogger(__name__)

args = argparse.Namespace()
args.logfile = ''


class FritzCalls():

    def __init__(self, connection, nameNotFoundList):
        self.http = urllib3.PoolManager(
            cert_reqs='CERT_REQUIRED', ca_certs=certifi.where())
        self.areaCode = (connection.call_action(
            'X_VoIP', 'GetVoIPCommonAreaCode'))['NewVoIPAreaCode']
        self.nameNotFoundList = nameNotFoundList
        self.calldict = FritzCall(fc=connection).get_calls()
        self.get_unknown()

    def get_unknown(self):  # get list of callers not listed with their name
        self.unknownCallers = {}
        for i in range(len(self.calldict)-1, -1, -1):
            if self.calldict[i].Name and not self.calldict[i].Name.isdigit() and not '(' in self.calldict[i].Name:
                del self.calldict[i]
                continue
            if datetime.datetime.strptime(
                    self.calldict[i].Date, "%d.%m.%y %H:%M") < datetime.datetime.today() - datetime.timedelta(days=7):
                del self.calldict[i]
                continue
            if self.calldict[i].Caller and self.calldict[i].Type in ('1', '2') and self.calldict[i].Caller.isdigit():
                if self.calldict[i].Name and '(' in self.calldict[i].Name:
                    new = Call()
                    startAlternate = self.calldict[i].Name.find('(')
                    new.Name = self.calldict[i].Name[startAlternate +
                                                     1:len(self.calldict[i].Name)-1]
                    if new.Name not in self.nameNotFoundList:
                        self.calldict.append(new)
                self.calldict[i].Name = self.calldict[i].Caller
            if self.calldict[i].Called and self.calldict[i].Type == '3' and self.calldict[i].Called.isdigit():
                self.calldict[i].Name = self.calldict[i].Called
            if self.calldict[i].Name in self.nameNotFoundList:
                del self.calldict[i]

    def get_names(self, nameNotFoundList):
        foundlist = {}
        for call in self.calldict:
            number = call.Name
            origNumber = number
            # remove international numbers
            if number.startswith("00"):
                fullNumber = ""
                logger.info("Ignoring international number %s", number)
                nameNotFoundList.append(number)
            # remove pre-dial number
            elif number.startswith("010"):
                nextZero = number.find('0', 3)
                number = number[nextZero:]
                fullNumber = number
            else:
                # add the area code for local numbers
                m = re.search('^[1-9][0-9]+', number)
                if m:
                    fullNumber = '{}{}'.format(self.areaCode, number)
                else:
                    fullNumber = number
            name = None
            numberLogged = False
            numberSaved = False
            l_onkz = FritzBackwardSearch().get_ONKz_length(fullNumber)
            while (name == None and len(fullNumber) > (l_onkz + 3)):
                name = self.lookup_dasoertliche(fullNumber)
                if not name:
                    logger.info('{} not found'.format(fullNumber))
                    nameNotFoundList.append(fullNumber)
                    if fullNumber != number and not numberLogged:
                        nameNotFoundList.append(number)
                    if origNumber != number and not numberLogged:
                        nameNotFoundList.append(origNumber)
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

    def lookup_dasoertliche(self, number):
        url = 'https://www.dasoertliche.de/Controller?form_name=search_inv&ph={}'.format(
            number)
        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/54.0.2840.90 Safari/537.36'}
        response = self.http.request('GET', url, headers=headers)
        content = response.data.decode("utf-8", "ignore") \
            .replace('\t', '').replace('\n', '').replace('\r', '').replace('&nbsp;', ' ')
        soup = BeautifulSoup(content, 'html.parser')
        string = str(soup.find('script', type='application/ld+json'))
        m = re.search('\"@type\":\"Person\",\"name\":\"(.*?)\"', string)
        if m:
            name = m.group(1).replace(' & ', ' u. ')
            logger.info('%s = dasoertliche(%s)', number, name)
            return name
        m = re.search('\"@type\":\"LocalBusiness\",\"name\":\"(.*?)\"', string)
        if m:
            name = m.group(1).replace(' & ', ' u. ')
            logger.info('%s = dasoertliche(%s)', number, name)
            return name


class MyFritzPhonebook(object):

    def __init__(self, connection, name):
        self.connection = connection
        if name and isinstance(name, list):
            name = name[0]
        self.bookNumber = None
        for book_id in FritzPhonebook(self.connection).list_phonebooks:
            book = FritzPhonebook(self.connection).phonebook_info(book_id)
            if book['name'] == name:
                self.bookNumber = book_id
                break
        if not self.bookNumber:
            logger.error('Phonebook: %s not found !', name)
            sys.exit(1)

    def get_phonebook(self):
        self.http = urllib3.PoolManager()
        response = self.http.request('GET', self.connection.call_action(
            'X_AVM-DE_OnTel', 'GetPhonebook', NewPhonebookID=self.bookNumber)['NewPhonebookURL'])
        self.phonebookEntries = fromstring(
            re.sub("!-- idx:(\d+) --", lambda m: "idx>"+m.group(1)+"</idx", response.data.decode("utf-8")))

    def get_entry(self, name=None, number=None, uid=None, id=None):
        for contact in self.phonebookEntries.iter('contact'):
            if name is not None:
                for realName in contact.iter('realName'):
                    if html.unescape(realName.text) == html.unescape(name):
                        for idx in contact.iter('idx'):
                            return {'contact_id': idx.text, 'contact': contact}
            elif number is not None:
                for realNumber in contact.iter('number'):
                    if realNumber.text == number:
                        for idx in contact.iter('idx'):
                            return {'contact_id': idx.text, 'contact': contact}
            elif uid is not None:
                for uniqueid in contact.iter('uniqueid'):
                    if uniqueid.text == uid:
                        for idx in contact.iter('idx'):
                            return {'contact_id': idx.text, 'contact': contact}
            elif id is not None:
                phone_entry = fromstring(self.connection.call_action(
                    'X_AVM-DE_OnTel', 'GetPhonebookEntry', NewPhonebookID=self.bookNumber,
                    NewPhonebookEntryID=id)['NewPhonebookEntryData'])
                return {'contact_id': id, 'contact': phone_entry}

    def add_entry_list(self, entry_list):
        if entry_list:
            for number, name in entry_list.items():
                entry = self.get_entry(name=name)
                if entry:
                    self.append_entry(entry, number)
                else:
                    self.add_entry(number, name)

    def append_entry(self, entry, phone_number):
        phonebookEntry = self.get_entry(id=entry['contact_id'])['contact']
        for realName in phonebookEntry.iter('realName'):
            realName.text = realName.text.replace('& ', '&#38; ')
        newnumber = None
        for number in phonebookEntry.iter('number'):
            if 'quickdial' in number.attrib:
                del number.attrib['quickdial']
            newnumber = copy.deepcopy(number)
            newnumber.text = phone_number
            newnumber.set('type', 'home')
            newnumber.set('prio', '1')
        if not newnumber == None:
            for telephony in phonebookEntry.iter('telephony'):
                telephony.append(newnumber)
            arg = {
                'NewPhonebookID': self.bookNumber,
                'NewPhonebookEntryID': entry['contact_id'],
                'NewPhonebookEntryData':
                '<Envelope encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" xmlns:s="http://www.w3.org/2003/05/soap-envelope/">' +
                tostring(phonebookEntry).decode("utf-8") +
                '</Envelope>'
            }
            self.connection.call_action(
                'X_AVM-DE_OnTel', 'SetPhonebookEntry', arguments=arg)
            self.get_phonebook()

    def add_entry(self, phone_number, name):
        phonebookEntry = fromstring(
            '<contact><person><realName></realName></person><telephony><number></number></telephony></contact>')
        for number in phonebookEntry.iter('number'):
            number.text = phone_number
            number.set('type', 'home')
            number.set('prio', '1')
            number.set('id', '0')
        for realName in phonebookEntry.iter('realName'):
            realName.text = html.unescape(name)
        arg = {
            'NewPhonebookID': self.bookNumber,
            'NewPhonebookEntryID': '',
            'NewPhonebookEntryData':
            '<Envelope encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" xmlns:s="http://www.w3.org/2003/05/soap-envelope/">' +
            tostring(phonebookEntry).decode("utf-8") +
            '</Envelope>'
        }
        self.connection.call_action(
            'X_AVM-DE_OnTel:1', 'SetPhonebookEntry', arguments=arg)
        self.get_phonebook()


class FritzBackwardSearch(object):

    def __init__(self):
        fname = os.path.join(
            os.path.dirname(__file__),
            'config',
            'fritzBackwardSearch.ini',
        )
        if os.path.isfile(fname):
            self.prefs = self.__read_configuration__(fname)
        else:
            logger.error('%s not found', fname)
            exit(1)
        self.__init_logging__()
        global args
        args = self.__get_cli_arguments__()
        self.__read_ONKz__()
        self.connection = FritzConnection(
            address=args.address,
            port=args.port,
            user=args.username,
            password=args.password)
        self.phonebook = MyFritzPhonebook(self.connection, name=args.phonebook)
        self.phonebook.get_phonebook()
        self.notfoundfile = args.notfoundfile
        if args.notfoundfile and type(args.notfoundfile) is list:
            self.notfoundfile = args.notfoundfile[0]
        try:
            self.nameNotFoundList = open(
                self.notfoundfile, 'r').read().splitlines()
        except:
            self.nameNotFoundList = open(
                self.notfoundfile, 'w+').read().splitlines()

    def __init_logging__(self):
        numeric_level = getattr(logging, self.prefs['loglevel'].upper(), None)
        if not isinstance(numeric_level, int):
            raise ValueError('Invalid log level: %s' % self.prefs['loglevel'])
        logging.basicConfig(
            filename=self.prefs['logfile'],
            level=numeric_level,
            format=(
                '%(asctime)s %(levelname)s [%(name)s:%(lineno)s] %(message)s'),
            datefmt='%Y-%m-%d %H:%M:%S',
        )

    # read configuration from the configuration file and prepare a preferences dict
    def __read_configuration__(self, filename):
        cfg = configparser.ConfigParser()
        cfg.read(filename)
        preferences = {}
        for name, value in cfg.items('DEFAULT'):
            preferences[name] = value
        logger.debug(preferences)
        return preferences

    def __read_ONKz__(self):  # read area code numbers
        self.onkz = []
        fname = os.path.join(
            os.path.dirname(__file__),
            'data',
            args.areacodefile,
        )
        if os.path.isfile(fname):
            with open(fname, encoding='utf-8', mode='r') as csvfile:
                for row in csvfile:
                    self.onkz.append(row.strip().split('\t'))
        else:
            logger.error('% not found', fname)

    def get_ONKz_length(self, phone_number):
        for row in self.onkz:
            if phone_number[0:len(row[0])] == row[0]:
                return len(row[0])
        # return 4 as default length if not found (e.g. 0800)
        return 4

    # ---------------------------------------------------------
    # cli-section:
    # ---------------------------------------------------------

    def __get_cli_arguments__(self):
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
        parser.add_argument('-v', '--version',
                            action='version', version=__version__,
                            help='Print the program version')
        return parser.parse_args()

    def runSearch(self, s=''):
        if self.prefs['password'] != '':
            args.password = self.prefs['password']
        if args.password == '':
            logger.error('No password given')
            sys.exit(1)
        if args.password and type(args.password) == list:
            args.password = args.password[0].rstrip()
        calls = FritzCalls(
            self.connection, nameNotFoundList=self.nameNotFoundList)
        nameList = ''
        searchnumber = []
        if args.searchnumber:
            if type(args.searchnumber) == tuple:
                searchnumber += args.searchnumber
            else:
                searchnumber.append(args.searchnumber)
        if s:
            if type(s) == tuple:
                searchnumber += s
            else:
                searchnumber.append(s)
        if searchnumber:
            for number in searchnumber:
                logger.info("Searching for {}".format(number))
                contact = self.phonebook.get_entry(number=number)
                if not contact:
                    if number in self.nameNotFoundList:
                        logger.info(
                            '{} already in nameNotFoundList'.format(number))
                    else:
                        new = Call()
                        new.Name = number
                        calls.calldict.append(new)
                else:
                    for realName in contact['contact'].iter('realName'):
                        logger.info(
                            '%s = %s(%s)',
                            number,
                            args.phonebook,
                            realName.text,
                        )
                        nameList += realName.text.replace('& ', '&#38; ')+'\n'
        else:
            logger.error("Searchnumber nicht gesetzt")

        nameNotFoundList_length = len(self.nameNotFoundList)
        knownCallers = calls.get_names(self.nameNotFoundList)
        if len(self.nameNotFoundList) > nameNotFoundList_length:
            with open(self.notfoundfile, "w") as outfile:
                outfile.write("\n".join(self.nameNotFoundList))
        self.phonebook.add_entry_list(knownCallers)
        if s in knownCallers:
            nameList += knownCallers[s].replace('& ', '&#38; ')+'\n'
        elif not nameList:
            nameList = 'Nicht gefunden'
        return nameList


if __name__ == '__main__':
    FBS = FritzBackwardSearch()
#   to search for a number specify it in here:
# FBS.runSearch(s=('06131177282 (06131170)', ))
    FBS.runSearch()
