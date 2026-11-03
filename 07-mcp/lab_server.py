"""
An MCP server that exposes my lab notes to ANY MCP client:
Claude Code, Claude Desktop, or my own agent.

Tools:
  search_notes(query, top_k)  semantic search over the lab index (RAG from stage 05)
  read_note(path)             read one file from the lab (.md, .py, .pdf)

Run it directly to check it starts (it then waits for a client on stdin):
    python lab_server.py
Normally a client starts it for you; see README.md.

IMPORTANT for stdio servers: stdout carries the protocol messages. Anything
printed to stdout corrupts them, so all logging goes to stderr.
"""

import contextlib
import os
import sys
from pathlib import Path

from mcp.server.mcpserver import MCPServer

import rag

HERE = Path(__file__).resolve().parent
INDEX_FILE = Path(os.environ.get("LAB_INDEX", HERE.parent / "05-rag" / "index.json"))


def _log(msg: str):
    print(f"[lab-server] {msg}", file=sys.stderr, flush=True)


def _ensure_api_key():
    """The client that starts us may not have GEMINI_API_KEY; on Windows, read the saved user setting."""
    if os.environ.get("GEMINI_API_KEY") or os.name != "nt":
        return
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            os.environ["GEMINI_API_KEY"] = winreg.QueryValueEx(key, "GEMINI_API_KEY")[0]
    except OSError:
        _log("GEMINI_API_KEY not found; search_notes will fail")


# Loaded on first use, so the server starts instantly.
_index, _embed = None, None


def _load():
    global _index, _embed
    if _index is None:
        _ensure_api_key()
        from google import genai
        _index = rag.load_index(INDEX_FILE)
        _embed = rag.gemini_embedder(genai.Client())
        _log(f"loaded {INDEX_FILE.name}: {len(_index['chunks']) if _index else 0} chunks")
    return _index


server = MCPServer(
    "lab-notes",
    instructions="Search and read the user's AI agent lab: journal, notes, stage READMEs, code and PDFs. "
                 "Use search_notes first, then read_note to see a whole file.",
)


@server.tool(description=(
    "Semantic search over the user's AI agent lab notes, code and PDFs. Finds passages similar in "
    "MEANING to the query. Returns numbered passages, each with a citable source like "
    "'journal/2026-10-14.md:12-30' or 'library/paper.pdf p.3'."
))
def search_notes(query: str, top_k: int = 5) -> str:
    index = _load()
    if index is None:
        return f"No index found at {INDEX_FILE}. Build one with 05-rag/index.py."
    with contextlib.redirect_stdout(sys.stderr):  # rag.py may print rate-limit notes: keep stdout clean
        return rag.format_results(rag.search(index, query, _embed, top_k=min(max(top_k, 1), 10)))


@server.tool(description=(
    "Read one file from the user's AI agent lab by its path relative to the lab root "
    "(as shown in search_notes sources, e.g. 'knowledge/agent-concepts.md'). PDFs are returned "
    "as text with '--- page N ---' markers."
))
def read_note(path: str) -> str:
    index = _load()
    root = Path(index["root"]) if index else HERE.parent
    p = (root / path.split(":")[0].split(" p.")[0]).resolve()  # accept a citation as the path
    if root.resolve() not in p.parents or not p.is_file():
        return f"Not a file inside the lab: {path}"
    if p.name in rag.SKIP_FILES:
        return f"{path} is private and not shared."
    if p.suffix.lower() == ".pdf":
        return "\n\n".join(f"--- page {n} ---\n{t}" for n, t in enumerate(rag.read_pdf_pages(p), 1))
    if p.suffix.lower() not in rag.INCLUDE:
        return f"Only {sorted(rag.INCLUDE)} files can be read."
    text = p.read_text(encoding="utf-8", errors="replace")
    return text if len(text) < 50_000 else text[:50_000] + "\n... (truncated)"


if __name__ == "__main__":
    _log(f"starting; index = {INDEX_FILE}")
    server.run(transport="stdio")
