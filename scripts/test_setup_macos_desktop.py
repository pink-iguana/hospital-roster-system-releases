"""Check RustDesk status handling without requiring macOS or remote access."""

import importlib.util
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    'desktop', Path(__file__).with_name('setup-macos-desktop.py'))
desktop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desktop)


class DesktopStatusTests(unittest.TestCase):
    def exchange(self, replies):
        """Serve the real Unix IPC protocol, including fragmented responses."""
        with tempfile.TemporaryDirectory(dir='/tmp') as directory:
            address = str(Path(directory) / 'ipc')
            errors = []
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
                listener.bind(address)
                listener.listen(1)
                listener.settimeout(5)

                def serve():
                    try:
                        with listener.accept()[0] as connection:
                            connection.settimeout(5)
                            for index, reply in enumerate(replies):
                                header = connection.recv(1)
                                if not header:
                                    return
                                size = header[0] >> 2
                                payload = bytearray()
                                while len(payload) < size:
                                    part = connection.recv(size - len(payload))
                                    if not part:
                                        raise AssertionError('Request closed early')
                                    payload.extend(part)
                                request = json.loads(payload)
                                expected = ({'t': 'Config', 'c': ['id', None]},
                                            {'t': 'OnlineStatus', 'c': None})[index]
                                self.assertEqual(request, expected)
                                if reply is None:
                                    return
                                data = json.dumps(reply).encode()
                                width = 1 if len(data) <= 63 else 2
                                frame = ((len(data) << 2) | (width - 1)).to_bytes(width, 'little') + data
                                for value in frame:
                                    connection.sendall(bytes([value]))
                    except BaseException as error:
                        errors.append(error)

                worker = threading.Thread(target=serve, daemon=True)
                worker.start()
                try:
                    return desktop.read_desktop_status(address)
                finally:
                    worker.join(6)
                    self.assertFalse(worker.is_alive())
                    if errors:
                        raise errors[0]

    def test_active_service_id_and_online_status(self):
        result = self.exchange([
            {'t': 'Config', 'c': ['id', '123456789']},
            {'t': 'OnlineStatus', 'c': [1500, True]},
        ])
        self.assertEqual(result, ('123456789', 1500, True))

    def test_two_byte_frame_header(self):
        remote_id = '1234567890123456'
        result = self.exchange([
            {'t': 'Config', 'c': ['id', remote_id], 'padding': 'x' * 100},
            {'t': 'OnlineStatus', 'c': [1500, True]},
        ])
        self.assertEqual(result[0], remote_id)

    def test_closed_connection_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'connection closed'):
            self.exchange([None])

    def test_invalid_id_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'no usable ID'):
            self.exchange([
                {'t': 'Config', 'c': ['id', '000000000']},
                {'t': 'OnlineStatus', 'c': [1500, True]},
            ])

    def test_invalid_status_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'Invalid RustDesk desktop online status'):
            self.exchange([
                {'t': 'Config', 'c': ['id', '123456789']},
                {'t': 'OnlineStatus', 'c': ['online', True]},
            ])

    def test_stored_id_does_not_count_as_online(self):
        with patch.object(desktop, 'read_desktop_status', return_value=('123456789', 0, True)), \
                patch.object(desktop.time, 'sleep'), patch('builtins.print'):
            with self.assertRaisesRegex(RuntimeError, 'did not become online'):
                desktop.wait_for_desktop_online()

    def test_unconfirmed_registration_does_not_count_as_online(self):
        with patch.object(desktop, 'read_desktop_status', return_value=('123456789', 1500, False)), \
                patch.object(desktop.time, 'sleep'), patch('builtins.print'):
            with self.assertRaisesRegex(RuntimeError, 'key_confirmed=False'):
                desktop.wait_for_desktop_online()

    def test_waits_for_network_then_returns_active_id(self):
        states = [OSError('socket not ready'), ('123456789', 0, False),
                  ('987654321', 1500, True)]
        with patch.object(desktop, 'read_desktop_status', side_effect=states), \
                patch.object(desktop.time, 'sleep'), patch('builtins.print'):
            self.assertEqual(desktop.wait_for_desktop_online(), '987654321')


if __name__ == '__main__':
    unittest.main()
