"""
Talk to lab_server.py over real MCP, the way Claude Code would: start it as a
separate process, list its tools, call them.

    python test_server.py            # offline checks + one live search (needs GEMINI_API_KEY)
"""

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

HERE = Path(__file__).resolve().parent


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    if not cond:
        sys.exit(1)


def text_of(result) -> str:
    return "".join(getattr(c, "text", "") for c in result.content)


async def main():
    params = StdioServerParameters(command=sys.executable, args=[str(HERE / "lab_server.py")], cwd=str(HERE))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = (await session.list_tools()).tools
            print("Tools the server offers:")
            for t in tools:
                print(f"  {t.name}({', '.join(t.input_schema.get('properties', {}))}): {t.description[:70]}...")
            check("the server offers search_notes and read_note", {t.name for t in tools} == {"search_notes", "read_note"})
            check("schemas were generated from the Python type hints",
                  tools[0].input_schema["properties"] and "type" in next(iter(tools[0].input_schema["properties"].values())))

            r = await session.call_tool("read_note", {"path": "knowledge/agent-concepts.md"})
            check("read_note returns a lab file", "Tool descriptions are the interface" in text_of(r))
            r = await session.call_tool("read_note", {"path": "knowledge/agent-concepts.md:53-70"})
            check("read_note accepts a citation as the path", "Tool descriptions" in text_of(r))
            r = await session.call_tool("read_note", {"path": "../../Desktop/anything.md"})
            check("read_note refuses paths outside the lab", "Not a file inside the lab" in text_of(r))
            r = await session.call_tool("read_note", {"path": "05-rag/memory.md"})
            check("read_note refuses memory.md (private)", "private" in text_of(r))

            if "--offline" not in sys.argv:
                r = await session.call_tool("search_notes", {"query": "What is tool poisoning?", "top_k": 2})
                out = text_of(r)
                print("\nLive search result (first 300 chars):\n" + out[:300])
                check("search_notes finds the glossary PDF page", "agent-glossary.pdf p.3" in out)

    print("\nAll lab-server checks passed.")


asyncio.run(main())
