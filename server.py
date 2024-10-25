import socket
import json
import threading
import logging
import os

logging.basicConfig(level=logging.INFO)

clients = {}
rooms = {}

def handle_client(client_socket, client_address):
    while True:
        try:
            data = client_socket.recv(1024).decode()
            if not data:
                break
            message = json.loads(data)
            
            if message["action"] == "join":
                name = message["name"]
                room = message["room"]
                volume = message["volume"]
                muted = message["muted"]
                clients[client_socket] = {"name": name, "room": room, "volume": volume, "muted": muted}
                if room not in rooms:
                    rooms[room] = []
                rooms[room].append(client_socket)
                update_room(room)
                logging.info(f"{name} joined room {room} with volume {volume} and muted status {muted}")
            
            elif message["action"] == "volume":
                name = message["name"]
                volume = message["volume"]
                muted = message["muted"]
                room = clients[client_socket]["room"]
                clients[client_socket]["volume"] = volume
                clients[client_socket]["muted"] = muted
                update_room(room)
                logging.info(f"{name} updated volume: {volume}, muted: {muted}")
            
            elif message["action"] == "leave":
                remove_client(client_socket)
                break
        
        except json.JSONDecodeError:
            logging.error("Received invalid JSON data")
        except Exception as e:
            logging.error(f"Error handling client: {e}")
            break
    
    remove_client(client_socket)
    client_socket.close()

def remove_client(client_socket):
    if client_socket in clients:
        name = clients[client_socket]["name"]
        room = clients[client_socket]["room"]
        del clients[client_socket]
        if room in rooms:
            rooms[room].remove(client_socket)
            update_room(room)
            if not rooms[room]:
                del rooms[room]
        logging.info(f"{name} left room {room}")

def update_room(room):
    if room in rooms:
        room_clients = rooms[room]
        peers = {clients[client]["name"]: {"volume": clients[client]["volume"], "muted": clients[client]["muted"]} for client in room_clients}
        update_message = json.dumps({"action": "update", "peers": peers})
        for client in room_clients:
            try:
                client.send(update_message.encode())
            except Exception as e:
                logging.error(f"Error sending update to client: {e}")
                remove_client(client)

def start_server():
    port = int(os.environ.get("PORT", 10000))  # Render uses PORT=10000 by default
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(('0.0.0.0', port))  # Bind to 0.0.0.0 instead of localhost
    server.listen(5)
    logging.info(f"Server listening on port {port}")

    while True:
        client_socket, client_address = server.accept()
        logging.info(f"New connection from {client_address}")
        client_thread = threading.Thread(target=handle_client, args=(client_socket, client_address))
        client_thread.start()

if __name__ == "__main__":
    start_server()
