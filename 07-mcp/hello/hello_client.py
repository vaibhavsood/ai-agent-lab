import asyncio
import sys

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def main():
    server = StdioServerParameters(command=sys.executable, args=["hello_server.py"])

    async with stdio_client(server) as (read, write):        # start the server process
        async with ClientSession(read, write) as session:    # speak MCP over its stdin/stdout
            await session.initialize()                       # handshake

            tools = await session.list_tools()               # "what can you do?"
            print("Server offers:", [t.name for t in tools.tools])

            result = await session.call_tool("hello", {"name": "World"})   # "do it"
            print("Server says: ", result.content[0].text)


asyncio.run(main())
