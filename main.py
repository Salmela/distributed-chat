#!/bin/python3

from socket import AF_INET, SOCK_STREAM, SOL_SOCKET, SO_REUSEADDR, socket as os_socket
import tty
import termios
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

def send_packet(socket, data):
    socket.sendall(json.dumps(data).encode())

class UserInterface:
    def __init__(self, event_queue, send_message, nickname):
        self.buffer = ""
        self.cursor = 0
        self.scroll = 0
        self.content = []
        self.event_queue = event_queue
        self.send_message = send_message
        self.exited = False
        self.nickname = nickname

    def print_footer(self):
        size = os.get_terminal_size()
        sys.stdout.write(f"\033[{size.lines};1H")
        prefix = f"{self.nickname}: "
        sys.stdout.write(prefix + self.buffer)
        sys.stdout.write(f"\033[{size.lines};{self.cursor + len(prefix) + 1}H")
        sys.stdout.flush()

    def print_messages(self):
        size = os.get_terminal_size()
        sys.stdout.write(f"\033[1;1H")
        logger.info("content: %d - %d - %d" % (len(self.content), self.scroll, (size.lines - 2)))
        logger.info("scroll: %d" % (len(self.content) - self.scroll - (size.lines - 2)))
        logger.info("lines; %d" % size.lines)
        start = len(self.content) - self.scroll - (size.lines - 2)
        offset = -start if start < 0 else 0
        for index, line in enumerate(self.content[max(0, start):][:size.lines - 2]):
            sys.stdout.write(f"\033[{index + offset + 1};1H")
            sys.stdout.write(line)
        sys.stdout.flush()

    def run(self):
        if os.name == 'nt':
            self.run_plain()
        else:
            self.run_fancy()

    def run_input_listener(self):
        try:
            while not self.exited:
                new_char = sys.stdin.read(1)
                logger.info(f"handle read: {ord(new_char)}")
                self.event_queue.put({"type": 'input', "char": new_char})
        finally:
            self.exited = True

    def run_fancy(self):
        try:
            print("\033[?1049h")
            tty_attrs = termios.tcgetattr(sys.stdin)
            tty.setraw(sys.stdin)
            self.print_messages()
            self.print_footer()

            thread = Thread(target=self.run_input_listener, name="input")
            thread.start()

            while not self.exited:
                logger.info(f"wait")
                event = self.event_queue.get()
                logger.info(f"handle event: {event}")

                if event["type"] == "input":
                    new_char = event["char"]
                    if ord(new_char) == 3:
                        raise KeyboardInterrupt()
                    elif ord(new_char) == 4:
                        break
                    elif ord(new_char) == 27:
                        code = sys.stdin.read(2)
                        if code == "[D":
                            self.cursor = max(0, self.cursor - 1)
                        elif code == "[C":
                            self.cursor = max(len(self.buffer), self.cursor + 1)
                    elif ord(new_char) == 13:
                        self.send_message(self.buffer)
                        self.buffer = ""
                        self.cursor = 0
                    elif ord(new_char) == 127:
                        self.buffer = self.buffer[0:self.cursor - 1] + self.buffer[self.cursor:]
                        self.cursor = max(0, self.cursor - 1)
                    else:
                        self.buffer += new_char
                        self.cursor += 1
                        # self.buffer += str(ord(new_char[0]))
                        # self.cursor += len(str(ord(new_char[0])))
                elif event["type"] == "error":
                    self.content.append("\033[1m\033[31m" + event["content"] + "\033[0m")
                elif event["type"] == "info":
                    self.content.append(event["content"])
                elif event["type"] == "own_message":
                    color = hash(self.nickname) % 7
                    self.content.append(f"\033[9{color}m{self.nickname}\033[0m: {event['content']}")
                elif event["type"] == "others_message":
                    color = hash(event['sender']) % 7
                    self.content.append(f"\033[9{color}m{event['sender']}\033[0m: {event['content']}")

                # refresh screen content after every event
                sys.stdout.write("\033[1;1H\033[0J")
                self.print_messages()
                self.print_footer()

        except Exception as exc:
            logger.exception(exc)
            raise exc
        finally:
            self.exited = True
            sys.stdout.write("\033[0m\033[?1049l")
            sys.stdout.flush()
            termios.tcsetattr(sys.stdin, termios.TCSAFLUSH, tty_attrs)

    def run_plain(self, input=input):
        """
        The fallback ui for windows
        """
        try:
            while True:
                message = input()
                self.send_message(message)
        except Exception as exc:
            logger.exception(exc)
            raise exc
        finally:
            sys.stdout.write("\033[0m\033[?1049l")
            sys.stdout.flush()
            termios.tcsetattr(sys.stdin, termios.TCSAFLUSH, tty_attrs)


