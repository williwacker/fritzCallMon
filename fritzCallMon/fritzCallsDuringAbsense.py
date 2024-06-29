#!/usr/bin/env python
# -*- coding: utf-8 -*-

import http.client
import logging
import os
import re
import urllib

import speech_recognition as sr
import urllib3
from fritzconnection.lib.fritzcall import FritzCall

logger = logging.getLogger(__name__)


class FritzCallsDuringAbsense():

	def __init__(self, connection, prefs):
		self.prefs = prefs
		self.areaCode = (connection.call_action('X_VoIP', 'GetVoIPCommonAreaCode'))['NewVoIPAreaCode']
		self.http = urllib3.PoolManager()
		self.callURLList = connection.call_action('X_AVM-DE_OnTel', 'GetCallList')
		entries = re.search("sid=(.*)$", self.callURLList['NewCallListURL'])
		self.sid = entries.group(0)
		self.FC = FritzCall(fc=connection)
		self.unresolved_list = []

	def get_sid(self):
		return self.sid

	def get_fullCode(self, code):
		if code == None or code[:1] == '0':
			return code
		else:
			return self.areaCode + code

	def set_unresolved(self, caller):
		self.unresolved_list.append(caller)

	def get_unresolved(self):
		for caller in self.unresolved_list:
#			calls = [
#				call for call in self.FC.get_calls(update=True, days=5)
#				if call.Type == "1" and call.Port == "40" and call.Path and call.Caller in caller]			
			calls = [
				call for call in self.FC.get_calls(update=True, days=5)
				if call.Type == "1" and call.Port == "40" and call.Caller in caller]
			calls += [
				call for call in self.FC.get_missed_calls(update=True, days=3)
				if call.Type == "2" and call.Caller in caller]
			calls = sorted(calls, key=lambda x: x.Date, reverse=True)
			for call in calls:
				self.process_notification(call)
				self.unresolved_list.remove(call.Caller)
				break

	def process_notification(self, call):
		phone_message = self.get_phone_message(call)
		logger.info("phone_message=%s", phone_message)
		self.pushover(self.get_message(call, phone_message))
		return

	def get_phone_message(self, call):
		phone_message = ""
		# if it is a phone message
		if call.Path:
			try:
				# build download link for phone message
				entries = re.search("(path=)(.*)", call.Path)
				dlpath = entries.group(2)
				dlfile = dlpath.split("/")
				response = self.http.request(
					'GET',
					f'{self.prefs["fritz_ip_address"]}/lua/photo.lua?{self.get_sid()}&myabfile={dlpath}'
				)
				wave = open(os.path.join(self.prefs['phone_msg_dir'], f'{dlfile[-1]}.wav'), 'wb')
				wave.write(response.data)
				wave.close()
				phone_message = self.speech_to_text(wave.name)
			except Exception as e:
				logger.error('Error in get_phone_message %s', e)
				self.pushover(f'Error in get_phone_message {e}')
		return phone_message

	def pushover(self, message):
		if self.prefs['pushover_token'] and self.prefs['pushover_userkey']:
			retry_count = 5
			retry = True
			while retry and retry_count > 0:
				try:
					conn = http.client.HTTPSConnection("api.pushover.net:443")
					conn.request("POST", "/1/messages.json",
								urllib.parse.urlencode({
									"token": self.prefs['pushover_token'],
									"user": self.prefs['pushover_userkey'],
									"message": message,
								}), {"Content-type": "application/x-www-form-urlencoded"})
					conn.getresponse()
					retry = False
				except Exception:
					retry_count -= 1
					logger.error("Pushover Error.", exc_info=True)

	def get_message(self, call, phone_message):
		text = '{} {} {} {}'.format(
			call.Date,
			call.Name,
			call.Caller,
			call.Called,
		)
		if phone_message:
			text += ' /Message: {}'.format(
				phone_message,
			)
		return text

	def speech_to_text(self, filename):
		retry_count = 5
		retry = True
		while retry and retry_count > 0:
			try:
				# initialize the recognizer
				r = sr.Recognizer()
				# open the file
				with sr.AudioFile(filename) as source:
					# listen for the data (load audio to memory)
					audio_data = r.record(source)
					# recognize (convert from speech to text)
					text = r.recognize_google(audio_data, language="de-DE")
					return text
				retry = False
			except Exception as e:
				retry_count -= 1
				logger.error('Error in speech_to_text %s', e)
				self.pushover(f'Error in speech_to_text {e}')

