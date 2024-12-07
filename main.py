"""docstring"""
#!/bin/python3

from socket import AF_INET, SOCK_STREAM, socket as os_socket
import os
import sys
import json
import queue
import logging
import time
import random
from threading import Thread

APPLICATION_PORT = 65412
logger = logging.getLogger(__name__)
logging.basicConfig(filename=os.environ.get('LOG_FILE', "chat.log"),
                    level=logging.DEBUG, format="%(asctime)s - %(message)s")

class Node:
    """
        docstring
    """
    def __init__(self, hosts, nickname):
        #too many instance attributes T: pylint :D
        self.incoming_queue = queue.Queue()
        self.outbound_queue = queue.Queue() #for outbound pending messages
        self.peer_hosts = set(hosts)
        self.nickname = nickname
        self.acks = 0 #can this be function spesific
        self.rejects = 0 # can this be function spesific
        self.index = 0 #indicates the next message index for every node
        self.pending_own = None
        self.pending_other = None

    def ui(self, peer_port, input=input):
        """
        docstring
        """
        try:

            self.request_peers(peer_port)
            self.send_address(peer_port)

            while True:
                message = input()
                #check that this queue works
                self.outbound_queue.put(message)
                if not self.pending_own:
                    self.pending_own = self.outbound_queue.get(message)
                    self.send_message(peer_port, "PROPOSE")
        except Exception as exc:
            logger.exception(exc)
            raise exc

    def start_server(self, socket=os_socket):
        """
        docstring
        """
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
                            data = json.loads(data)

                            #check that this queue works
                            self.incoming_queue.put(data)
                            message = self.incoming_queue.get()

                            if message.get("type") == "GET_NODES":
                                conn.sendall(json.dumps({"nodes": list(self.peer_hosts)}).encode())
                                self.peer_hosts.add(addr[0])
                                print(f"server connected to {self.peer_hosts}")
                            elif message.get("type") == "NEW_NODE":
                                self.peer_hosts.add(addr[0])
                                print(f"{addr[0]} joined.")
                                conn.sendall(json.dumps({"type": "SYSTEM_INDEX",
                                                         "index": self.index}).encode())
                            elif message.get("type") == "PROPOSE":
                                #pending has to be time limited in case committing node chrashes
                                #otherwise the pending will just get stuck
                                value = ""
                                if not self.pending_other and self.index == message.get("index"):
                                    self.pending_other = message.get("message")
                                    value = "ack"
                                else:
                                    value = "reject"
                                conn.sendall(json.dumps({"type": "RESPONSE", "value": value,
                                                         "index": message.get("index"),
                                                         "sender": self.nickname}).encode())
                            elif message.get("type") == "COMMIT":
                                #if a node misses commits, it will have the wrong index when
                                #the next commit arrives. Node requests the missing
                                #indexes from other nodes?
                                # HISTORY needed for this
                                print(f"{message.get('sender')}: {message.get('message')}")
                                logger.debug("Received by %s: %s", message.get('sender'), str(message))
                                formatted_message = (
                                                f"Received {message['message']} "
                                                f"from {message['sender']}"
                                )
                                ack_commit = json.dumps({"type": "ACK_COMMIT",
                                                         "message": formatted_message,
                                                         "sender": self.nickname}).encode()
                                conn.sendall(ack_commit)
                                self.pending_other = None
                                self.index = message.get('index')+1
                                logger.debug("%s sent ack %s", self.nickname, str(ack_commit.decode('utf-8')))
        except Exception as exc:
            logger.exception(exc)
            raise exc

    def request_peers(self, peer_port, socket=os_socket):
        """
        docstring
        """
        try:
            with socket(AF_INET, SOCK_STREAM) as s:
                s.connect((list(self.peer_hosts)[0], peer_port))
                s.sendall(json.dumps({"type": "GET_NODES"}).encode())
                data = s.recv(1024)

            response = json.loads(data)
            self.peer_hosts.clear()
            self.peer_hosts.update(response.get("nodes", []))
            print(f"Connected to {self.peer_hosts}")

        except Exception as exc:
            logger.error("Failed to request peers: %s", exc)

    def send_address(self, peer_port, socket=os_socket):
        """
        docstring
        """
        index = []
        try:
            for peer_host in self.peer_hosts:
                with socket(AF_INET, SOCK_STREAM) as s:
                    s.connect((peer_host, peer_port))
                    s.sendall(json.dumps({"type": "NEW_NODE"}).encode())
                    data = s.recv(1024)
                    response = json.loads(data)

                    index.append(response.get('index'))

            self.index = max(index) #max index is the most up to date

        except Exception as exc:
            logger.error("Failed to send address to peers: %s", exc)

    def send_message(self, peer_port, type, socket=os_socket):
        """
        docstring
        """
        try:
            for peer_host in self.peer_hosts:
                with socket(AF_INET, SOCK_STREAM) as s:
                    s.connect((peer_host, peer_port))
                    s.sendall(json.dumps({"type": type,
                                          "index": self.index,
                                          "message": self.pending_own,
                                          "sender": self.nickname}).encode())
                    data = s.recv(1024)
                    response = json.loads(data)

                    if response.get("type") == "RESPONSE":
                        if response.get("value") == "ack":
                            self.acks+=1
                        elif response.get("value") == "reject":
                            self.rejects+=1

                    if response.get("type") == "ACK_COMMIT":
                        print(f"{response.get('message')}, sender: {response.get('sender')}")

                    logger.debug("Sent by %s: %s", self.nickname, str(response))

            if type == "PROPOSE":
                self.handle_responses(peer_port)
                self.acks = 0
                self.rejects = 0

        except Exception as exc:
            logger.error("Failed to propose message to peers: %s", exc)

    def handle_responses(self, peer_port):
        """
        docstring
        """
        if self.acks + self.rejects == len(self.peer_hosts):
            if self.acks > self.rejects:
                self.send_message(peer_port, "COMMIT")
                print(f"{self.nickname}: {self.pending_own}")
                self.index+=1
                self.pending_own = None
                return

        delay = random.uniform(0.1, 0.3) #change this to async?
        time.sleep(delay)
        self.send_message(peer_port, "PROPOSE")

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

        # We are creating separate threads for server and client
        # so that they can run at same time. The sockets api is blocking.
        t = Thread(target=node.ui, args=[APPLICATION_PORT])
        t.start()

    t = Thread(target=node.start_server, args=[])
    t.start()
