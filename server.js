const WebSocket = require("ws");
const PORT = process.env.PORT || 10000;

// Initialize server state
const clients = new Map();
const rooms = new Map();

// Create WebSocket server
const wss = new WebSocket.Server({ port: PORT });
console.info(`Server listening on port ${PORT}`);

wss.on("connection", (ws, req) => {
  console.info(`New connection from ${req.socket.remoteAddress}`);

  ws.on("message", (data) => {
    try {
      const message = JSON.parse(data);

      switch (message.action) {
        case "join":
          const { name, room, volume, muted } = message;
          clients.set(ws, { name, room, volume, muted });

          if (!rooms.has(room)) {
            rooms.set(room, new Set());
          }
          rooms.get(room).add(ws);
          updateRoom(room);
          console.info(
            `${name} joined room ${room} with volume ${volume} and muted status ${muted}`
          );
          break;

        case "volume":
          const clientData = clients.get(ws);
          clientData.volume = message.volume;
          clientData.muted = message.muted;
          updateRoom(clientData.room);
          console.info(
            `${message.name} updated volume: ${message.volume}, muted: ${message.muted}`
          );
          break;

        case "leave":
          removeClient(ws);
          break;
      }
    } catch (error) {
      console.error("Error processing message:", error);
    }
  });

  ws.on("close", () => {
    removeClient(ws);
  });

  ws.on("error", (error) => {
    console.error("WebSocket error:", error);
    removeClient(ws);
  });
});

function removeClient(ws) {
  if (clients.has(ws)) {
    const { name, room } = clients.get(ws);
    clients.delete(ws);

    if (rooms.has(room)) {
      rooms.get(room).delete(ws);
      updateRoom(room);

      if (rooms.get(room).size === 0) {
        rooms.delete(room);
      }
    }
    console.info(`${name} left room ${room}`);
  }
}

function updateRoom(room) {
  if (rooms.has(room)) {
    const roomClients = rooms.get(room);
    const peers = {};

    for (const client of roomClients) {
      const { name, volume, muted } = clients.get(client);
      peers[name] = { volume, muted };
    }

    const updateMessage = JSON.stringify({
      action: "update",
      peers,
    });

    for (const client of roomClients) {
      try {
        client.send(updateMessage);
      } catch (error) {
        console.error("Error sending update to client:", error);
        removeClient(client);
      }
    }
  }
}
