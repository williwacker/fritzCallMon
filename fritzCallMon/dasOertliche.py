# -*- coding: utf-8 -*-

import logging
import os
import re
import sys
from ast import literal_eval

import certifi
import urllib3

# import root directory into python module search path
sys.path.insert(1, os.getcwd())  # noqa

from logs import get_logger

logger = logging.getLogger(__name__)


class DasOertliche():
    """
    Reverse Lookup of a given number using DasOertliche.de
    """

    def __init__(self, lookup_number):
        self.logger = get_logger()
        self.name = self._lookup_dasoertliche(lookup_number)

    def _init_dict(self):
        transTable = ['pc', 'na', 'ci', 'st', 'hn', 'ph', 'mph', 'recuid']
        data_dict = {}
        for key in transTable:
            data_dict[key] = ''
        return data_dict

    def _lookup_dasoertliche(self, number):
        http = urllib3.PoolManager(
            cert_reqs='CERT_REQUIRED', ca_certs=certifi.where())
        url = f'https://www.dasoertliche.de/Controller?form_name=search_inv&ph={number}'
        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/54.0.2840.90 Safari/537.36'}
        response = http.request('GET', url, headers=headers)
        content = response.data.decode("utf-8", "ignore") \
            .replace('\t', '').replace('\n', '').replace('\r', '').replace('&nbsp;', ' ')
        if content.find('keine Treffer finden') > -1:
            return
        try:
            handlerData = literal_eval(
                (re.search(r'handlerData\s*=\s*(.*?);', content).group(1)).replace("null", "None"))
            # item list matching to address list
            itemList = re.search(
                'var item = {(.*?)};', content).group(1).split(',')
            for m in range(len(handlerData)):
                data_dict = self._init_dict()
                for singleItem in itemList:
                    item = singleItem.split(':', 1)
                    i_id = item[0].strip()
                    if i_id in data_dict.keys():
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


if __name__ == '__main__':
    DO = DasOertliche(lookup_number='012345678')
    print(DO.name)
