import argparse
import copy
import datetime
import html.parser
import logging
import os
import re
import sys
from ast import literal_eval
from xml.etree.ElementTree import fromstring, tostring

import certifi
import urllib3
from fritzconnection import FritzConnection
from fritzconnection.lib.fritzcall import Call, FritzCall
from fritzconnection.lib.fritzphonebook import FritzPhonebook
from prefs import read_configuration
from logs import get_logger

logger = logging.getLogger(__name__)

__version__ = '0.3.3'

args = argparse.Namespace()
args.logfile = ''


class FritzCalls():

    def __init__(self, connection, nameNotFoundList):
        self.logger = None
        self.connection = connection
        self.nameNotFoundList = nameNotFoundList
        self.prefs = read_configuration()
        self.unknownCallers = {}
        self.onkz = []

        self.run()
        super().__init__()

    def run(self):
        self.logger = get_logger()
        self.logger.info('%s has been started', __class__.__name__)

        self.http = urllib3.PoolManager(
            cert_reqs='CERT_REQUIRED', ca_certs=certifi.where())
        self.areaCode = (self.connection.call_action(
            'X_VoIP', 'GetVoIPCommonAreaCode'))['NewVoIPAreaCode']
        self.calldict = FritzCall(fc=self.connection).get_calls()
        self.get_unknown()
        self.__read_ONKz__()

    def get_unknown(self):  # get list of callers not listed with their name
        for i in range(len(self.calldict)-1, -1, -1):
            if self.calldict[i].Id is None:
                del self.calldict[i]
                continue
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

    def __read_ONKz__(self):  # read area code numbers
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
            logger.error('%s not found', fname)

    def get_ONKz_length(self, phone_number):
        for row in self.onkz:
            if phone_number[0:len(row[0])] == row[0]:
                return len(row[0])
        # return 4 as default length if not found (e.g. 0800)
        return 4

    def only_numerics(self, seq):
        if seq:
            seq_type = type(seq)
            return seq_type().join(filter(seq_type.isdigit, seq))
        return ''

    def get_names(self, nameNotFoundList):
        foundlist = {}
        for call in self.calldict:
            number = self.only_numerics(call.Name)
            origNumber = number
            # remove international numbers
            if number.startswith("00"):
                fullNumber = ""
                logger.info("Ignoring international number %s", number)
                nameNotFoundList.append(number)
            # remove pre-dial number for mobile
            elif number.startswith("010"):
                m = re.search("^010\d*?(01(5|6|7)\d+)", number)
                if m:
                    number = m.group(1)
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
            l_onkz = self.get_ONKz_length(fullNumber)
            while (name is None and len(fullNumber) > (l_onkz + 3)):
                name = self.lookup_dasoertliche(fullNumber)
                if not name:
                    logger.info('%s not found', fullNumber)
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

    def _init_dict(self, transTable):
        data_dict = {}
        for m in transTable.values():
            data_dict[m] = ''
        return data_dict

    def lookup_dasoertliche(self, number):
        transTable = {'pc': 'pc', 'na': 'na', 'ci': 'ci', 'st': 'st',
                                  'hn': 'hn', 'ph': 'ph', 'mph': 'mph', 'recuid': 'recuid'}
        url = 'https://www.dasoertliche.de/Controller?form_name=search_inv&ph={}'.format(
            number)
        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/54.0.2840.90 Safari/537.36'}
        response = self.http.request('GET', url, headers=headers)
        content = response.data.decode("utf-8", "ignore") \
            .replace('\t', '').replace('\n', '').replace('\r', '').replace('&nbsp;', ' ')
        if content.find('keine Treffer finden') > -1:
            return
        try:
            handlerData = literal_eval(
                (re.search('handlerData\s*=\s*(.*?);', content).group(1)).replace("null", "None"))
            # item list matching to address list
            itemList = re.search(
                'var item = {(.*?)};', content).group(1).split(',')
            for m in range(len(handlerData)):
                data_dict = self._init_dict(transTable)
                for singleItem in itemList:
                    item = singleItem.split(':', 1)
                    if item[0].strip() in transTable:
                        i_id = transTable[item[0].strip()]
                        if i_id == 'ph':
                            phone = eval(item[1]).replace('(', '').replace(
                                ')', '-').replace(' ', '-', 1).replace(' ', '')
                            if phone[:3] in ('015', '016', '017'):
                                data_dict['mph'] = phone
                            else:
                                data_dict['ph'] = phone
                        else:
                            data_dict[i_id] = eval(item[1])
            return data_dict['na']
        except Exception:
            logger.error("Telefonbuchsuche DasOertliche error", exc_info=True)


