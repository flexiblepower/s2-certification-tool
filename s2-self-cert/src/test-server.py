# simple_server.py
import asyncio
import websockets

async def handler(websocket, path):
    print(f"Client connected from {websocket.remote_address}")
    try:
        async for message in websocket:
            print(f"Received message: {message}")
            # await websocket.send(f"Echo: {message}")
    except websockets.exceptions.ConnectionClosedOK:
        print(f"Client {websocket.remote_address} disconnected")
    except Exception as e:
        print(f"Error with client {websocket.remote_address}: {e}")

async def main():
    async with websockets.serve(handler, "localhost", 8765):
        print("WebSocket server started on ws://localhost:8765")
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())
