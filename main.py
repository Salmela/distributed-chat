#!/bin/python3

import socket
import sys
from threading import Thread

HOST = "0.0.0.0"
HOST_PORT = int(sys.argv[1])

PEER_HOST = sys.argv[2] # svm-11-3.cs.helsinki.fi
PEER_PORT = int(sys.argv[3]) # 65412

def ui(peer_host, peer_port):
    while True:
        message = input("viestisi: ")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((peer_host, peer_port))
            s.sendall(message.encode())
            data = s.recv(1024)

            print(f"Received {data!r}")

def start_server(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, HOST_PORT))
        s.listen()
        while True:
            conn, addr = s.accept()
            with conn:
                while True:
                    data = conn.recv(1024)
                    if not data:
                        break
                    print(f"Received by {data}")
                    conn.sendall(b"peer: " + data)

# We are creating separate threads for server and client so that they can run at same time. The sockets api is blocking.
t = Thread(target=ui, args=[PEER_HOST, PEER_PORT])
t.start()

t = Thread(target=start_server, args=[HOST, HOST_PORT])
t.start()
