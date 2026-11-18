"""
Talk MCP to lab_server.py WITHOUT the MCP library: just subprocess + json.
Prints every message in both directions, so you can see the actual protocol.

    python raw_mcp_client.py

The stdio transport: one JSON-RPC 2.0 message per line.
  client -> server: written to the server's stdin
  server -> client: read from the server's stdout
  server logs:      stderr (not part of the protocol)
"""

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

server = subprocess.Popen(
    [sys.executable, str(HERE / "lab_server.py")],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    text=True, encoding="utf-8", bufsize=1,
)


def send(message: dict):
    line = json.dumps(message)
    print(f"\n>>> CLIENT -> SERVER\n{json.dumps(message, indent=2)}")
    server.stdin.write(line + "\n")  # one message = one line
    server.stdin.flush()


def receive() -> dict:
    line = server.stdout.readline()
    message = json.loads(line)
    shown = json.dumps(message, indent=2)
    print(f"\n<<< SERVER -> CLIENT\n{shown if len(shown) < 1500 else shown[:1500] + chr(10) + '  ... (truncated for display)'}")
    return message


# 1. Handshake: say who we are and which protocol version we speak.
send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2026-07-28",
    "capabilities": {},
    "clientInfo": {"name": "raw-client", "version": "0.1"},
}})
receive()

# 2. A NOTIFICATION (no "id"): "handshake done". The server sends no reply.
send({"jsonrpc": "2.0", "method": "notifications/initialized"})

# 3. Discovery.
send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
receive()

# 4. Call a tool.
send({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
      "params": {"name": "read_note", "arguments": {"path": "CLAUDE.md"}}})
receive()

# 5. Call a tool that doesn't exist.
send({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
      "params": {"name": "delete_everything", "arguments": {}}})
receive()

# 6. A method MCP doesn't have at all.
send({"jsonrpc": "2.0", "id": 5, "method": "make/coffee"})
receive()

# Closing stdin is how a stdio client says goodbye; the server then exits.
server.stdin.close()
server.wait(timeout=10)
print(f"\nServer exited with code {server.returncode}")
