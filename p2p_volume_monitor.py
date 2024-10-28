import sys
import json
import threading
import subprocess
import asyncio
import websockets
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
        self.uri = ""  # Changed from server/port to uri
        self.volume_level = 0
        self.is_muted = False
        self.peers = {}
        self.websocket = None  # Change socket to websocket
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

        self.uri_input = QLineEdit(self)
        self.uri_input.setPlaceholderText("Enter WebSocket URI (wss://...)")
        self.uri_input.setText("wss://speaker-detect.onrender.com:443/ws")
        layout.addWidget(self.uri_input)

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
        if self.websocket is None:
            self.join_room()
        else:
            self.leave_room()

    def join_room(self):
        self.name = self.name_input.text()
        self.room = self.room_input.text()
        self.uri = self.uri_input.text()  # Get URI directly
        if self.name and self.room and self.uri:
            try:
                print(f"Connecting to {self.uri}")  # Debug print
                
                # Get initial volume and mute status
                self.volume_level = self.get_system_volume()
                self.is_muted = self.is_system_muted()
                
                # Start websocket connection in a separate thread
                self.websocket_thread = threading.Thread(
                    target=self.run_websocket_client,
                    args=(self.uri,),  # Pass URI directly
                    daemon=True
                )
                self.websocket_thread.start()
                
                self.status_label.setText(f"Connecting to room: {self.room}")
                self.room_button.setText("Leave Room")
                self.name_input.setEnabled(False)
                self.room_input.setEnabled(False)
                self.uri_input.setEnabled(False) 
            except Exception as e:
                self.status_label.setText(f"Connection error: {str(e)}")
                self.websocket = None
        else:
            self.status_label.setText("Please fill in all fields")

    def run_websocket_client(self, uri):
        async def client():
            try:
                async with websockets.connect(uri) as websocket:
                    self.websocket = websocket
                    
                    # Send join message
                    join_message = {
                        "action": "join",
                        "name": self.name,
                        "room": self.room,
                        "volume": self.volume_level,
                        "muted": self.is_muted
                    }
                    await websocket.send(json.dumps(join_message))
                    
                    # Start receiving messages
                    while True:
                        try:
                            message = await websocket.recv()
                            data = json.loads(message)
                            if data["action"] == "update":
                                self.peers = data["peers"]
                                self.signal_emitter.update_signal.emit()
                        except websockets.exceptions.ConnectionClosed:
                            break
                        except Exception as e:
                            print(f"Error receiving message: {e}")
                            break
                    
            except Exception as e:
                print(f"WebSocket connection error: {e}")
            finally:
                self.websocket = None
                self.signal_emitter.update_signal.emit()

        asyncio.run(client())

    def leave_room(self):
        if self.websocket:
            async def close_connection():
                try:
                    await self.websocket.send(json.dumps({"action": "leave"}))
                    await self.websocket.close()
                except:
                    pass
                finally:
                    self.websocket = None
            
            asyncio.run(close_connection())
            self.status_label.setText("Disconnected")
            self.room_button.setText("Join Room")
            self.name_input.setEnabled(True)
            self.room_input.setEnabled(True)
            self.uri_input.setEnabled(True)  # Enable URI input instead of server/port
            self.peer_list.clear()

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

        if self.websocket is None:
            self.status_label.setText("Not connected")
            self.room_button.setText("Join Room")

    def get_system_volume(self):
        if IS_WINDOWS:
            try:
                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                volume = cast(interface, POINTER(IAudioEndpointVolume))
                level = volume.GetMasterVolumeLevelScalar()
                # Properly release COM objects
                volume.Release()
                interface.Release()
                return int(level * 100)
            except Exception as e:
                print(f"Error getting system volume: {e}")
                return 0
        else:  # macOS
            try:
                result = subprocess.run(['osascript', '-e', 'output volume of (get volume settings)'], capture_output=True, text=True)
                return int(result.stdout.strip())
            except Exception as e:
                print(f"Error getting system volume: {e}")
                return 0

    def is_system_muted(self):
        if IS_WINDOWS:
            try:
                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                volume = cast(interface, POINTER(IAudioEndpointVolume))
                muted = volume.GetMute()
                # Properly release COM objects
                volume.Release()
                interface.Release()
                return muted
            except Exception as e:
                print(f"Error getting mute status: {e}")
                return False
        else:  # macOS
            try:
                result = subprocess.run(['osascript', '-e', 'output muted of (get volume settings)'], capture_output=True, text=True)
                return result.stdout.strip().lower() == 'true'
            except Exception as e:
                print(f"Error getting mute status: {e}")
                return False

    def start_volume_detection(self):
        def check_volume():
            if self.websocket is None:
                return
            new_volume = self.get_system_volume()
            new_mute_status = self.is_system_muted()
            if new_volume != self.volume_level or new_mute_status != self.is_muted:
                self.volume_level = new_volume
                self.is_muted = new_mute_status
                status_text = f"Muted" if self.is_muted else f"Volume: {self.volume_level}"
                self.volume_label.setText(f"Current Status: {status_text}")
                
                async def send_volume_update():
                    try:
                        await self.websocket.send(json.dumps({
                            "action": "volume",
                            "name": self.name,
                            "volume": self.volume_level,
                            "muted": self.is_muted
                        }))
                    except Exception as e:
                        print(f"Error sending volume update: {e}")
                        self.leave_room()
                
                if self.websocket:
                    asyncio.run(send_volume_update())

        self.volume_timer = QTimer()
        self.volume_timer.timeout.connect(check_volume)
        self.volume_timer.start(1000)  # Check every second

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = VolumeMonitorApp()
    ex.show()
    sys.exit(app.exec())
