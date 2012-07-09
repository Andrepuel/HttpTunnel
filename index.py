#!/usr/bin/python3

if __name__ == "__main__":
	import cgitb
	cgitb.enable()

	import server
	server.communicate()
