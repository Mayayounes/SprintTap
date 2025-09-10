# server.py
import time
import asyncio
import json
from typing import Dict, Any, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restrict in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory simple room management
rooms: Dict[str, Dict[str, Any]] = {}  # room_id -> room data

# Utility
def now() -> float:
    return time.time()  # seconds since epoch, float


async def broadcast(room_id: str, message: dict):
    """Send message JSON to all connected websockets in the room (best-effort)."""
    room = rooms.get(room_id)
    if not room:
        return
    websockets = list(room["clients"].values())
    data = json.dumps(message)
    for ws in websockets:
        try:
            if ws.application_state == WebSocketState.CONNECTED:
                await ws.send_text(data)
        except Exception:
            pass


@app.websocket("/ws/{room_id}/{username}")
async def ws_room(websocket: WebSocket, room_id: str, username: str):
    """
    WebSocket protocol (JSON messages). Client must send/receive messages of shape:
      { "type": "timesync", "client_time": <float> }  -> server replies with {"type":"timesync_resp", "server_time": <float>}
      { "type": "join" } -> server responds with current room info
      server can send {"type":"start", "start_time": <float>, "duration": 15}
      client sends {"type":"result", "count": <int>, "timestamps": [<float>, ...], "offset": <float>}
    """
    await websocket.accept()
    # create room if needed
    room = rooms.setdefault(room_id, {"clients": {}, "results": {}, "start_time": None, "duration": 15})
    # register client
    room["clients"][username] = websocket
    try:
        # notify others that user joined
        await broadcast(room_id, {"type": "presence", "users": list(room["clients"].keys())})

        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            typ = msg.get("type")

            if typ == "timesync":
                # client asks for server time to estimate offset
                # reply immediately with server time
                await websocket.send_text(json.dumps({"type": "timesync_resp", "server_time": now()}))

            elif typ == "join":
                # send room info
                await websocket.send_text(json.dumps({
                    "type": "room_info",
                    "users": list(room["clients"].keys()),
                    "start_time": room["start_time"],
                    "duration": room["duration"]
                }))

            elif typ == "request_start":
                # Only allow if sender exists; simple server check. In extendable version check admin privileges.
                # Create a start time sufficiently in the future
                lead = 5.0  # seconds to wait before start (allows syncing)
                start_time = now() + lead
                room["start_time"] = start_time
                room["results"] = {}
                # broadcast start
                await broadcast(room_id, {"type": "start", "start_time": start_time, "duration": room["duration"]})
                # also schedule automatic end broadcast after duration + small buffer
                asyncio.create_task(end_round_after(room_id, start_time + room["duration"] + 2.0))

            elif typ == "result":
                # client submits reported taps and offset estimate
                # msg should contain: "count", "timestamps" (list of floats in client local time),
                # and "offset" such that server_time ~= client_time + offset
                if room.get("start_time") is None:
                    await websocket.send_text(json.dumps({"type": "error", "reason": "no active round"}))
                    continue

                client_count = int(msg.get("count", 0))
                client_offset = float(msg.get("offset", 0.0))
                timestamps = msg.get("timestamps", [])  # client local times (seconds)
                # validate: convert timestamps -> server time using offset
                valid = 0
                start = room["start_time"]
                end = start + room["duration"]
                for t_local in timestamps:
                    t_server = float(t_local) + client_offset
                    if t_server >= start and t_server <= end:
                        valid += 1
                # store best valid for user
                room["results"][username] = {"reported": client_count, "validated": valid, "offset": client_offset}
                # optionally notify others partial result
                await broadcast(room_id, {"type": "partial_result", "user": username, "validated": valid})
                # If all clients have submitted, finalize early
                if len(room["results"]) == len(room["clients"]):
                    await finalize_round(room_id)

            # other message types can be handled here...
    except WebSocketDisconnect:
        # remove client
        room["clients"].pop(username, None)
        room["results"].pop(username, None)
        await broadcast(room_id, {"type": "presence", "users": list(room["clients"].keys())})


async def end_round_after(room_id: str, when: float):
    """Wait until 'when' server time, then finalize if not already done."""
    await asyncio.sleep(max(0, when - now()))
    # finalize
    await finalize_round(room_id)


async def finalize_round(room_id: str):
    room = rooms.get(room_id)
    if not room:
        return
    # compute winner by validated taps
    results = room.get("results", {})
    # any users that didn't submit -> zero validated
    for user in room["clients"].keys():
        if user not in results:
            results[user] = {"reported": 0, "validated": 0, "offset": 0.0}
    # build ranking
    ranking = sorted(
        [{"user": u, "validated": r["validated"], "reported": r["reported"]} for u, r in results.items()],
        key=lambda x: (-x["validated"], -x["reported"])
    )
    room["last_ranking"] = ranking
    # broadcast results then clear start_time
    await broadcast(room_id, {"type": "round_end", "ranking": ranking})
    room["start_time"] = None
    room["results"] = {}
