# Multiplayer Tap Sprint Game

## Overview
This is a multiplayer browser game where players join the same room and compete
to see who can tap the fastest in a 15-second sprint. The winner is the player
with the most taps.

## Methodology
- **Fair Start:** The server chooses a start time (in UTC) a few seconds in the future.
- **Clock Synchronization:** Each client exchanges "ping-pong" messages with the
  server to estimate clock offset and latency.
- **Validation:** Players log each tap with a timestamp. The server verifies
  that the taps happened within the 15-second window using the synchronized clock.

## How to Run
1. Start server:
   ```bash
   pip install -r requirements.txt
   uvicorn server:app --host 0.0.0.0 --port 8000
-----------------------------------------------------------
Code Explanation (Simple)

1. server.js

Uses WebSockets to let many players talk to each other in real time.
Keeps track of players in rooms.
Decides the start time for the round (to be fair).
Collects scores from all players and shows results.

2. client.html

Connects to the server with WebSockets.
Shows the countdown and game timer.
Counts your taps (spacebar or mouse).
Sends your final score to the server.

Shows results for everyone at the end.

-------------------------------------------------
Challenges I Faced:

1. WebSocket issue
At first, the client URL was wrong (ws://:8000/...), then I fixed it by using location.hostname.

2. score issue
The score was not being sent correctly from the client to the server, so results were always showing 0.

-------------------------------------------------------
propmts used:
1. How to make multiplayer tap sprint game with WebSockets.
2. How to run from one device
3. The score is appearing 0 at the end

what AI knows : told me to debug from network tab to know score , i ran on 2 different browsers instead of friends