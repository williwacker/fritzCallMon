# -*- coding: utf-8 -*-

import argparse
import copy
import html.parser
import logging
import re
import sys
from xml.etree.ElementTree import fromstring, tostring

import urllib3
from fritzconnection.lib.fritzphonebook import FritzPhonebook
from logs import get_logger
from prefs import read_configuration

logger = logging.getLogger(__name__)

__version__ = '0.3.3'

args = argparse.Namespace()
args.logfile = ''


class MyFritzPhonebook():

    def __init__(self, connection, name):
        self.logger = None
        self.prefs = read_configuration()
        self.connection = connection
        self.phonebook = FritzPhonebook(self.connection)
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
        for book_id in self.phonebook.phonebook_ids:
            phonebook_info = self.phonebook.phonebook_info(book_id)
            if phonebook_info['name'] == name:
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
                    self.logger.info('%s %s has been appended', name, number)
                else:
                    self.add_entry(number, name)
                    self.logger.info('%s %s has been added', name, number)

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
                    '<?xml version="1.0" encoding="utf-8"?>' +
                    '<Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" ' +
                    's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">' +
                    tostring(phonebookEntry).decode("utf-8") +
                    '</Envelope>'
            }
            self.connection.call_action(
                'X_AVM-DE_OnTel', 'SetPhonebookEntry', arguments=arg)

    def add_entry(self, phone_number, name):
        arg = {
            'NewPhonebookID': self.bookNumber,
            'NewPhonebookEntryID': '',
            'NewPhonebookEntryData':
                '<?xml version="1.0" encoding="utf-8"?>' +
                '<Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" ' +
                's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">' +
                '<contact><category>0</category><person><realName>' +
                name +
                '</realName></person><telephony nid="1"><number type="home" prio="1" id="0">' +
                phone_number +
                '</number></telephony></contact></Envelope>'
        }

        self.connection.call_action(
            'X_AVM-DE_OnTel:1', 'SetPhonebookEntry', arguments=arg)


# if __name__ == '__main__':
#    FPB = FritzPhonebook()
#   to search for a number specify it in here:
#    FPB.runSearch(s=('06322955681', ))
#    FBS.runSearch()
