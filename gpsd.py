#!/usr/bin/env python 
#
# gpsd-locapi - A simple GPSd compatible server based on Maemo 5 location api
# Copyright 2012, debloxxx <debloxxx@googlemail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
 

# Thanks to Pavel Machek <pavel@ucw.cz> for his simple gpsd server
# Original source http://tui.cvs.sourceforge.net/viewvc/tui/tui/maemo/gpsd.py?view=log
#
# some documentation links
# - GPSd Protocol http://catb.org/gpsd/gpsd_json.html
# - Maemo Location API http://wiki.maemo.org/PyMaemo/Using_Location_API

import socket
import threading
import time
import datetime
import gps
import simplejson as json
import math
import sys

# BUGFIX: libgps will not accept JSON data like {"class": "TPV"} -> only {"class":"TPV"}
def correct_jsonstring4libgps(jsondata):
	if jsondata == None:
		return jsondata

	return jsondata.replace("\": ", "\":")

class GpsdClient(threading.Thread):
	MAX_SIZE = 1024

	def __init__(self, Sock, Provider):
		self.client_socket = Sock
		self.gps = Provider
		self.request_type = -1
		self.watch_mode = False
		self.question_mark_set = False
		self.json_mode = True 
		self.nmea_mode = False
		self.raw_mode = -1
		self.interval = 1

		threading.Thread.__init__(self)

	def handle_request(self, data):
		print "request: \"%s\"" % (str(data))

		if len(data) == 0:
			return 1
		
		# gpsd "?" requests
		if len(data) == 1:
			if data[0] == "?":
				self.question_mark_set = True
				return 0

			if data[1] == "w":
				self.watch_mode = True
				return 0

		begin = data.find('WATCH=')
		begin_json = data.find('{')
		end_json = data.find('}')
		if begin >= 0 and begin <= 1:

			if begin_json >= 0 and end_json > begin_json:
				print 'WATCH request in json format: '
				req_json = data[begin_json:][:end_json-begin_json+1]
				req_json = json.loads(req_json)
				print req_json

				if req_json.has_key('class') == True and req_json['class'] == "WATCH":
					return 0

				if req_json.has_key('json') == True:
					self.json_mode = req_json['json']
				else:
					self.json_mode = True

				if req_json.has_key('enable') == True:
					self.watch_mode = req_json['enable']
				else:
					self.watch_mode = True
				
				if req_json.has_key('nmea') == True:
					self.nmea = req_json['nmea']
				else:
					self.nmea = False
				
				if req_json.has_key('raw') == True:
					self.raw_mode = req_json['raw']
				else:
					self.raw_mode = -1

			else:
				print 'WATCH request'
				self.json_mode = True
				self.nmea = False
				self.watch_mode = True
			
			if self.raw_mode > 0:
				self.json_mode = False

			if self.json_mode == True:
				self.raw_mode = 0

			self.answer_device()
			self.answer_watch()

			return 0

		if data.find('POLL') >= 0:
			self.answer_postion()
			return 0

		if data.find('VERSION') >= 0:
			self.answer_version()
			return 0

		if data.find('SKY') >= 0:
			self.answer_satellites()
			return 0


		self.question_mark_set = False

		self.answer_error()
		return 1

	def answer_version(self):
		asw = {
			"release" : "0.1",
			"proto_major" : 3,
			"proto_minor" : 1,
			"class" : "VERSION"
		}
		asw = "%s\r\n" % (json.dumps(asw))
		asw = correct_jsonstring4libgps(asw)

		self.client_socket.send(asw)

		return 0

	def answer_postion(self):
		asw = ""

		if self.json_mode == True:
			asw = "%s\r\n" % (json.dumps(self.gps.pos.gpsd_json_tpv(), allow_nan=False, ensure_ascii=True, indent=False))
			asw = correct_jsonstring4libgps(asw)
			print 'sending json answer : %s' % (asw)
	
		else:
			asw  = "%s\r\n" % (self.gps.pos.nema_gprmc()) 
			asw += "%s\r\n" % (self.gps.pos.nema_gpgga()) 

			print 'sending nmea answer : %s' % (asw)
		
		self.client_socket.send(asw)

		return 0

	def answer_satellites(self):
		asw = ""

		if self.json_mode == True:
			asw = "%s\r\n" % (json.dumps(self.gps.pos.gpsd_json_sky(), allow_nan=False))
			asw = correct_jsonstring4libgps(asw)
			print 'sending json answer : %s' % (asw)
		else:
			asw = "%s\r\n" % (self.gps.pos.nema_gpgsa())
			for i in self.gps.pos.nema_gpgsv():
				asw += "%s\r\n" % (i)

		self.client_socket.send(asw)
		return 0

	def answer_error(self):
		if self.json_mode == True:
			asw = {
				"class" : "ERROR",
				"message" : "Don't understand request"
			}
			asw = "%s\n" % (json.dumps(asw))
			asw = correct_jsonstring4libgps(asw)
		else:
			asw = "Error\r\n"
		
		try:
			if self.client_socket.send(asw) != len(asw):
				print 'Error while sending'
				return 1
		except:
			print 'Error while sending'
			return 1

		return 0

	def answer_device(self):
		#if self.json_mode == True:
		asw = {
			"devices" : [ {
				"activated" : self.gps.pos.activated.isoformat()+"Z",
				"cycle" : self.interval,
				"native" : 0, # no, I only speek NEMA
				"bps" : 9600, # a must have
				"parity" : "N", #  a must have
				"stopbits" : 1, # a must have
				"flags" : 1, # my language is GPS data
				"driver" : "Generic NEMA", # yes, I can speek NEMA
				"path" : gps.Position.DEVICE,
				"class" : "DEVICE"
			} ],
			"class" : "DEVICES"
		}
		asw = "%s\n" % (json.dumps(asw))
		# BUGFIX: libgps will not accept JSON data with entries like >"KEY":_SPACE_"VALUE"< 
		asw = correct_jsonstring4libgps(asw)

		self.client_socket.send(asw)

		return 0

	def answer_watch(self):
		if self.json_mode == True:
			asw = {
				"json" : self.json_mode,
				"raw" : self.raw_mode,
				"enable" : self.watch_mode,
				"nmea" : self.nmea_mode,
				"scaled" : False,
				"timing" : False,
				"device" : gps.Position.DEVICE,
				"class" : "WATCH"
			}
			asw = "%s\n" % (json.dumps(asw))
			asw = correct_jsonstring4libgps(asw)

			self.client_socket.send(asw)

		return 0

	def run(self):
		self.client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
		self.client_socket.settimeout(self.interval)
		self.answer_version()

		auto_cycle = 0

		while True:
			data = []
			try:
				data = self.client_socket.recv(GpsdClient.MAX_SIZE)
				if data == '':
					print 'Closed client connection -> terminate'
					break
				else:
					print 'Got request ... handling it'
					self.handle_request(data)

			except socket.timeout:
				if self.watch_mode == True:
					print 'watch mode set -> sending default answer on timeout'
					if self.gps.pos.satellites_changed or auto_cycle == 0:
						self.answer_satellites()
					self.answer_postion()
			
					auto_cycle += 1

			except KeyboardInterrupt:
				print 'Keyboard interrupt'
				break

		self.client_socket.close()
					
class GpsProvider(threading.Thread):
	def __init__(self):
		threading.Thread.__init__(self)
		self.pos = gps.Position()

	def run(self):
		self.pos.position_loop()

# TODO: add command line options for port, interface, etc.
if __name__ == "__main__":
	print "Starting GPSd"
	prov = GpsProvider()
	prov.start()

	print "Starting network server"
	host = '' 
	port = 2947 
	backlog = 5

	s = socket.socket(socket.AF_INET, socket.SOCK_STREAM) 
	s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	s.settimeout(0.5)
	print "Bind to port"
	s.bind((host,port)) 
	print "Listening on network"
	s.listen(backlog)

	while True: 
		print "Waiting for clients"
		try:
			client, address = s.accept()
			print "New client connected"
			GpsdClient(client, prov).start()

		except KeyboardInterrupt:
			prov.pos.quit()
			prov.join(1)
			break

		except socket.timeout:
			pass

	sys.exit(0)

