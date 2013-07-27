import socket
import threading
import time
import datetime
from struct import pack, unpack
import traceback

import logging
from logging import error, info, debug
logging.getLogger().setLevel(logging.INFO)

CREATE_CONNECTION=b'\x01'
SYNC_CONNECTION=b'\x02'
OKAY=b'\x03'
ERROR=b'\x04'
DATA=b'\x05'
CONNECTION_CLOSED=b'\x06'

connections_pool = []
connections_pool_nextfree = 0
connections_pool_mutex = threading.Lock()

BUFFER_SIZE=4096

def _recv_exactly(socket,size):
	result = b""
	while len(result) < size:
		data = socket.recv(size-len(result))
		if data == '':
			raise IOError("Connection unexpectedly closed")
		result += data
	return result

def _recv_if_has_data(socket,size=BUFFER_SIZE):
	socket.setblocking(0)
	try:
		data = socket.recv(size)
		socket.setblocking(1)
		return (True,data)
	except BlockingIOError:
		socket.setblocking(1)
		return (False,b"")
	except ConnectionResetError:
		socket.setblocking(1)
		return (True,b"")

def _recv_message(socket):
	msg = b""
	(size,) = unpack(">I",_recv_exactly(socket,4))
	if size > 0:
		msg = _recv_exactly(socket,size)
	return msg

def _recv_error_message(socket):
	error(_recv_message(socket).decode('utf8'))

class Handler(threading.Thread):
	def __init__(self,conn):
		threading.Thread.__init__(self)
		self.conn = conn

	def recv_exactly(self,size):
		#TODO Remove-me
		return _recv_exactly(self.conn,size)

	def close_conn(self,result_number):
		global connections_pool_nextfree
		debug("Acquiring lock for release")
		connections_pool_mutex.acquire()
		try:
			new_conn = connections_pool[result_number]
			new_conn.close()
			connections_pool[result_number] = connections_pool_nextfree
			connections_pool_nextfree = result_number
		finally:
			debug("Lock freed 2")
			connections_pool_mutex.release()
	
	def run(self):
		global connections_pool_nextfree
		try:
			action = self.recv_exactly(1)
			if action == CREATE_CONNECTION:
				dest_address = _recv_message(self.conn)
				(dest_port,) = unpack('>H', self.recv_exactly(2))

				debug("Acquiring lock for creation")
				connections_pool_mutex.acquire()
				try:
					result_number = connections_pool_nextfree
					if result_number == len(connections_pool):
						connections_pool.append(socket.socket(socket.AF_INET))
						connections_pool_nextfree = len(connections_pool)
					else:
						connections_pool_nextfree = connections_pool[result_number]
						connections_pool[result_number] = socket.socket(socket.AF_INET)
					new_conn = connections_pool[result_number]
				finally:
					debug("Lock freed")
					connections_pool_mutex.release()
				address = socket.getaddrinfo(dest_address,dest_port)[-1][4]
				new_conn.connect(address)
				self.conn.sendall(pack('>cI',OKAY,result_number))
				info("Created connection %r to %r"%(result_number,address))
			elif action == SYNC_CONNECTION:
				(result_number,) = unpack('>I',self.recv_exactly(4))
				new_conn = connections_pool[result_number]
				if type(new_conn) == int:
					raise IOError("This connection is closed")
				self.conn.sendall(pack('>c',OKAY))
				while True:
					(has_data,s_action) = _recv_if_has_data(self.conn,1)
					if has_data:
						if s_action == DATA:
							(size,) = unpack('>I',self.recv_exactly(4))
							if size > 0:
								data_received = self.recv_exactly(size)
								new_conn.sendall(data_received)
						elif s_action == CONNECTION_CLOSED:
							info("Connection %r closed by peer" % result_number)
							self.close_conn(result_number)
						elif s_action == b'':
							break
						else:
							raise IndexError("Invalid synchronize action (%r)" % s_action)

					(has_data,back) = _recv_if_has_data(new_conn)
					debug("Real connection has data? %r : %r" % (has_data,back))
					if back == b'' and has_data:
						info("Connection %r closed by real connection" % result_number)
						self.close_conn(result_number)
						self.conn.sendall(pack('>c',CONNECTION_CLOSED))
						self.conn.close()
						return

					if len(back) > 0:
						self.conn.sendall(pack('>cI',DATA,len(back)))
						self.conn.sendall(back)
						
					time.sleep(0)
			else:
				raise IndexError("Invalid action")
		except BaseException as e:
			eStr = str(traceback.format_exc())
			error("Sending error message "+eStr)
			self.conn.sendall(pack('>cI',ERROR,len(eStr)))
			self.conn.sendall(eStr.encode('utf8'))
		self.conn.close()

