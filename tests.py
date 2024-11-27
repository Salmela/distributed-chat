import unittest
from unittest.mock import Mock, MagicMock
from main import ui, start_server

class UserInterfaceTestCase(unittest.TestCase):

    def test_send_message(self):
        mock_input = Mock()
        mock_input.side_effect = ["Cool example message", KeyboardInterrupt()]
        socket_instance = Mock()
        socket_instance.recv.return_value = 'Cool message from peer'

        mock_socket_factory = Mock()
        mock_socket_factory.return_value = MagicMock()
        mock_socket_factory.return_value.__enter__.return_value = socket_instance

        with self.assertRaises(KeyboardInterrupt):
            ui('123.123.123.123', 456, nickname="Nick", input=mock_input, socket=mock_socket_factory)

        socket_instance.connect.assert_called_with(('123.123.123.123', 456))
        socket_instance.sendall.assert_called_with(b'{"message": "Cool example message", "sender": "Nick"}')

class ServerTestCase(unittest.TestCase):
    def test_receive_connection(self):
        peer_socket = MagicMock()
        peer_socket.recv.side_effect = [b'{"message": "Nice message from peer", "sender": "Rick"}', ""]

        server_socket = Mock()
        server_socket.accept.side_effect = [(peer_socket, None), KeyboardInterrupt]

        mock_socket_factory = Mock()
        mock_socket_factory.return_value = MagicMock()
        mock_socket_factory.return_value.__enter__.return_value = server_socket

        with self.assertRaises(KeyboardInterrupt):
            start_server(socket=mock_socket_factory)

        server_socket.bind.assert_called_with(('0.0.0.0', 65412))
        server_socket.listen.assert_called_with()
        peer_socket.sendall.assert_called_with(b'{"message": "Nice message from peer", "sender": "Rick"}')

if __name__ == '__main__':
    unittest.main()
