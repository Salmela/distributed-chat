#!/bin/python3

from socket import AF_INET, SOCK_STREAM, socket as os_socket
import os
import sys
import json
import queue
import logging
from threading import Thread

APPLICATION_PORT = 65412
logger = logging.getLogger(__name__)
logging.basicConfig(filename=os.environ.get('LOG_FILE', "chat.log"), level=logging.DEBUG, format="%(asctime)s - %(message)s")

class Node:
    def __init__(self, hosts, nickname):
        self.message_queue = queue.Queue()
        self.peer_hosts = set(hosts)
        self.inactive_hosts = set()
        self.nickname = nickname

    def ui(self, peer_port, input=input, socket=os_socket):
        try:

            self.request_peers(peer_port, socket)
            self.send_address(peer_port, socket)

            while True:
                message = input()
                print(f"{self.nickname}: {message}")
                try:
                    for peer_host in self.peer_hosts:
                        with socket(AF_INET, SOCK_STREAM) as s:
                            s.connect((peer_host, peer_port))
                            s.sendall(json.dumps({"type": "msg", "message": message, "sender": self.nickname}).encode())
                            data = s.recv(1024)


                            logger.debug(f"Sent by {self.nickname}: {data}")
                except Exception as exc:
                        logger.exception(exc)
                        #print(str(exc))
                        if "Connection refused" in str(exc):
                            print(f"{peer_host} has disconnected.")
                            logger.debug(f"Removing {peer_host} from set of peer hosts due to connection error.")
                            self.inactive_hosts.add(peer_host)
                            #self.peer_hosts.remove(peer_host)
                #TODO: update peers
                self.update_peer_hosts()
        except Exception as exc:
            logger.exception(exc)
            raise exc

    def start_server(self, socket=os_socket):
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

                            if message.get("type") == "GET_NODES":
                                conn.sendall(json.dumps({"nodes": list(self.peer_hosts)}).encode())
                                self.peer_hosts.add(addr[0])
                                print(f"server connected to {self.peer_hosts}")
                            elif message.get("type") == "NEW_NODE":
                                self.peer_hosts.add(addr[0])
                                print(f"Connected to {self.peer_hosts}")
                            else:
                                if message.get("type") == "msg":
                                    print(f"{message.get('sender')}: {message.get('message')}")
                                logger.debug(f"Received by {message.get('sender')}: {message}")
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
        try:
            with socket(AF_INET, SOCK_STREAM) as s:
                s.connect((list(self.peer_hosts)[0], peer_port))
                s.sendall(json.dumps({"type": "GET_NODES"}).encode())
                data = s.recv(1024)

            response = json.loads(data)
            self.peer_hosts.clear() #clears the startup server from the peer hosts of a node so that the server does not get messages
            self.peer_hosts.update(response.get("nodes", []))
            print(f"Connected to {self.peer_hosts}")

        except Exception as exc:
            logger.error(f"Failed to request peers: {exc}")

    def send_address(self, peer_port, socket=os_socket):
        try:
            for peer_host in self.peer_hosts:
                with socket(AF_INET, SOCK_STREAM) as s:
                    s.connect((peer_host, peer_port))
                    s.sendall(json.dumps({"type": "NEW_NODE"}).encode())

        except Exception as exc:
            logger.error(f"Failed to send address to peers: {exc}")
    
    def update_peer_hosts(self):
        """
        Helper method for updating the set of peer hosts.
        """
        logger.debug(f'Updating peer hosts. Inactive hosts :{self.inactive_hosts}\nActive hosts: {self.peer_hosts}')
        self.peer_hosts = self.peer_hosts-self.inactive_hosts
        self.inactive_hosts.clear()
        logger.debug(f'Inactive hosts removed from list of peer hosts. Current peer hosts: {self.peer_hosts}')

# Only run this code if the file was executed from command line
if __name__ == '__main__':

    if '--help' in sys.argv:
        print("Start the startup server:")
        print(f"Usage: {sys.argv[0]} startup")
        print("Start the application:")
        print(f"Usage: {sys.argv[0]} [STARTUP SERVER NAME]")
        exit(-1)

    if len(sys.argv) > 1 and sys.argv[1] == "startup":
        peer_hosts =  []
        node = Node(peer_hosts, "startup_server")
    else:
        peer_hosts = sys.argv[1:] if len(sys.argv) > 1 else ["startup_server"]
        nickname = input("Set nickname: ")
        node = Node(peer_hosts, nickname)

        # We are creating separate threads for server and client so that they can run at same time. The sockets api is blocking.
        t = Thread(target=node.ui, args=[APPLICATION_PORT])
        t.start()

    t = Thread(target=node.start_server, args=[])
    t.start()
