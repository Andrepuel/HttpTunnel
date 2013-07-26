import daemon

import urllib.request
import urllib.parse

def server_action(host,action,post):
	result = urllib.request.urlopen(host+'?'+urllib.parse.urlencode({"action":action}),urllib.parse.urlencode(post).encode('ascii')).read()
	debug("Server action %s /action=%s with %r gave %r" % (host,action,post,result) )
	return result

# Based on:
"""Minimal non-feature complete socks proxy""" #https://github.com/argandgahandapandpa/minimal_python_socks

import logging
from logging import error, info, debug
import random
import socket
from socketserver import StreamRequestHandler, ThreadingTCPServer
from struct import pack, unpack
import threading
import datetime
import time

CLOSED = object()
WAIT_TIME=0.001
class SocketHttpTranslator(threading.Thread):
	def __init__(self,host,result_number):
		threading.Thread.__init__(self)
		self.data = b""
		self.recvd = b""
		self.lock = threading.Lock()
		self.closed = False
		self.remote_closed = False

		self.host = host
		self.result_number = result_number

	def send(self,data):
		self.lock.acquire()
		try:
			if self.closed:
				raise IOError("Connection is closed, not allowed to send more data")
			while len(self.data) >= daemon.BUFFER_SIZE:
				self.lock.release()
				time.sleep(0)
				self.lock.acquire()
			self.data += data
		finally:
			self.lock.release()

	def send_close(self):
		self.lock.acquire()
		try:
			self.closed = True
		finally:
			self.lock.release()

	def recv(self):
		self.lock.acquire()
		try:
			if len(self.recvd) == 0:
				return (self.remote_closed,b"")
			result = self.recvd
			self.recvd = b""
			return (True,result)
		finally:
			self.lock.release()

	def run(self):
		last_sent = datetime.datetime.now()
		wait_time = 0
		while True:
			now = datetime.datetime.now()
			to_send = b""
			should_send = False
			self.lock.acquire()
			try:
				if len(self.data) == 0 and self.closed:
					to_send = CLOSED
					should_send = True
				elif (now-last_sent).total_seconds() >= wait_time or len(self.data) > 1024 or self.closed:
					to_send = self.data
					self.data = b""
					should_send = True
			finally:
				self.lock.release()

			result = b""
			if not should_send:
				time.sleep(0)
				continue
			if to_send is CLOSED:
				result = server_action(self.host,"close",{"result_number":str(self.result_number)})
			else:
				result = server_action(self.host,"sync",{"result_number":str(self.result_number),"data":to_send})
			last_sent = datetime.datetime.now()

			wait_time = WAIT_TIME
			if result[0:1] == daemon.DATA:
				(size,) = unpack(">I",result[1:5])
				if size > 0:
					wait_time = 0
					self.lock.acquire()
					try:
						self.recvd += result[5:5+size]
					finally:
						self.lock.release()
			elif result[0:1] == daemon.CONNECTION_CLOSED:
				self.lock.acquire()
				try:
					self.remote_closed = True
				finally:
					self.lock.release()
				return
			elif result[0:1] == daemon.ERROR:
				(size,) = unpack(">I",result[1:5])
				raise BaseException("Error on http communication, server sent: %s" % result[5:5+size].decode("utf8"))
			else:
				raise BaseException("Server sent an unknown response (%r)" % result)

			if to_send is CLOSED:
				return
			

CLOSE = object()

logging.getLogger().setLevel(logging.INFO)

VERSION = b'\x05'
NOAUTH = b'\x00'
CONNECT = b'\x01'
IPV4 = b'\x01'
IPV6 = b'\x04'
DOMAIN_NAME = b'\x03'
SUCCESS = b'\x00'

def forward(local_source, http):
	while True:
		(has_data,data) = daemon._recv_if_has_data(local_source)
		if has_data:
			if data == b'':
				http.send_close()
				local_source.close()
				return
			else:
				http.send(data)
		(has_data,data) = http.recv()
		if has_data:
			if data == b'':
				local_source.close()
				return
			else:
				local_source.sendall(data)
		time.sleep(0.001)

class SocksHandler(StreamRequestHandler):
	"""Highly feature incomplete SOCKS 5 implementation"""

	def close_request(self):
		self.server.close_request(self.request)

	def read(self, n):
		data = b''
		while len(data) < n:
			extra = self.rfile.read(n)
			if extra == b'':
				raise Exception('Connection closed')
			data += extra
		return data

	def handle(self):
		http_address = self.server.http_address
		(protocol,address) = http_address.split("//")
		(host,*path) = address.split("/")
		(host,port,*unused) = (host.split(":") + ["80"])
		host = list(map(int,socket.gethostbyname(host).split(".")))
		port = int(port)
		assert len(host) == 4

		# IMRPOVEMENT: Report who requests are from in logging
		# IMPROVEMENT: Timeout on client
		info('Connection - authenticating')
		version = self.read(1)

		if version != b'\x05':
			error('Wrong version number (%r) closing...' % version)
			self.close_request()
			return

		nmethods = ord(self.read(1))
		method_list = self.read(nmethods)

		if NOAUTH not in method_list:
			error('Server only supports NOAUTH')
			self.send_no_method()
			return
		else:
			self.send_no_auth_method()
			info('Authenticated')

		# If we were authenticating it would go here
		version = self.read(1)
		cmd = self.read(1)
		zero = self.read(1)
		address_type = self.read(1)
		if version != b'\x05':
			error('Wrong version number (%r) closing...' % version)
			self.close_request()
		elif cmd != CONNECT:
			error('Only supports connect method not (%r) closing' % cmd)
			self.close_request()
		elif zero != b'\x00':
			error('Mangled request. Reserved field (%r) is not null' % zero)
			self.close_request()

		if address_type == IPV4:
			raw_dest_address = self.read(4)
			dest_address = '.'.join(map(str, unpack('>4B', raw_dest_address)))
		elif address_type == IPV6:
			raise BaseException("IPV6 not supported") 
		elif address_type == DOMAIN_NAME:
			dns_length = ord(self.read(1))
			dns_name = self.read(dns_length)
			dest_address = dns_name
		else:
			error('Unknown addressing (%r)' % address_type)
			self.close_request()
			return
		
		raw_dest_port = self.read(2)
		(dest_port,) = unpack(">H",raw_dest_port)

		result = server_action(http_address,"create",{"dest_address":dest_address,"dest_port":dest_port})
		if result[0:1] == daemon.ERROR:
			(size,) = unpack(">I",result[1:5])
			error("Error on creating connection: %s" % result[5:5+size])
		if result[0:1] != daemon.OKAY:
			error("Unknown error on creating connection (%r)" % result)
			self.close_request()
			return
		(result_number,) = unpack(">I",result[1:5])

		debug("Created forwarder connection to %r:%r on %r" % (dest_address,dest_port,result_number))

		self.send_reply(host,port)

		http = SocketHttpTranslator(http_address,result_number)
		http.start()
		forward(self.request, http)

	def send_reply(self,host,port):
		full_address = host + [port]
		info('Setting up forwarding port %r' % (full_address,))
		msg = pack('>cccc4BH', VERSION, SUCCESS, b'\x00', IPV4, *full_address)
		self.wfile.write(msg)

	def send_no_method(self):
		self.wfile.write(b'\x05\xff')
		self.close_request()

	def send_no_auth_method(self):
		self.wfile.write(b'\x05\x00')
		self.wfile.flush()

class SocksServer(ThreadingTCPServer):
	allow_reuse_address = True
	def __init__(self,http_address,binding):
		self.http_address = http_address
		ThreadingTCPServer.__init__(self,binding,SocksHandler)