class Client:
	@staticmethod
	def connect(port_number,dest_address,dest_port):
		address = socket.getaddrinfo("localhost",port_number)[-1][4]
		conn = socket.socket(socket.AF_INET)
		conn.connect(address)
		conn.sendall(pack('>cI', CREATE_CONNECTION, len(dest_address.encode())))
		conn.sendall(dest_address.encode())
		conn.sendall(pack('>H',dest_port))
		is_okay = conn.recv(1)
		if is_okay == OKAY:
			(result_number,) = unpack('>I',_recv_exactly(conn,4))
			conn.close()
			return Client(result_number,port_number)
		elif is_okay == ERROR:
			msg = _recv_message(conn)
			conn.close()
			raise BaseException("Some error on creating connection (%s) " % msg.decode("utf8"))
		else:
			conn.close()
			raise IndexError("Invalid response")

	def __init__(self,result_number,port_number):
		self.address = socket.getaddrinfo("localhost",port_number)[-1][4]
		self.result_number = result_number
		self.conn = None

	def handshake(self):
		if self.conn is None:
			self.conn = self._handshake()
		return self.conn

	def _handshake(self):
		conn = socket.socket(socket.AF_INET)
		conn.connect(self.address)
		conn.sendall(pack('>cI',SYNC_CONNECTION,self.result_number))
		okay = conn.recv(1)
		if okay == ERROR:
			msg = _recv_message(conn)
			conn.close()
			raise BaseException("Some error on creating connection (%s) " % msg.decode("utf8"))
		elif okay != OKAY:
			raise BaseException("Unknown error on creating connection")
		return conn

	def send(self,data):
		conn = self.handshake()
		conn.sendall(pack('>cI',DATA,len(data)))
		if len(data) > 0:
			conn.sendall(data)
	
	def recv(self):
		conn = self.handshake()
		#TODO refactor magic numbers

		MAX_TIME=1
		start = datetime.datetime.now()
		while (datetime.datetime.now()-start).total_seconds() < MAX_TIME:
			has_data,action = _recv_if_has_data(conn,1)
			if has_data:
				break
		if action == DATA:
			(size,) = unpack('>I',_recv_exactly(conn,4))
			data = b""
			if size > 0:
				data = _recv_exactly(conn,size)
			return data
		elif action == ERROR:
			msg = _recv_message(conn)
			raise BaseException("Error on receiving data (%s) " % msg.decode("utf8"))
		elif action == CONNECTION_CLOSED:
			return CONNECTION_CLOSED
		elif action == b'':
			self.conn = None
			return b""
		else:
			raise IndexError("Received invalid response (%r)" % result_action)

	def done(self):
		if self.conn is None:
			return
		self.conn.close()
	
	def close(self):
		conn = self.handshake()
		conn.sendall(pack('>c',CONNECTION_CLOSED))

class SocksDaemon:
	def __init__(self,port_number):
		serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		serversocket.bind(("localhost", port_number))
		serversocket.listen(5)
		while True:
			(conn,address) = serversocket.accept()
			debug("Accepted connection")
			handler = Handler(conn)
			handler.start()
