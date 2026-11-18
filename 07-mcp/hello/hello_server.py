from mcp.server.mcpserver import MCPServer

server = MCPServer("hello-server")


@server.tool(description="Say hello to someone.")
def hello(name: str) -> str:
    return f"Hello, {name}!"


server.run(transport="stdio")
