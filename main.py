#!/bin/python3

from socket import AF_INET, SOCK_STREAM, SOL_SOCKET, SO_REUSEADDR, gethostname, gethostbyname, socket as os_socket
import tty
import termios
import os
import sys
import json
import queue
import logging
import time
import random
from threading import Thread, Timer
from json.decoder import JSONDecodeError

APPLICATION_PORT = 65412
logger = logging.getLogger(__name__)
logging.basicConfig(filename=os.environ.get('LOG_FILE', "chat.log"),
                    level=logging.DEBUG, format="%(asctime)s - %(message)s")

def send_packet(socket, data):
    socket.sendall(json.dumps(data).encode())

class UserInterface:
    def __init__(self, event_queue, send_message, nickname, history):
        self.buffer = ""
        self.cursor = 0
        self.scroll = 0
        self.content = []
        self.event_queue = event_queue
        self.send_message = send_message
        self.exited = False
        self.nickname = nickname
        self.ui_history = history

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

    def print_history(self):
        return

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
#            self.print_history()

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
                        if self.buffer.strip() == "\\exit":
                            break
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
                    size = os.get_terminal_size()
                    color = hash(self.nickname) % 7
                    content = event['content']
                    first = True
                    while content:
                        line = content[:size.columns]
                        content = content[size.columns:]
                        if first:
                            self.content.append(f"\033[9{color}m{self.nickname}\033[0m: {event['content']}")
                        else:
                            self.content.append(f"{' ' * len(self.nickname)}  {event['content']}")
                        first = False
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
            os._exit(0)

    def run_plain(self, input=input):
        """
        The fallback ui for windows
        """
        try:
            thread = Thread(target=self.plain_events, name="events")
            thread.start()
            while True:
                message = input()
                if message.strip() == "\\exit":
                    break
                self.send_message(message)
        except Exception as exc:
            logger.exception(exc)
            self.exited = True
        finally:
            os._exit(0)

    def plain_events(self):
        while not self.exited:
            logger.info(f"wait")
            event = self.event_queue.get()
            logger.info(f"handle event: {event}")

            if event["type"] == "error":
                print("\033[1m\033[31m" + event["content"] + "\033[0m")
            elif event["type"] == "info":
                print(event["content"])
            elif event["type"] == "own_message":
                size = os.get_terminal_size()
                color = hash(self.nickname) % 7
                content = event['content']
                first = True
                while content:
                    line = content[:size.columns]
                    content = content[size.columns:]
                    if first:
                        print(f"\033[9{color}m{self.nickname}\033[0m: {event['content']}")
                    else:
                        print(f"{' ' * len(self.nickname)}  {event['content']}")
                    first = False
            elif event["type"] == "others_message":
                color = hash(event['sender']) % 7
                print(f"\033[9{color}m{event['sender']}\033[0m: {event['content']}")


