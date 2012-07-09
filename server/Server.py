import urllib
import os
import sys

sys.stdin = sys.stdin.detach()

URLENCODED_CONTENT = "application/x-www-form-urlencoded"
MULTIPART_CONTENT = "multipart/form-data"

class Server:
	def __init__(self):
		print("Content-Type: text/html")
		print()
		self.post = self._parsePost()
		self.get = self._parseGet()

	def communicate(self):
		print("""<form method="post" action="index.py" enctype="multipart/form-data">
		<input type="text" name="texto" />
		<input type="file" name="file_input" />
		<input type="submit" />
		</form>""")
		for i in os.environ:
			print(i," = ",os.environ[i],"<br />")
		print("Get = <pre>",self.get,"</pre>")
		print("Post = <pre>",self.post,"</pre>")

	def _parsePost(self):
		#TODO Refactor
		if os.environ["REQUEST_METHOD"] != "POST":
			return dict()
		contentType = os.environ["CONTENT_TYPE"]
		data = b"\r\n"+sys.stdin.read()
		if contentType[0:len(URLENCODED_CONTENT)] == URLENCODED_CONTENT:
			return self._parseUrlencoded(str(data))
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

	def _parseUrlencoded(self,urlencoded):
		get = urlencoded.split("&")
		result = dict()
		for each in get:
			nameValue = each.split("=")
			name = nameValue[0]
			value = None
			if len(nameValue) > 1:
				value = nameValue[1]
			result[name] = value
		return result

