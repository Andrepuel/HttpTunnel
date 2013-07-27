HTTP Tunnel
===========
Proxy server that uses only HTTP request for the data transferring.

On applications perspective, HTTP Tunnel tries to provide a general purpose communication layer using only HTTP request. On developers perspective, it is a research on how HTTP may be used for streaming general purpose data (both upload and download).

Right now it is fully functional but a bit slow for highly interactive applications (see "Known bugs and Limitations"). For web browsing, it practically does not affect the user experience.

Installing
----------
Three tiers are involved in the HTTP Tunnel:
1. SOCKS5 server. Will be run locally on your machine. It adapts the communication to the HTTP protocol.
2. CGI capable HTTP web server. Will forward the data to the connection pool.
3. Connection pool daemon. Will establish the actual connection with destination.

All coding was done using Python 3.3, so both your machine and web server must have it installed.

The SOCKS5 server will run locally on your machine. While the CGI script and connection pool must be installed on a server.

### Remote machine (the web server)
1. Run `run_daemon.py`, it will open the connection pool daemon on the default port.
2. Put the source code in your web server's appropriate folder. You will need the URL for the `index.py`, which will receive the HTTP requests and forward it to the connection pool.

### Local machine
1. Just run `run_client.py url port`. Where `url` is the URL to the index.py in your web server, and `port` is which port the SOCKS will listen to.

How it works
------------
HTTP Tunnel creates a SOCKS5 server on the local machine. When a new connection is issued to the SOCKS5 server it will redirect the data to an external server through HTTP requests. The CGI script that receives HTTP requests will just redirect data to a connection pool daemon that keeps the real connection (the connection with the actual destination) alive between requests. This daemon is necessary because the end-to-end communication comprises lot of small HTTP Requests.

The communication goes through the following path:

 * `Alice` 
  * _Application protocol over SOCKS5 Protocol_
 * `SOCKS5 server` 
  * _Internal protocol over pure HTTP_
 * `HTTP Server`
  * _Internal low level protocol_ 
 * `Connections pool` 
  * _Application protocol_
 * `Bob`

Note that the interface of the local machine with the external world is at "_Internal protocol over pure HTTP_", this means that for external observers you are just doing HTTP requests.

Features
--------
HTTP Tunnel works with HTTP and HTTPS (secure HTTP), any application that works with SOCKS5 shall work fine with HTTP Tunnel.


Known bugs and Limitations
--------------------------
Right now, HTTP Tunnel is to slow for interactive applications. Tests with SSH showed that the a few seconds are needed to feedback key presses. 

This happens because data uploading through HTTP Tunnel is unoptimized. While it is easy to stream data **from** HTTP ([see Chunked transfer encoding](http://en.wikipedia.org/wiki/Chunked_transfer_encoding)), it is hard to stream data **to** HTTP, because the client must send the length of uploaded content in the request headers.

Also with SSH, if the remote burst information (tested with `strings /dev/urandom`), the connection will be lost within a few minutes. The cause of this behavior is still unknown.

And finally, the thread handling on the SOCKS server is a bit poor and apparently some threads are alive even after their respective connections were closed.


Future Work
-----------
 * Speed and latency optimization (which is the major issue right now)
 * Figure out an way to stream data through HTTP
 * Code refactor
 * Implement reverse proxy (opening a port on the remote server that will redirect to a local server)
 * Fully implement SOCKS5 server and improve its error reporting.
 * Modularization on the protocols. SOCKS5 should become just a wrapper for the actual HTTP protocol, and the HTTP protocol may be used directly. I.e. create something like a socket but using HTTP as communication layer
