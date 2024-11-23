#!/bin/python3

from socket import socket as os_socket
import sys
import json
from threading import Thread

APPLICATION_PORT = 65412

def ui(peer_host, peer_port, input=input, socket=os_socket):
    while True:
        message = input("viestisi: ")
        with socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((peer_host, peer_port))
            s.sendall(json.dumps({"message": message}).encode())
            data = s.recv(1024)

            print(f"Received {data!r}")

def start_server(socket=os_socket):
    with socket(socket.AF_INET, socket.SOCK_STREAM) as s:
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

    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} PEER_HOSTNAME")
        exit(-1)

    peer_host = sys.argv[1] # svm-11-3.cs.helsinki.fi

    # We are creating separate threads for server and client so that they can run at same time. The sockets api is blocking.
    t = Thread(target=ui, args=[peer_host, APPLICATION_PORT])
    t.start()

    t = Thread(target=start_server, args=[])
    t.start()
