"""
TANFINET - Network Monitor Server

HTTP file serving AND WebSocket relay run on a single port (8080).
No second port is needed, so only one firewall rule is required.

Usage:
    python server.py

Open on ANY device on the same network:
    Simulator  -> http://<LAN-IP>:8080/sim.html
    Dashboard  -> http://<LAN-IP>:8080/sla-dashboard.html
"""

import asyncio
import mimetypes
import socket
from pathlib import Path

try:
    import websockets
    from websockets.http11 import Request, Response
    from websockets.datastructures import Headers
except ImportError:
    import subprocess, sys
    print("Installing 'websockets' package...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets"])
    import websockets
    from websockets.http11 import Request, Response
    from websockets.datastructures import Headers

PORT = 8080
DIR  = Path(__file__).parent.resolve()

# -- Connected clients --------------------------------------------------------
CLIENTS: set = set()

# -- WebSocket relay ---------------------------------------------------------
async def relay(websocket):
    CLIENTS.add(websocket)
    try:
        async for message in websocket:
            dead = set()
            for client in CLIENTS - {websocket}:
                try:
                    await client.send(message)
                except Exception:
                    dead.add(client)
            CLIENTS.difference_update(dead)
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        CLIENTS.discard(websocket)

# -- HTTP handler (WebSocket upgrade requests pass through) ------------------
async def http_handler(connection, request: Request):
    # WebSocket upgrade requests must pass through - return None to proceed
    if request.headers.get("Upgrade", "").lower() == "websocket":
        return None

    # Resolve file path safely
    raw = request.path.split("?")[0].lstrip("/") or "sim.html"
    try:
        target = (DIR / raw).resolve()
        target.relative_to(DIR)  # blocks path traversal
    except ValueError:
        return Response(403, "Forbidden",
                        Headers([("Content-Type", "text/plain")]),
                        b"403 Forbidden")

    if target.is_file():
        body = target.read_bytes()
        mime, _ = mimetypes.guess_type(str(target))
        return Response(
            200, "OK",
            Headers([
                ("Content-Type",   mime or "application/octet-stream"),
                ("Content-Length", str(len(body))),
            ]),
            body,
        )

    return Response(404, "Not Found",
                    Headers([("Content-Type", "text/plain")]),
                    b"404 Not Found")

# -- LAN IP helper -----------------------------------------------------------
def get_lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()

# -- Entry point -------------------------------------------------------------
async def main():
    lan = get_lan_ip()
    async with websockets.serve(
        relay, "0.0.0.0", PORT,
        process_request=http_handler,
    ):
        print()
        print("  +------------------------------------------------------+")
        print("  |          TANFINET Network Monitor Server             |")
        print("  +------------------------------------------------------+")
        print()
        print("  This device (localhost):")
        print(f"    Simulator  ->  http://localhost:{PORT}/sim.html")
        print(f"    Dashboard  ->  http://localhost:{PORT}/sla-dashboard.html")
        print()
        print("  Other devices on your network:")
        print(f"    Simulator  ->  http://{lan}:{PORT}/sim.html")
        print(f"    Dashboard  ->  http://{lan}:{PORT}/sla-dashboard.html")
        print()
        print(f"  HTTP + WebSocket on a single port ({PORT}). Only port 8080 needed.")
        print("  Press Ctrl+C to stop.")
        print()
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())
