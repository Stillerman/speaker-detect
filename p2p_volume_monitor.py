import sys
import json
import socket
import threading
import subprocess
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QPushButton, QLineEdit, QListWidget, QListWidgetItem
from PyQt6.QtCore import QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QColor

# Detect the operating system
IS_WINDOWS = sys.platform.startswith('win')

if IS_WINDOWS:
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

class SignalEmitter(QObject):
    update_signal = pyqtSignal()

class VolumeMonitorApp(QWidget):
    def __init__(self):
        super().__init__()
        self.name = ""
        self.room = ""
        self.server = ""
        self.port = ""
        self.volume_level = 0
        self.is_muted = False
        self.peers = {}
        self.socket = None
        self.signal_emitter = SignalEmitter()
        self.signal_emitter.update_signal.connect(self.update_peer_list)
        self.initUI()
        self.start_volume_detection()

    def initUI(self):
        layout = QVBoxLayout()

        self.name_input = QLineEdit(self)
        self.name_input.setPlaceholderText("Enter your name")
        layout.addWidget(self.name_input)

        self.room_input = QLineEdit(self)
        self.room_input.setPlaceholderText("Enter room name")
        layout.addWidget(self.room_input)

        self.server_input = QLineEdit(self)
        self.server_input.setPlaceholderText("Enter server address")
        layout.addWidget(self.server_input)

        self.port_input = QLineEdit(self)
        self.port_input.setPlaceholderText("Enter port number")
        layout.addWidget(self.port_input)

        self.room_button = QPushButton("Join Room", self)
        self.room_button.clicked.connect(self.toggle_room)
        layout.addWidget(self.room_button)

        self.status_label = QLabel("Not connected", self)
        layout.addWidget(self.status_label)

        self.peer_list = QListWidget(self)
        layout.addWidget(self.peer_list)

        self.volume_label = QLabel("Current Volume: 0", self)
        layout.addWidget(self.volume_label)

        self.setLayout(layout)
        self.setWindowTitle('P2P Volume Monitor')
        self.setGeometry(300, 300, 300, 400)

    def toggle_room(self):
        if self.socket is None:
            self.join_room()
        else:
            self.leave_room()

    def join_room(self):
        self.name = self.name_input.text()
        self.room = self.room_input.text()
        self.server = self.server_input.text()
        self.port = self.port_input.text()
        if self.name and self.room and self.server and self.port:
            try:
                port = int(self.port)
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.connect((self.server, port))
                
                # Get initial volume and mute status
                self.volume_level = self.get_system_volume()
                self.is_muted = self.is_system_muted()
                
                # Send join message with initial volume and mute status
                join_message = {
                    "action": "join",
                    "name": self.name,
                    "room": self.room,
                    "volume": self.volume_level,
                    "muted": self.is_muted
                }
                self.socket.send(json.dumps(join_message).encode())
                
                threading.Thread(target=self.listen_for_messages, daemon=True).start()
                
                self.status_label.setText(f"Connected to room: {self.room}")
                self.room_button.setText("Leave Room")
                self.name_input.setEnabled(False)
                self.room_input.setEnabled(False)
                self.server_input.setEnabled(False)
                self.port_input.setEnabled(False)
                
                # Update the volume label
                status_text = f"Muted" if self.is_muted else f"Volume: {self.volume_level}"
                self.volume_label.setText(f"Current Status: {status_text}")
            except ValueError:
                self.status_label.setText("Invalid port number")
                self.socket.close()
                self.socket = None
            except Exception as e:
                self.status_label.setText(f"Connection error: {str(e)}")
                self.socket.close()
                self.socket = None
        else:
            self.status_label.setText("Please fill in all fields")

    def leave_room(self):
        if self.socket:
            self.socket.send(json.dumps({"action": "leave"}).encode())
            self.socket.close()
            self.socket = None
        self.peers = {}
        self.update_peer_list()
        self.status_label.setText("Not connected")
        self.room_button.setText("Join Room")
        self.name_input.setEnabled(True)
        self.room_input.setEnabled(True)
        self.server_input.setEnabled(True)
        self.port_input.setEnabled(True)

    def listen_for_messages(self):
        while self.socket:
            try:
                data = self.socket.recv(1024).decode()
                if not data:
                    break
                message = json.loads(data)
                if message["action"] == "update":
                    self.peers = message["peers"]
                    self.signal_emitter.update_signal.emit()
            except json.JSONDecodeError:
                print("Received invalid JSON data")
            except Exception as e:
                print(f"Error in listen_for_messages: {e}")
                break
        self.socket = None
        self.signal_emitter.update_signal.emit()
        self.name_input.setEnabled(True)
        self.room_input.setEnabled(True)
        self.room_button.setText("Join Room")

    def update_peer_list(self):
        self.peer_list.clear()
        for name, status in self.peers.items():
            volume, muted = status['volume'], status['muted']
            status_text = f"Muted" if muted else f"Volume {volume}"
            item = QListWidgetItem(f"{name}: {status_text}")
            if muted or volume == 0:
                item.setBackground(QColor('#90EE90'))  # Light green
            else:
                item.setBackground(QColor('#FFB6C1'))  # Light red
            self.peer_list.addItem(item)

        if self.socket is None:
            self.status_label.setText("Not connected")
            self.room_button.setText("Join Room")

    def get_system_volume(self):
        if IS_WINDOWS:
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            return int(volume.GetMasterVolumeLevelScalar() * 100)
        else:  # macOS
            try:
                result = subprocess.run(['osascript', '-e', 'output volume of (get volume settings)'], capture_output=True, text=True)
                return int(result.stdout.strip())
            except Exception as e:
                print(f"Error getting system volume: {e}")
                return 0

    def is_system_muted(self):
        if IS_WINDOWS:
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            return volume.GetMute()
        else:  # macOS
            try:
                result = subprocess.run(['osascript', '-e', 'output muted of (get volume settings)'], capture_output=True, text=True)
                return result.stdout.strip().lower() == 'true'
            except Exception as e:
                print(f"Error getting mute status: {e}")
                return False

    def start_volume_detection(self):
        def check_volume():
            if self.socket is None:
                return
            new_volume = self.get_system_volume()
            new_mute_status = self.is_system_muted()
            if new_volume != self.volume_level or new_mute_status != self.is_muted:
                self.volume_level = new_volume
                self.is_muted = new_mute_status
                status_text = f"Muted" if self.is_muted else f"Volume: {self.volume_level}"
                self.volume_label.setText(f"Current Status: {status_text}")
                try:
                    self.socket.send(json.dumps({
                        "action": "volume",
                        "name": self.name,
                        "volume": self.volume_level,
                        "muted": self.is_muted
                    }).encode())
                except Exception as e:
                    print(f"Error sending volume update: {e}")
                    self.leave_room()

        self.volume_timer = QTimer()
        self.volume_timer.timeout.connect(check_volume)
        self.volume_timer.start(1000)  # Check every second

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = VolumeMonitorApp()
    ex.show()
    sys.exit(app.exec())