def send_message(socket, data):
    socket.sendall(json.dumps(data).encode())


class Node:
    """
        docstring
    """
    def __init__(self, hosts, nickname):
        # Too many instance attributes T: pylint :D
        self.event_queue = queue.Queue()
        self.incoming_queue = queue.Queue()
        self.outbound_queue = queue.Queue() # for outbound pending messages
        self.peer_hosts = set(hosts)
        self.inactive_hosts = set()
        self.nickname = nickname
        self.acks = 0 # can this be function spesific
        self.rejects = 0 # can this be function spesific
        self.index = 0 # indicates the next message index for every node
        self.pending_own = None
        self.pending_other = None
        self.ui = UserInterface(self.event_queue, self.send_ui_message, nickname)

    def send_ui_message(self, message):
        self.outbound_queue.put(message)
        if not self.pending_own:
            self.pending_own = self.outbound_queue.get(message)
            self.send_message(APPLICATION_PORT, "PROPOSE")

    def start_server(self, socket=os_socket):
        """
        docstring
        """
        try:
            with socket(AF_INET, SOCK_STREAM) as s:
                s.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
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

                            # Check that this queue works
                            self.incoming_queue.put(data)
                            message = self.incoming_queue.get()

                            if message.get("type") == "GET_NODES":
                                send_packet(conn, {"nodes": list(self.peer_hosts)})
                                self.peer_hosts.add(addr[0])
                                self.event_queue.put({"type": "info", "content": f"Server connected to {self.peer_hosts}"})
                            elif message.get("type") == "NEW_NODE":
                                self.peer_hosts.add(addr[0])
                                self.event_queue.put({"type": "info", "content": f"{addr[0]} joined."})
                                send_packet(conn, {"type": "SYSTEM_INDEX", "index": self.index})
                            elif message.get("type") == "PROPOSE":
                                # Pending has to be time limited in case committing node chrashes
                                # otherwise the pending will just get stuck
                                value = ""
                                if not self.pending_other and self.index == message.get("index"):
                                    self.pending_other = message.get("message")
                                    value = "ack"
                                else:
                                    value = "reject"
                                send_packet(conn, {
                                    "type": "RESPONSE",
                                    "value": value,
                                    "index": message.get("index"),
                                    "sender": self.nickname
                                })
                            elif message.get("type") == "DROP":
                                self.pending_other = None
                            elif message.get("type") == "COMMIT":
                                # If a node misses commits, it will have the wrong index when
                                # the next commit arrives. Node requests the missing
                                # indexes from other nodes?
                                # HISTORY needed for this
                                if self.nickname != message.get('sender'):
                                    self.event_queue.put({"type": "others_message", "sender": message.get('sender'), "content": message.get('message')})
                                logger.debug("Received by %s: %s", message.get('sender'), str(message))
                                formatted_message = (
                                    f"Received {message['message']} "
                                    f"from {message['sender']}"
                                )
                                ack_commit = {"type": "ACK_COMMIT",
                                              "message": formatted_message,
                                              "sender": self.nickname}
                                send_packet(conn, ack_commit)
                                self.pending_other = None
                                self.index = message.get('index') + 1
                                logger.debug("%s sent ack %s", self.nickname, ack_commit)
        except Exception:
            logger.exception("Server thread")
            self.event_queue.put({"type": "error", "content": "Server thread error"})

    def request_peers(self, peer_port, socket=os_socket):
        """
        docstring
        """
        try:
            with socket(AF_INET, SOCK_STREAM) as s:
                s.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
                s.connect((list(self.peer_hosts)[0], peer_port))
                send_packet(s, {"type": "GET_NODES"})
                data = s.recv(1024)

            response = json.loads(data)
            self.peer_hosts.clear()
            self.peer_hosts.update(response.get("nodes", []))
            print(f"Connected to {self.peer_hosts}")

        except Exception:
            logger.exception("Failed to request peers")
            self.event_queue.put({"type": "error", "content": "Failure on peer request"})

    def send_address(self, peer_port, socket=os_socket):
        """
        docstring
        """
        index = []
        try:
            for peer_host in self.peer_hosts:
                try:
                    with socket(AF_INET, SOCK_STREAM) as s:
                        s.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
                        s.connect((peer_host, peer_port))
                        send_message(s, {"type": "NEW_NODE"})
                        data = s.recv(1024)
                        try:
                            response = json.loads(data)
                        except JSONDecodeError:
                            logger.error("Invalid response data: " + data)
                            raise

                        index.append(response.get("index"))
                except Exception as exc:
                    self.handle_exception(peer_host, exc)

            self.index = max(index) if index else 0 # Max index is the most up to date
            self.update_peer_hosts()

        except Exception:
            logger.exception("Failed to send address to peers")
            self.event_queue.put({"type": "error", "content": "Failure to send address to other participants"})

    def send_message(self, peer_port, type, socket=os_socket):
        """
        docstring
        """
        try:
            for peer_host in self.peer_hosts:
                try:
                    with socket(AF_INET, SOCK_STREAM) as s:
                        s.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
                        s.connect((peer_host, peer_port))
                        send_packet(s, {
                            "type": type,
                            "index": self.index,
                            "message": self.pending_own,
                            "sender": self.nickname
                        })
                        data = s.recv(1024)
                        response = json.loads(data)

                        if response.get("type") == "RESPONSE":
                            if response.get("value") == "ack":
                                self.acks += 1
                            elif response.get("value") == "reject":
                                self.rejects += 1

                        if response.get("type") == "ACK_COMMIT":
                            self.event_queue.put({"type": "ack", "message": response.get('message'), "sender": response.get('sender')})

                        logger.debug("Sent by %s: %s", self.nickname, str(response))
                except Exception as exc:
                    self.handle_exception(peer_host, exc)
                    self.event_queue.put({"type": "error", "content": "Failed to propose message to peers"})

            self.update_peer_hosts()

            if type == "PROPOSE":
                self.handle_responses(peer_port)
                self.acks = 0
                self.rejects = 0

        except Exception:
            logger.exception("Failed to propose message to peers")
            self.event_queue.put({"type": "error", "content": "Failed to propose message to peers"})

    def handle_responses(self, peer_port):
        """
        docstring
        """
        if self.acks + self.rejects == len(self.peer_hosts):
            if self.acks > self.rejects:
                self.send_message(peer_port, "COMMIT")
                self.event_queue.put({"type": "own_message", "content": self.pending_own})
                self.index += 1
                self.pending_own = None
                return

        delay = random.uniform(0.1, 0.3) #change this to async?
        time.sleep(delay)
        self.send_message(peer_port, "PROPOSE")
    
    def handle_exception(self, peer_host, exc):
        """
        Currently only handles connection refused errors. Assumed to be called during an exception 
        in a loop where each peer host is iterated through.

        :param peer_host: The peer host which an exception has occurred with.
        :param exc: The exception raised.
        """
        if "Connection refused" in str(exc):
            print(f"{peer_host} has disconnected.")
            logger.debug(f"Removing {peer_host} from set of peer hosts due to connection error.")
            self.inactive_hosts.add(peer_host)


    def update_peer_hosts(self):
        """
        Helper method for updating the set of peer hosts, if inactive hosts are found.
        """
        if len(self.inactive_hosts)>0:
            logger.debug(f'Updating peer hosts. Inactive hosts :{self.inactive_hosts}; Active hosts: {self.peer_hosts}')
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
        logger.info('Starting startup server')
        peer_hosts =  []
        node = Node(peer_hosts, "startup_server")
    else:
        logger.info('Starting peer node')
        peer_hosts = sys.argv[1:] if len(sys.argv) > 1 else ["startup_server"]
        nickname = input("Set nickname: ")
        node = Node(peer_hosts, nickname)

        node.request_peers(APPLICATION_PORT)
        node.send_address(APPLICATION_PORT)

        # We are creating separate threads for server and client
        # so that they can run at same time. The sockets api is blocking.
        thread = Thread(target=node.ui.run, args=[], name="ui")
        thread.start()

    thread = Thread(target=node.start_server, args=[], name="server")
    thread.start()
