#!/usr/bin/python3

port=7008
import sys
if len(sys.argv) > 1:
	port = int(sys.argv[1])

import daemon
daemon.SocksDaemon(port)
