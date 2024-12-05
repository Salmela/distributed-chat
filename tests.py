import unittest
from unittest.mock import Mock, MagicMock, call
from main import Node

class UserInterfaceTestCase(unittest.TestCase):

    def test_send_message(self):
        node = Node(['123.123.123.123'], "Nick")
        mock_input = Mock()
        mock_input.side_effect = ["Cool example message", KeyboardInterrupt()]
        socket_instance = Mock()
        socket_instance.recv.return_value = '{"type": "NEW_NODES", "nodes": ["123.123.123.123"]}'

        mock_socket_factory = Mock()
        mock_socket_factory.return_value = MagicMock()
        mock_socket_factory.return_value.__enter__.return_value = socket_instance

        with self.assertRaises(KeyboardInterrupt):
            node.ui(456, input=mock_input, socket=mock_socket_factory)

        socket_instance.connect.assert_called_with(('123.123.123.123', 456))
        socket_instance.sendall.assert_has_calls([
            call(b'{"type": "GET_NODES"}'),
            call(b'{"type": "NEW_NODE"}'),
            call(b'{"type": "msg", "message": "Cool example message", "sender": "Nick"}'),
        ])

class ServerTestCase(unittest.TestCase):
    def test_receive_connection(self):
        node = Node([], "Rick")
        peer_socket = MagicMock()
        peer_socket.recv.side_effect = [b'{"type": "msg", "message": "Nice message from peer", "sender": "Rick"}', ""]

        server_socket = Mock()
        server_socket.accept.side_effect = [(peer_socket, None), KeyboardInterrupt]

        mock_socket_factory = Mock()
        mock_socket_factory.return_value = MagicMock()
        mock_socket_factory.return_value.__enter__.return_value = server_socket

        with self.assertRaises(KeyboardInterrupt):
            node.start_server(socket=mock_socket_factory)

        server_socket.bind.assert_called_with(('0.0.0.0', 65412))
        server_socket.listen.assert_called_with()
        peer_socket.sendall.assert_called_with(b'{"type": "ack", "message": "Received Nice message from peer from Rick", "sender": "Rick"}')

if __name__ == '__main__':
    unittest.main()
