import daemon

import urllib.parse

from client import http_client

def server_action(host,action,post):
	request = http_client.HTTPRequest(host,{"action":action},post)
	result = b""
	while True:
		more = request.recv(daemon.BUFFER_SIZE)
		if more == b"":
			return result
		result += more

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
BUFFER_SIZE=1024

class DataBuffer:
	def __init__(self,max_size=BUFFER_SIZE*4):
		self.lock = threading.Condition()
		self.data = b""
		self.max_size=max_size

	def length(self):
		self.lock.acquire()
		try:
			return len(self.data)
		finally:
			self.lock.release()

	def get(self):
		self.lock.acquire()
		try:
			while not self.data is CLOSED and len(self.data) == 0:
				self.lock.wait()
			if self.data is CLOSED:
				return b""
			result = self.data
			self.data = b""
			return result
		finally:
			self.lock.notifyAll()
			self.lock.release()
	
	def append(self,data):
		while True:
			self.lock.acquire()
			if self.data is CLOSED:
				raise RuntimeError("Buffer is closed")
			i=0
			try:
				remaining = self.max_size-len(self.data)
				if remaining > 0:
					self.data += data[i:i+remaining]
					i += remaining
				if i >= len(data):
					return
			finally:
				self.lock.notifyAll()
				self.lock.release()
	
	def close(self):
		self.lock.acquire()
		try:
			while not self.data is CLOSED and len(self.data) > 0:
				self.lock.wait()
			self.data = CLOSED
			self.lock.notifyAll()
		finally:
			self.lock.release()
	
	def is_closed(self):
		self.lock.acquire()
		try:
			return self.data is CLOSED
		finally:
			self.lock.release()

class SocketHttpTranslator(threading.Thread):
	def __init__(self,host,result_number):
		threading.Thread.__init__(self)
		self.send_buffer = DataBuffer()
		self.recv_buffer = DataBuffer()
		self.remote_closed = False

		self.host = host
		self.result_number = result_number

	def is_closed(self):
		return self.send_buffer.is_closed() or self.recv_buffer.is_closed()

	def start(self):
		sender = threading.Thread(target=self.send_thread)
		sender.start()
		threading.Thread.start(self)

	def send(self,data):
		self.send_buffer.append(data)

	def send_close(self):
		self.send_buffer.close()

	def recv(self):
		return self.recv_buffer.get()

	def run(self):
		self.recv_thread()

	def send_thread(self):
		while True:
			to_send = self.send_buffer.get()
			if to_send == b"":
				#Receiver closes
				return
			else:
				server_action(self.host,"send",{"result_number":self.result_number,"data":to_send})

	def recv_thread(self):
		last_sent = datetime.datetime.now()
		wait_time = 0
		while True:
			now = datetime.datetime.now()
			if (now-last_sent).total_seconds() < wait_time:
				time.sleep(0)
				continue
			request = http_client.HTTPRequest(self.host,{"action":"recv"},{"result_number":str(self.result_number)})
			wait_time = WAIT_TIME
			while True:
				result_type = request.recv(1)
				if result_type == b'':
					break
				elif result_type == daemon.DATA:
					(size,) = unpack(">I",daemon._recv_exactly(request,4))
					if size > 0:
						wait_time = 0
						while size > 0:
							result = request.recv(min(BUFFER_SIZE,size))
							if result == b'':
								raise IOError("Connection unexpectedly closed")
							size -= len(result)
							self.recv_buffer.append(result)
				elif result_type == daemon.CONNECTION_CLOSED:
					self.recv_buffer.close()
					self.send_buffer.close()
				elif result_type == daemon.ERROR:
					(size,) = unpack(">I",daemon._recv_exactly(request,4))
					raise BaseException("Error on http communication, server sent: %s" % daemon._recv_exactly(request,size).decode("utf8"))
				else:
					raise BaseException("Server sent an unknown response %r" % (result_type+request.recv(4096)))
			last_sent = datetime.datetime.now()
			if self.send_buffer.is_closed():
				server_action(self.host,"close",{"result_number":self.result_number})
				self.recv_buffer.close()
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

def backward(local_source,http):
	while True:
		data = local_source.recv(BUFFER_SIZE)
		if data == b'':
			http.send_close()
			local_source.close()
			return
		else:
			http.send(data)


def forward(local_source, http):
	while True:
		data = http.recv()
		if data == b'':
			local_source.close()
			return
		else:
			local_source.sendall(data)

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
		back = threading.Thread(target=backward,args=(self.request,http))
		back.start()
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

