#!/bin/python3

from socket import AF_INET, SOCK_STREAM, gethostname, gethostbyname, socket as os_socket
import sys
import json
import queue
import logging
from threading import Thread

APPLICATION_PORT = 65412
startup = None
logger = logging.getLogger(__name__)
logging.basicConfig(filename=f"chat.log", level=logging.DEBUG, format="%(asctime)s - %(message)s")

class Node:
    def __init__(self, hosts, nickname):
        self.message_queue = queue.Queue()
        self.peer_hosts = hosts if hosts is not None else []
        self.ip = gethostbyname(gethostname())
        self.nickname = nickname

    def ui(self, peer_port, startup, input=input, socket=os_socket):
        try:

            if not startup:
                self.request_peers(peer_port, socket)

            while True:
                message = input("viestisi: ")
                for peer_host in self.peer_hosts:
                    with socket(AF_INET, SOCK_STREAM) as s:
                        s.connect((peer_host, peer_port))
                        s.sendall(json.dumps({"type": "msg", "message": message, "sender": self.nickname}).encode())
                        data = s.recv(1024)

                        print()
                        logger.debug(f"Sent by {self.nickname}: {data}")
        except Exception as exc:
            logger.exception(exc)
            raise exc

    def start_server(self, peer_port, socket=os_socket):
        try:
            with socket(AF_INET, SOCK_STREAM) as s:
                s.bind(("0.0.0.0", APPLICATION_PORT))
                s.listen()
                while True:
                    conn, addr = s.accept()
                    with conn:
                        while True:
                            data = conn.recv(1024)
                            if not data:
                                break
                            message = json.loads(data)
                            print()

                            if message.get("type") == "GET_NODES":
                                conn.sendall(json.dumps({"nodes": self.peer_hosts}).encode())
                                new_peer = message.get("node_ip")
                                self.peer_hosts.append(new_peer)
                                print(f"server connected to {self.peer_hosts}")
                                self.send_peers(peer_port)
                            elif message.get("type") == "NEW_NODES":
                                all_peers = set(self.peer_hosts)
                                new_peers = message.get("nodes", [])
                                all_peers.update(new_peers)
                                all_peers.remove(self.ip)
                                self.peer_hosts = list(all_peers)
                            else:
                                print(f"Received by {data}")
                                logger.debug(f"Received by {message['sender']}: {message}")
                                self.message_queue.put(data)

                                if not self.message_queue.empty():
                                    msg = self.message_queue.get()

                                    ack = json.dumps({"type": "ack", "message": f"Received {message['message']} from {message['sender']}", "sender": self.nickname}).encode()
                                    conn.sendall(ack)
                                    logger.debug(f"{self.nickname} sent ack {ack}")
        except Exception as exc:
            logger.exception(exc)
            raise exc

    def request_peers(self, peer_port, socket=os_socket):

        all_peers = set(self.peer_hosts)
        try:
            with socket(AF_INET, SOCK_STREAM) as s:
                s.connect(("startup_server", peer_port))
                s.sendall(json.dumps({"type": "GET_NODES", "node_ip": self.ip}).encode())
                data = s.recv(1024)

                response = json.loads(data)
                peers = response.get("nodes", [])

                all_peers.update(peers)

        except Exception as exc:
            logger.error(f"Failed to connect to startup server: {exc}")

        self.peer_hosts = list(all_peers)
        print(f"Connected to {self.peer_hosts}")

    def send_peers(self, peer_port, socket=os_socket):
        try:
            for peer_host in self.peer_hosts:
                with socket(AF_INET, SOCK_STREAM) as s:
                    s.connect((peer_host, peer_port))
                    s.sendall(json.dumps({"type": "NEW_NODES", "nodes": self.peer_hosts}).encode())

        except Exception as exc:
            logger.error(f"Failed to send new peers: {exc}")


# Only run this code if the file was executed from command line
if __name__ == '__main__':

    if '--help' in sys.argv:
        print("Start the startup server:")
        print(f"Usage: {sys.argv[0]} startup")
        exit(-1)

    if len(sys.argv) > 1 and sys.argv[1] == "startup":
        startup = 1
        peer_hosts = None
        nickname = "startup_server"
    else:
        peer_hosts = sys.argv[1:] # svm-11-3.cs.helsinki.fi
        nickname = input("Set nickname: ")

    node = Node(peer_hosts, nickname)

    # We are creating separate threads for server and client so that they can run at same time. The sockets api is blocking.
    t = Thread(target=node.ui, args=[APPLICATION_PORT, startup])
    t.start()

    t = Thread(target=node.start_server, args=[APPLICATION_PORT])
    t.start()
