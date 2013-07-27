#!/usr/bin/python3

#import cgitb
#cgitb.enable()
import server
import daemon
import sys
import os
from struct import pack,unpack
import traceback
from time import sleep
from datetime import datetime

DAEMON_PORT=7008
MAX_TIME=10

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
			client.done()
		except BaseException as e:
			send_error(traceback.format_exc())
	
	def action_send(self,post):
		try:
			result_number = int(post["result_number"])
			client = daemon.Client(result_number,DAEMON_PORT)
			client.send(post["data"])
			client.done()
		except BaseException as e:
			send_error(traceback.format_exc())

	def action_recv(self,post):
		try:
			result_number = int(post["result_number"])
			client = daemon.Client(result_number,DAEMON_PORT)

			start = datetime.now()
			while (datetime.now()-start).total_seconds() < MAX_TIME:
				result = client.recv()
				if result is daemon.CONNECTION_CLOSED:
					sys.stdout.write(daemon.CONNECTION_CLOSED)
					return
				sys.stdout.write(daemon.DATA)
				sys.stdout.write(pack(">I",len(result)))
				sys.stdout.write(result)
				if( len(result) == 0 ):
					break
				sleep(0)
			client.done()
		except BaseException as e:
			send_error(traceback.format_exc())

	def action_close(self,post):
		try:
			result_number = int(post["result_number"])
			client = daemon.Client(result_number,DAEMON_PORT)
			client.close()
			client.done()
		except BaseException as e:
			send_error(traceback.format_exc())

coisa = Tunnel()
try:
	coisa.communicate()
except BaseException as e:
	send_error(traceback.format_exc())
