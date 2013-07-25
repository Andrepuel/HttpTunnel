#!/usr/bin/python3

import sys
port = 8080
if len(sys.argv) < 2:
	sys.stderr.write("Usage %s http_address [local_port]\r\n" % sys.argv[0])
	sys.exit(1)
http_address = sys.argv[1]
if len(sys.argv) > 2:
	port = int(sys.argv[2])

import client.Client
server = client.Client.SocksServer(http_address,('localhost', port))
server.serve_forever()
