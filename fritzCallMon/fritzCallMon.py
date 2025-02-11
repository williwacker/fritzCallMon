import datetime
import logging
import os
import socket
import sys
import threading
import time
from queue import Queue

# import root directory into python module search path
sys.path.insert(1, os.getcwd())  # noqa

from fritzconnection import FritzConnection

from fritzBackwardSearch import FritzBackwardSearch
from fritzCallsDuringAbsense import FritzCallsDuringAbsense
from logs import get_logger
from prefs import read_configuration

"""
Fritzbox Call Monitor

Adopted from here: http://dede67.bplaced.net/PhythonScripte/callmon/callmon.html

 - The thread (worker1) receives the CallMonitor messages from the Fritzbox and writes them to the fb_queue.

 - The thread (worker2) receives from the fb_queue and calls the FritzBackwardSearch class, which updates the Fritzbox phonebook

 - The message from the Fritzbox has the following flow:
   	- Message is received in thread runFritzboxCallMonitor()
   	- Message gets passed via self.fb_queue to the thread runFritzBackwardSearch()
   	- Message is received in runFritzBackwardSearch()
	 	- split message
	 	- call of the FritzBackwardSearch instance with passing the caller number
	- Message is received in runFritzCallsDuringAbsense()
		- if incoming call has't been accepted a pushover message with the callers name, number and phonemessage will be sent
"""


class CallMonServer():

    def __init__(self):
        self.logger = logging.getLogger()
        self.prefs = read_configuration()
        self.run()
        super().__init__()

    def run(self):
        self.logger = get_logger()

        # initialize FB connection
        if self.prefs['password'] == '':
            self.logger.error('No password given')
            sys.exit(1)
        self.connection = FritzConnection(
            address=self.prefs['fritz_ip_address'],
            port=self.prefs['fritz_tcp_port'],
            user=self.prefs['fritz_username'],
            password=self.prefs['password'])
        # Meldungs-Übergabe von runFritzboxCallMonitor() an runFritzBackwardSearch()
        self.fb_queue = Queue()
        self.fb_absense_queue = Queue()

        self.FBS = FritzBackwardSearch()
        self.FCDA = FritzCallsDuringAbsense(self.connection)
        self.startFritzboxCallMonitor()

    # self.FCDA.set_unresolved('01772429352')

    # ###########################################################
    # Empfangs-Thread und Verarbeitungs-Thread aufsetzen.
    # Funktion verändert:
    #   startet zwei Threads
    # ###########################################################
    def startFritzboxCallMonitor(self):
        worker1 = threading.Thread(
            target=self.runFritzboxCallMonitor, name="runFritzboxCallMonitor")
        worker1.daemon = True
        worker1.start()

        worker2 = threading.Thread(
            target=self.runFritzBackwardSearch, name="runFritzBackwardSearch")
        worker2.daemon = True
        worker2.start()

        worker3 = threading.Thread(
            target=self.runFritzCallsDuringAbsense, name="runFritzCallsDuringAbsense")
        worker3.daemon = True
        worker3.start()

    # ###########################################################
    # Running as Thread.
    # Make connection to Fritzbox, receive messages from the Fritzbox and pass over to queue
    # ###########################################################
    def runFritzboxCallMonitor(self):
        while True:  # Socket-Connect-Loop
            self.recSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                self.recSock.connect(
                    (self.prefs['fritz_ip_address'], int(self.prefs['fritz_callmon_port'])))
            except socket.herror as e:
                self.logger.error("socket.herror %s", e)
                time.sleep(10)
                continue
            except socket.gaierror as e:
                self.logger.error("socket.gaierror %s", e)
                time.sleep(10)
                continue
            except socket.timeout as e:
                self.logger.error("socket.timeout %s", e)
                continue
            except socket.error as e:
                self.logger.error("socket.error %s", e)
                time.sleep(10)
                continue
            except Exception as e:
                self.logger.error("%s", e)
                time.sleep(10)
                continue
            self.logger.info(
                "The connection to the Fritzbox call monitor has been established!")

            while True:  # Socket-Receive-Loop
                try:
                    ln = self.recSock.recv(256).strip()
                except:
                    ln = ""

                if ln != "":
                    self.fb_queue.put(ln)
                    self.fb_absense_queue.put(ln)
                else:
                    self.logger.info(
                        "The connection to the Fritzbox call monitor has been stopped!")
                    self.fb_queue.put("CONNECTION_LOST")
                    break   # back to the Socket-Connect-Loop

    # ###########################################################
    # Running as Thread.
    # Make connection to Fritzbox, do backwardsearch for callers number
    # ###########################################################
    def runFritzBackwardSearch(self):
        while True:
            time.sleep(0.01)
            msgtxt = self.fb_queue.get()
            if not (msgtxt in ("CONNECTION_LOST", "REFRESH")):
                msg = msgtxt.decode().split(';')
                if msg[1] == "RING":
                    self.FBS._runSearch(s=msg[3])
                if msg[1] == "CALL":
                    self.FBS._runSearch(s=msg[5])

    # ###########################################################
    # Running as Thread.
    # Make connection to Fritzbox and retrieve the answering machine message, and inform via Pushover
    # ###########################################################
    def runFritzCallsDuringAbsense(self):
        call_history = {}
        while True:
            time.sleep(0.01)
            msgtxt = self.fb_absense_queue.get()
            self.logger.info(msgtxt)
            if not (msgtxt in ("CONNECTION_LOST", "REFRESH")):
                # RING;ID;CALLER;CALLED;
                # CONNECT;ID;PORT;CALLER;
                # DISCONNECT;ID;SECONDS;
                call_type, call_id, caller_or_port = msgtxt.decode().split(';')[
                    1:4]
                if call_type == "RING":
                    call_history[call_id] = caller_or_port
                    self.logger.info(call_history)
                elif call_type == "CONNECT":
                    self.logger.info(call_history)
                    if call_id in call_history:
                        del call_history[call_id]
                elif call_type == "DISCONNECT":
                    if call_id in call_history:
                        self.logger.info(call_history)
                        self.logger.info('calling FCDA %s',
                                         call_history[call_id])
                        self.FCDA.set_unresolved(call_history[call_id])
                        del call_history[call_id]

    # ###########################################################
    # Start fritzCallMon Server
    # ###########################################################
    def runServer(self):
        self.srvSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srvSock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.srvSock.bind(("", int(self.prefs['callmon_server_socket'])))
            self.srvSock.listen(5)
        except Exception as e:
            self.logger.error("Cannot open socket %s : %s",
                              self.prefs['callmon_server_socket'], e)
            return
        self.logger.info('%s has been started', __class__.__name__)
        while True:
            try:
                self.srvSock.listen(5)
                time.sleep(0.01)
            except Exception:
                self.logger.info('has been stopped')
                sys.exit()

            now = datetime.datetime.now()
            if now.minute % 1 == 0 and now.second == 0:
                self.FCDA.get_unresolved()
                time.sleep(1)


if __name__ == '__main__':
    CallMonServer().runServer()
