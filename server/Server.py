import urllib
import urllib.parse
import os
import sys

sys.stdin = sys.stdin.detach()
sys.stdout = sys.stdout.detach()

URLENCODED_CONTENT = "application/x-www-form-urlencoded"
MULTIPART_CONTENT = "multipart/form-data"

def a_print(*args):
	for i in args:
		sys.stdout.write(str(i).encode('ascii'))
	sys.stdout.write(b"\n")

class Server:
	def __init__(self):
		self.content_type = "text/html"
		self.post = self._parsePost()
		self.get = self._parseGet()

	def print_header(self):
		a_print("Content-Type: %s" % self.content_type)
		a_print("")

	def communicate(self):
		self.print_header()

		a_print("""<form method="post" action="index.py"> <!-- enctype="multipart/form-data"-->
		<input type="text" name="texto" />
		<input type="file" name="file_input" />
		<input type="submit" />
		</form>""")
		for i in os.environ:
			a_print(i," = ",os.environ[i],"<br />")
		a_print("Get = <pre>",self.get,"</pre>")
		a_print("Post = <pre>")
		for i in self.post:
			a_print("%s = %s" % (i,self.post[i]))	
		a_print("</pre>")

	def _parsePost(self):
		#TODO Refactor
		if os.environ["REQUEST_METHOD"] != "POST":
			return dict()
		contentType = os.environ["CONTENT_TYPE"]
		if contentType[0:len(URLENCODED_CONTENT)] == URLENCODED_CONTENT:
			return self._parseUrlencoded(str(sys.stdin.read()))
		data = b"\r\n"+sys.stdin.read()
		assert contentType[0:len(MULTIPART_CONTENT)] == MULTIPART_CONTENT
		boundary = bytes("\r\n--"+contentType.split("; boundary=")[1],encoding='ascii')
		data = data.split(boundary)
		result = dict()
		for each in data:
			if len(each) == 0:
				continue
			if each == b"--\r\n":
				break
			dataName = None
			(eachHeader,eachData) = each.split(b"\r\n\r\n")
			headerComponents = eachHeader.split(b"\r\n")
			for eachComponent in headerComponents:
				try:
					(componentName,componentValue) = eachComponent.split(b": ")
				except:
					continue
				if componentName == b'Content-Disposition':
					dispositions = componentValue.split(b"; ")
					for eachDisposition in dispositions:
						try:
							(dispositionKey,dispositionValue) = eachDisposition.split(b"=")
						except:
							continue
						if dispositionKey == b"name":
							dataName = dispositionValue[1:-1]
				else:
					pass #Content-Type
			result[dataName.decode()] = eachData
		return result

	def _parseGet(self):
		uri = os.environ['REQUEST_URI']
		get = uri.split("?")
		if len(get) < 2:
			return dict()
		return self._parseUrlencoded(get[1])

	#Workaround for weird behavior on urllib TODO Check this issue
	def _parseUrlencoded(self,urlencoded):
		if( urlencoded[0:2] == "b'" and urlencoded[-1] == "'" ):
			urlencoded = urlencoded[2:-1]
		return self._parseUrlencoded_original(urlencoded)

	def _unquote_to_bytes_plus(self,value):
		return urllib.parse.unquote_to_bytes(value.replace("+"," "))

	def _parseUrlencoded_original(self,urlencoded):
		get = urlencoded.split("&")
		result = dict()
		for each in get:
			nameValue = each.split("=")
			name = self._unquote_to_bytes_plus(nameValue[0]).decode('utf8')
			value = None
			if len(nameValue) > 1:
				value = self._unquote_to_bytes_plus(nameValue[1])
			result[name] = value
		return result

class ServerAction(Server):
	def communicate(self):
		if "action" in self.get:
			action = self.get["action"].decode('ascii')
			self.content_type = "application/octect-stream"
			self.print_header()
			if not hasattr(self,"action_"+action):
				a_print("Invalid action")
			else:
				getattr(self,"action_"+action)(self.post)
		else:
			self.print_header()
			a_print("No action issued")
