import urllib.parse
import daemon
import socket

def _get_line(conn):
	line = b""
	while True:
		one = conn.recv(1)
		if one == b'':
			return line
		line += one
		if line[-2:] == b'\r\n':
			return line[:-2]

class LengthRecvMode:
	def __init__(self,response,headers,conn):
		self.conn = conn
		self.size = int(headers[b"Content-Length"])
	
	def recv(self,bufsize):
		if self.size == 0:
			return b""
		received = self.conn.recv(min(bufsize,self.size))
		self.size -= len(received)
		return received

class ChunkedRecvMode:
	def __init__(self,response,headers,conn):
		self.conn = conn
		self.actual_chunk_size = 0
	
	def recv(self,bufsize):
		if self.actual_chunk_size == 0:
			line = _get_line(self.conn)
			if line == b'':
				self.actual_chunk_size = -1
				return b""
			self.actual_chunk_size = int(line,16)
			if self.actual_chunk_size == -1:
				self.actual_chunk_size = -1
				return b""
			return self.recv(bufsize)
		elif self.actual_chunk_size == -1:
			return b""
		else:
			received = self.conn.recv(min(bufsize,self.actual_chunk_size))
			self.actual_chunk_size -= len(received)
			return received

class HTTPRequest:
	def __init__(self,url,get=None,post=None):
		if post is None:
			method = "GET"
			if_post = False
		else:
			method = "POST"
			if_post = True
		agent = 'Python/3.3'

		(protocol,address) = url.split("//")
		assert protocol == "http:" or protocol == "https:"
		(full_host,*path) = address.split("/")
		(host,port,*unused) = (full_host.split(":") + ["80" if protocol == 'http:' else "443"])
		port = int(port)
		if not get is None:
			get_coded = "?" + urllib.parse.urlencode(get)
		else:
			get_coded = ""
		if not post is None:
			post_coded = urllib.parse.urlencode(post)
		path = "/".join(path)

		headers = "%s /%s%s HTTP/1.1\r\n" % (method,path,get_coded)
		headers += "Accept-Encoding: identity\r\n"
		headers += "Content-type: application/x-www-form-urlencoded\r\n" if if_post else ""
		headers += "User-Agent: %s\r\n" % agent
		headers += "Content-Length: %s\r\n" % len(post_coded) if if_post else ""
		headers += "Host: %s\r\n" % full_host
		headers += "Connection: close\r\n\r\n"

		self.conn = socket.socket(socket.AF_INET)
		self.conn.connect((host,port))
		if protocol == 'https:':
			import ssl
			self.conn = ssl.wrap_socket(self.conn)

		self.conn.sendall(headers.encode('ascii'))
		if if_post:
			self.conn.sendall(post_coded.encode('ascii'))

		self.response = _get_line(self.conn)
		self.got_headers = dict()
		while True:
			line = _get_line(self.conn)
			if line == b'':
				break
			line = line.split(b":")
			self.got_headers[ line[0].strip() ] = line[1].strip()

		if b"Transfer-Encoding" in self.got_headers and self.got_headers[b"Transfer-Encoding"] == b"chunked":
			self.transfer = ChunkedRecvMode(self.response,self.got_headers,self.conn)
		elif b"Content-Length" in self.got_headers:
			self.transfer = LengthRecvMode(self.response,self.got_headers,self.conn) 
		else:
			raise BaseException("Unimplemented")
	
	def recv(self,bufsize):
		return self.transfer.recv(bufsize)
