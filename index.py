#!/usr/bin/python3

#import cgitb
#cgitb.enable()
import server
import daemon
import sys
import os
from struct import pack,unpack
import traceback

DAEMON_PORT=7008

def send_error(traceback_str):
	eStr = str(traceback_str).encode('utf8')
	sys.stdout.write(daemon.ERROR)
	sys.stdout.write(pack(">I",len(eStr)))
	sys.stdout.write(eStr)

class Tunnel(server.ServerAction):
	def action_create(self,post):
		try:
			dest_address = post["dest_address"].decode()
			dest_port = post["dest_port"].decode()
			client = daemon.Client.connect(DAEMON_PORT,dest_address,int(dest_port))
			sys.stdout.write(daemon.OKAY)
			sys.stdout.write(pack(">I",client.result_number))
		except BaseException as e:
			send_error(traceback.format_exc())
	
	def action_sync(self,post):
		try:
			result_number = int(post["result_number"])
			client = daemon.Client(result_number,DAEMON_PORT)
			result = client.send_recv(post["data"])
			if result is daemon.CONNECTION_CLOSED:
				sys.stdout.write(daemon.CONNECTION_CLOSED)
				return
			sys.stdout.write(daemon.DATA)
			sys.stdout.write(pack(">I",len(result)))
			sys.stdout.write(result)
		except BaseException as e:
			send_error(traceback.format_exc())

	def action_close(self,post):
		try:
			result_number = int(post["result_number"])
			client = daemon.Client(result_number,DAEMON_PORT)
			result = client.send_recv(b"")
			client.close()
			if result is daemon.CONNECTION_CLOSED:
				sys.stdout.write(daemon.CONNECTION_CLOSED)
				return
			sys.stdout.write(daemon.DATA)
			sys.stdout.write(pack(">I",len(result)))
			sys.stdout.write(result)
		except BaseException as e:
			send_error(traceback.format_exc())

coisa = Tunnel()
try:
	coisa.communicate()
except BaseException as e:
	send_error(traceback.format_exc())
