#!/usr/bin/python
#
# Wrapper for Maemo's GPS.
# Copyright 2012 Pavel Machek <pavel@ucw.cz>, GPLv2

import location
import gobject
import datetime
import math

def is_nan(val):
	return (val != val)

def conv_val_to_nema(d):
	deg = math.floor(d)*100
	rest = (d*100.0 - deg)*0.6
	return deg+rest

def nema_checksum(string):
	csum = 0
	for i in string:
		csum = csum ^ ord(i)

	return csum

class Position:
	DEVICE = "liblocation"

	def __init__(self):
		self.debug = 0
		self.mode = 0
		self.time = ""
		self.ept = 0
		self.lat = 0
		self.lon = 0
		self.eph = 0
		self.altitude = 0
		self.epv = 0
		self.track = 0
		self.epd = 0
		self.speed = 0
		self.eps = 0 
		self.climb = 0
		self.epc = 0

		self.satellites_changed = False
		self.satellites = []
		self.satellites_in_use = 0
		self.satellites_in_view = 0
		
		self.timestamp = datetime.datetime(1970,1,1,0,0,0)
		self.activated = datetime.datetime.utcnow()

		self.thread_context = None

	def on_changed(self, device, data):

		if device.fix:
			if self.debug:
				print "fix: %s" % (str(device.fix))

			self.fix = device.fix
			self.mode = device.fix[0]

			if device.fix[1] & location.GPS_DEVICE_TIME_SET == location.GPS_DEVICE_TIME_SET:
				self.timestamp = datetime.datetime.utcfromtimestamp(device.fix[2])
				if is_nan(device.fix[3]):
					self.ept = 0
				else:
					self.ept = device.fix[3]

			if device.fix[1] & location.GPS_DEVICE_LATLONG_SET == location.GPS_DEVICE_LATLONG_SET:
				self.lat = device.fix[4]
				self.lon = device.fix[5]

				if is_nan(device.fix[6]):
					self.eph = 0
				else:
					self.eph = device.fix[6]

			if device.fix[1] & location.GPS_DEVICE_ALTITUDE_SET == location.GPS_DEVICE_ALTITUDE_SET:
				self.altitude = device.fix[7]

				if is_nan(device.fix[8]):
					self.epv = 0
				else:
					self.epv = device.fix[8]

			if device.fix[1] & location.GPS_DEVICE_TRACK_SET == location.GPS_DEVICE_TRACK_SET:
				self.track = device.fix[9]

			if device.fix[1] & location.GPS_DEVICE_SPEED_SET == location.GPS_DEVICE_SPEED_SET:
				self.speed = device.fix[11]
				if is_nan(device.fix[12]):
					self.eps = 0
				else:
					self.eps = device.fix[12]

			if device.fix[1] & location.GPS_DEVICE_CLIMB_SET == location.GPS_DEVICE_CLIMB_SET:
				self.climb = device.fix[13]
				if is_nan(device.fix[14]):
					self.epc = 0
				else:
					self.epc = device.fix[14]
				
		else:
			if self.debug:
				print "no fix", device.fix

		if device.satellites_in_use != self.satellites_in_use:
			self.satellites_changed = True

		elif device.satellites_in_view != self.satellites_in_view:
			self.satellites_changed = True

		elif len(device.satellites) != len(self.satellites):
			self.satellites_changed = True

		else:
			for i in range(0, len(device.satellites)):
				if device.satellites[i] != self.satellites[i]:
					self.satellites_changed = True
					break
				
		self.satellites = device.satellites
		self.satellites_in_use = device.satellites_in_use
		self.satellites_in_view = device.satellites_in_view

	def get_nema_lat(self):
		return conv_val_to_nema(abs(self.lat))
	
	def get_nema_lon(self):
		return conv_val_to_nema(abs(self.lon))

	def get_lat_dir(self):
		if self.lat >= 0:
			return 'N'
		else:
			return 'S'

	def get_lon_dir(self):
		if self.lon >= 0:
			return 'E'
		else:
			return 'W'

	def get_vel_knots(self):
		return self.speed * 1.852

	def get_vel_ms(self):
		return self.speed / 3.6

	def get_time_clock(self):
		time = self.timestamp
		return '%2.2i%2.2i%2.2i' % (time.hour, time.minute, time.second)

	def get_time_date(self):
		time = self.timestamp
		s_year = '%4.4i' % time.year
		return '%2.2i%2.2i%s' % (time.day, time.month, s_year[2:])

	def get_time_isoformat(self):
		time = self.timestamp
		ms = math.floor(time.microsecond*1000)/1000.0
		ms = "%.3f" % (ms)
		return "%04i-%02i-%02iT%02i:%02i:%02i.%sZ" % (time.year, time.month, time.day, time.hour, time.minute, time.second, ms[2:])

	def nema_gprmc(self):
		s_lat = '%4.4f,%s' % (self.get_nema_lat(), self.get_lat_dir())
		s_lon = '%5.5f,%s' % (self.get_nema_lon(), self.get_lon_dir())

		msg = 'GPRMC,%s,A,%s,%s,%.1f,%.1f,%s,0.0,E,A' % (self.get_time_clock(),s_lat,s_lon,self.get_vel_knots(),0.0,self.get_time_date())
		csum = nema_checksum(msg)
		msg = '$%s*%2.2X' % (msg,csum)
		return msg

	def nema_gpgga(self):
		s_lat = '%4.4f,%s' % (self.get_nema_lat(), self.get_lat_dir())
		s_lon = '%5.5f,%s' % (self.get_nema_lon(), self.get_lon_dir())

		msg = 'GPGGA,%s,%s,%s,1,24,1.0,%.1f,M,1.0,M,,' % (self.get_time_clock(),s_lat,s_lon,self.altitude)
		csum = nema_checksum(msg)
		msg = '$%s*%2.2X' % (msg,csum)
		return msg

	def gpsd_json_tpv(self):
		if self.mode < 2:
			asw = {
				"device" : Position.DEVICE,
				"mode" : self.mode,
				"track" : self.track,
				"time" : self.get_time_isoformat(),
				"tag" : "RMC",
				"class" : "TPV"
			}
		elif self.mode == 2:
			asw = {
				"lat" : self.lat,
				"lon" : self.lon,
				"device" : Position.DEVICE,
				"mode" : self.mode,
				"time" : self.get_time_isoformat(),
				"ept" : self.ept,
				"speed" : self.get_vel_ms(),
				"eps" : self.eps,
				"tag" : "RMC",
				"track" : self.track,
				"class" : "TPV"
			}

		elif self.mode == 3:
			asw = {
				"lat" : 51.30641833,
				"lon" : 12.37048666,
				"device" : Position.DEVICE,
				"mode" : self.mode,
				"alt" : self.altitude,
				"time" : self.get_time_isoformat(),
				"ept" : self.ept,
				"climb" : self.climb,
				"epc" : self.epc,
				"speed" : self.get_vel_ms(),
				"eps" : self.eps,
				"tag" : "RMC",
				"track" : self.track,
				"class" : "TPV"
			}
			
		return asw

	def nema_gpgsa(self):
		asw = "GPGSA,A,%i," % (self.mode)

		for i in range(0,14):
			if i < len(self.satellites):
				prn, _, _, _, used = self.satellites[i]
				if used == True:
					asw += "%i," % (prn)
				else:
					asw += ","
			else:
				asw += ","

		pdop = 0.0
		hdop = self.eph / 100.0
		vdop = self.epv / 100.0
		asw += "%f,%f,%f" % (pdop,hdop,vdop)
		
		csum = nema_checksum(asw)
		msg = '$%s*%2.2X' % (asw,csum)
		
		self.satellites_changed = False

		return msg

	def nema_gpgsv(self):
		msg = []

		idx = 0
		msgs = len(self.satellites)/3
		if math.floor(msgs) == 0.0:
			msgs = math.floor(msgs)
		else:
			msgs = math.floor(msgs)+1

		while idx < len(self.satellites):
			asw = "GPGSV,%i,%i,%i" % (msgs,int(idx/3)+1,len(self.satellites))

			for i in range(0,3):
				if idx < len(self.satellites):
					prn, elevation, azimuth, signal_strength, used = self.satellites[idx]
					if used == True:
						asw += ",%i,%i,%i,%02i" % (prn, elevation, azimuth, signal_strength)
					else:
						asw += ",%i,%02i,%03i,%02i" % (prn, elevation, azimuth, 0)
				else:
					asw += ",,,,"

				idx += 1
		
			csum = nema_checksum(asw)
			msg += ['$%s*%2.2X' % (asw,csum)]

		self.satellites_changed = False

		return msg

	def gpsd_json_sky(self):
		sat_list = []
		for prn, elevation, azimuth, signal_strength, used in self.satellites:
			sat_list += [{
				"PRN" : prn,
				"el" : elevation,
				"az" : azimuth,
				"ss" : signal_strength,
				"used" : (used == 1)
			}]

		asw = {
			"tag" : "GSV",
			"device" : Position.DEVICE,
			"time" : self.get_time_isoformat(),
			"satellites" : sat_list,
			"class" : "SKY"
		}

		self.satellites_changed = False

		return asw

	# Precision in cm
	def position_loop(self):
		def on_error(control, error, data):
			print "location error: %d... quitting" % error
			data.quit()

		def on_changed(device, data):
			if not device:
				return
			self.on_changed(device, data)

		def on_stop(control, data):
			data.quit()

		def start_location(data):
			data.start()
			self.thread_context.iteration(True)
			return False

		self.loop = gobject.MainLoop()
		# run threads smoother http://www.jejik.com/articles/2007/01/python-gstreamer_threading_and_the_main_loop/
		gobject.threads_init()
		self.thread_context = self.loop.get_context()
		

		self.control = location.GPSDControl.get_default()
		self.device = location.GPSDevice()
		self.control.set_properties(preferred_method=location.METHOD_USER_SELECTED,
					    preferred_interval=location.INTERVAL_DEFAULT)

		self.control.connect("error-verbose", on_error, self.loop)
		self.device.connect("changed", on_changed, self.control)
		self.control.connect("gpsd-stopped", on_stop, self.loop)

		gobject.idle_add(start_location, self.control)

		self.loop.run()

	def quit(self):
		self.loop.quit()