class MyFritzPhonebook():

    def __init__(self, connection, name):
        self.logger = None
        self.prefs = read_configuration()
        self.connection = connection
        self.bookNumber = None
        self.phonebookEntries = None
        self.run(name)
        super().__init__()

    def run(self, name):
        self.logger = get_logger()
        self.logger.info('%s has been started', __class__.__name__)

        self.http = urllib3.PoolManager()
        if name and isinstance(name, list):
            name = name[0]
        for book_id in FritzPhonebook(self.connection).phonebook_ids:
            book = FritzPhonebook(self.connection).phonebook_info(book_id)
            if book['name'] == name:
                self.bookNumber = book_id
                break
        if not self.bookNumber:
            logger.error('Phonebook: %s not found !', name)
            sys.exit(1)

    def get_phonebook(self):
        response = self.http.request('GET', self.connection.call_action(
            'X_AVM-DE_OnTel', 'GetPhonebook', NewPhonebookID=self.bookNumber)['NewPhonebookURL'])
        self.phonebookEntries = fromstring(
            re.sub("!-- idx:(\d+) --", lambda m: "idx>"+m.group(1)+"</idx", response.data.decode("utf-8")))

    def get_entry(self, name=None, number=None, uid=None, contact_id=None):
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
            elif contact_id is not None:
                phone_entry = fromstring(self.connection.call_action(
                    'X_AVM-DE_OnTel', 'GetPhonebookEntry', NewPhonebookID=self.bookNumber,
                    NewPhonebookEntryID=contact_id)['NewPhonebookEntryData'])
                return {'contact_id': contact_id, 'contact': phone_entry}

    def add_entry_list(self, entry_list):
        if entry_list:
            for number, name in entry_list.items():
                entry = self.get_entry(name=name)
                if entry:
                    self.append_entry(entry, number)
                else:
                    self.add_entry(number, name)

    def append_entry(self, entry, phone_number):
        phonebookEntry = self.get_entry(
            contact_id=entry['contact_id'])['contact']
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
        if not newnumber is None:
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


class FritzBackwardSearch():

    def __init__(self):
        self.logger = None
        self.prefs = read_configuration()
        self.nameNotFoundList = []
        self.run()
        super().__init__()

    def run(self):
        self.logger = get_logger()
        self.logger.info('%s has been started', __class__.__name__)

        global args
        args = self.__get_cli_arguments__()
        self.connection = FritzConnection(
            address=args.address,
            port=args.port,
            user=args.username,
            password=args.password)
        self.phonebook = MyFritzPhonebook(self.connection, name=args.phonebook)
        self.phonebook.get_phonebook()
        self.notfoundfile = args.notfoundfile
        if args.notfoundfile and isinstance(args.notfoundfile, list):
            self.notfoundfile = args.notfoundfile[0]
        try:
            self.nameNotFoundList = open(
                self.notfoundfile, encoding='utf-8', mode='r').read().splitlines()
        except:
            self.nameNotFoundList = open(
                self.notfoundfile, encoding='utf-8', mode='w+').read().splitlines()

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
        if args.password and isinstance(args.password, list):
            args.password = args.password[0].rstrip()
        calls = FritzCalls(
            self.connection, self.nameNotFoundList)
        nameList = ''
        searchnumber = []
        if args.searchnumber:
            if isinstance(args.searchnumber, tuple):
                searchnumber += args.searchnumber
            else:
                searchnumber.append(args.searchnumber)
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
                    if number in self.nameNotFoundList:
                        logger.info(
                            '%s already in nameNotFoundList', number)
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
            with open(self.notfoundfile, encoding='utf-8', mode="w") as outfile:
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
#    FBS.runSearch(s=('06359911', ))
    FBS.runSearch()