class Node:
    """
        Class for creating a node in the system.
    """
    def __init__(self, hosts, nickname):
        self.event_queue = queue.Queue()
        self.incoming_queue = queue.Queue()
        self.outbound_queue = queue.Queue()
        self.peer_hosts = set(hosts)
        self.inactive_hosts = set()
        self.nickname = nickname
        self.acks = 0
        self.rejects = 0
        self.index = 0
        self.pending_own = None
        self.pending_other = None
        self.history = []
        self.ui = UserInterface(self.event_queue, self.send_ui_message, nickname, self.history)

    def send_ui_message(self, message):
        """
        Function for printing messages in the user interface.

        Args:
        message (str): Message to send.
        """
        self.outbound_queue.put(message)
        if not self.pending_own:
            self.pending_own = self.outbound_queue.get(message)
            self.send_message(APPLICATION_PORT, "PROPOSE")

    def start_server(self, peer_port, socket=os_socket):
        """
        Starts server. Receives different message types.

        Args:
        socket (type): Socket module.

        Raises:
        Exception: If the connection fails.
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

                            self.incoming_queue.put(data)
                            message = self.incoming_queue.get()

                            if message.get("type") == "GET_NODES":
                                send_packet(conn, {"nodes": list(self.peer_hosts)})
                                self.peer_hosts = {i for i in self.peer_hosts if i[0] != addr[0]}
                                self.peer_hosts.add((addr[0], message.get("nickname")))
                                self.event_queue.put({"type": "info",
                                                      "content": f"Server connected to {self.peer_hosts}"})
                            elif message.get("type") == "NEW_NODE":
                                self.peer_hosts.add((addr[0], message.get("nickname")))
                                self.event_queue.put({"type": "info", "content": f"{message.get('nickname')} joined."})
                                send_packet(conn, {"type": "SYSTEM_INDEX", "index": self.index})
                            elif message.get("type") == "GET_HISTORY":
                                send_packet(conn, {"type": "HISTORY",
                                                    "history": self.history})
                            elif message.get("type") == "PROPOSE":
                                if not self.pending_other and self.index == message.get("index"):
                                    self.pending_other = self.set_pending_message(message.get("message"))
                                    value = "ack"
                                else:
                                    value = "reject"
                                send_packet(conn, {
                                    "type": "RESPONSE",
                                    "value": value,
                                    "index": message.get("index"),
                                    "sender": self.nickname
                                })
                            elif message.get("type") == "COMMIT":
                                if message.get("index") != self.index:
                                    self.get_history(peer_port, addr[0])
                                self.history.append({"index": message.get("index"),
                                                     "sender": message.get("sender"),
                                                     "message": message.get("message")})
                                if self.nickname != message.get('sender'):
                                    self.event_queue.put({"type": "others_message",
                                                          "sender": message.get('sender'),
                                                          "content": message.get('message')})
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
        Requests peers from the startup server. Sets peers.

        Args:
        peer_port (int): Application port number.
        socket (type): Socket module.

        Raises:
        Exception: If the connection fails.
        """
        local_address = gethostbyname(gethostname())
        try:
            with socket(AF_INET, SOCK_STREAM) as s:
                s.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
                s.connect((list(self.peer_hosts)[0], peer_port))
                send_packet(s, {"type": "GET_NODES", "nickname": self.nickname})
                data = s.recv(1024)

            response = json.loads(data)
            self.peer_hosts.clear()
            converted_nodes_list = [tuple(inner_list) for inner_list in response.get("nodes", [])]
            self.peer_hosts.update(converted_nodes_list)
            self.peer_hosts = {i for i in self.peer_hosts if i[0] != local_address}

            connected_to = []
            for i in self.peer_hosts:
                connected_to.append(i[1])
            print(f"Connected to {connected_to}")

        except Exception:
            logger.exception("Failed to request peers")
            self.event_queue.put({"type": "error", "content": "Failure on peer request"})


    def send_address(self, peer_port, socket=os_socket):
        """
        Sends address to all peers and receives indexes. Sets index.

        Args:
        peer_port (int): Application port number.
        socket (type): Socket module.

        Raises:
        JSONDecodeError: If the response data is invalid.
        Exception: If the connection fails.
        """
        index = []
        try:
            for peer_host in self.peer_hosts:
                try:
                    with socket(AF_INET, SOCK_STREAM) as s:
                        s.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
                        s.connect((peer_host[0], peer_port))
                        send_packet(s, {"type": "NEW_NODE", "nickname": self.nickname})
                        data = s.recv(1024)
                        try:
                            response = json.loads(data)
                        except JSONDecodeError:
                            logger.error("Invalid response data: " + data)
                            raise

                        index.append(response.get("index"))
                except Exception as exc:
                    self.handle_exception(peer_host, exc)

            self.index = max(index) if index else 0
            self.update_peer_hosts()

        except Exception:
            logger.exception("Failed to send address to peers")
            self.event_queue.put({"type": "error",
                                  "content": "Failure to send address to other participants"})

    def get_history(self, peer_port, peer_host, socket=os_socket):
        """
        Requests message history from a peer. Sets history.

        Args:
        peer_port (int): Application port number.
        peer_host (str): The request is send to this peer.
        socket (type): Socket module.

        Raises:
        Exception: If the connection fails.
        """
        if not self.peer_hosts:
            return
        else:
            if not peer_host:
                host = list(self.peer_hosts)[0]
            try:
                with socket(AF_INET, SOCK_STREAM) as s:
                    s.connect((host[0], peer_port))
                    send_packet(s, {"type": "GET_HISTORY"})
                    data = s.recv(1024)

                response = json.loads(data)
                self.history = response.get("history")

            except Exception as exc:
                logger.error("Failed to request history: %s", exc)

    def set_pending_message(self, message, timeout=3):
        """
        Sets incoming pending message.

        Args:
        message(str): The message which is set as pending.
        timeout (int): The timeout for the pending message.
        """
        self.pending_other = message
        timer = Timer(timeout, self.clear_pending_message)
        timer.start()

    def clear_pending_message(self):
        """
        Clears incoming pending message.
        """
        self.pending_other = None

    def send_message(self, peer_port, type, socket=os_socket):
        """
        Issues a message. Receives acknowledgements, rejects and ack_commits.

        Args:
        peer_port (int): Application port number.
        type (str): Message type.
        socket (type): Socket module.

        Raises:
        Exception: If the connection fails.
        """
        try:
            for peer_host in self.peer_hosts:
                try:
                    with socket(AF_INET, SOCK_STREAM) as s:
                        s.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
                        s.connect((peer_host[0], peer_port))
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
                            self.event_queue.put({"type": "ack",
                                                  "message": response.get('message'),
                                                  "sender": response.get('sender')})

                        logger.debug("Sent by %s: %s", self.nickname, str(response))
                except Exception as exc:
                    self.handle_exception(peer_host, exc)

            self.update_peer_hosts()

            if type == "PROPOSE":
                self.handle_responses(peer_port)
                self.acks = 0
                self.rejects = 0

        except Exception:
            logger.exception("Failed to propose message to peers")
            self.event_queue.put({"type": "error",
                                  "content": "Failed to propose message to peers"})

    def handle_responses(self, peer_port):
        """
        Handles acknowledges and rejects. Issues a commit message.
        Issues a new propose message.

        Args:
        peer_port (int): Application port number.
        """
        if self.acks + self.rejects == len(self.peer_hosts):
            if self.acks > self.rejects:
                self.send_message(peer_port, "COMMIT")
                self.event_queue.put({"type": "own_message",
                                      "content": self.pending_own})
                self.history.append({"index": self.index,
                                     "sender": self.nickname,
                                     "message": self.pending_own})
                self.index += 1
                self.pending_own = None
                return

        delay = random.uniform(0.1, 0.3)
        time.sleep(delay)
        self.send_message(peer_port, "PROPOSE")

    def handle_exception(self, peer_host, exc):
        """
        Handles connection refused errors.

        Args:
        peer_host: The peer host which an exception has occurred with.
        exc: The exception raised.
        """
        if "Connection refused" in str(exc):
            self.event_queue.put({"type": "info",
                                  "content": f"{peer_host[1]} has disconnected."})
            logger.debug(f"Removing {peer_host} from set of peer hosts due to connection error.")
            self.inactive_hosts.add(peer_host)


    def update_peer_hosts(self):
        """
        Helper method for updating the set of peer hosts, if inactive hosts are found.
        """
        if len(self.inactive_hosts) > 0:
            logger.debug(f'Updating peer hosts. Inactive hosts :{self.inactive_hosts}; Active hosts: {self.peer_hosts}')
            self.peer_hosts = self.peer_hosts - self.inactive_hosts
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
        node.get_history(APPLICATION_PORT, None)

        # We are creating separate threads for server and client
        # so that they can run at same time. The sockets api is blocking.
        thread = Thread(target=node.ui.run, args=[], name="ui")
        thread.start()

    thread = Thread(target=node.start_server, args=[APPLICATION_PORT], name="server")
    thread.start()
