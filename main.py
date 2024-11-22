#!/bin/python3

import socket
import sys
import json
from threading import Thread

if len(sys.argv) < 2:
    print(f"Usage: {sys.argv[0]} PEER_HOSTNAME")
    exit(-1)

APPLICATION_PORT = 65412
PEER_HOST = sys.argv[1] # svm-11-3.cs.helsinki.fi

def ui(peer_host, peer_port):
    while True:
        message = input("viestisi: ")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((peer_host, peer_port))
            s.sendall(json.dumps({"message": message}).encode())
            data = s.recv(1024)

            print(f"Received {data!r}")

def start_server(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", APPLICATION_PORT))
        s.listen()
        while True:
            conn, addr = s.accept()
            with conn:
                while True:
                    data = conn.recv(1024)
                    if not data:
                        break
                    print(f"Received by {data}")
                    conn.sendall(data)

# Only run this code if the file was executed from command line
if __name__ == '__main__':
    # We are creating separate threads for server and client so that they can run at same time. The sockets api is blocking.
    t = Thread(target=ui, args=[PEER_HOST, APPLICATION_PORT])
    t.start()

    t = Thread(target=start_server, args=[APPLICATION_PORT])
    t.start()
