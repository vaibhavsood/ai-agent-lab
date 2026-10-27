"""
Build the RAG index: chunk the lab's .md/.py files, embed them, save index.json.

    python index.py                 # indexes the whole lab (the parent folder)
    python index.py --root C:/notes # or any folder of notes

Re-run it whenever the notes change; the agent warns you when it's stale.
Free tier: file contents are sent to Google, so index only the lab or other
non-confidential folders. memory.md is always skipped.
"""

import argparse
import os
import sys
import time
from collections import Counter
from pathlib import Path

from google import genai

import rag

INDEX_FILE = Path(__file__).parent / "index.json"


def main():
    parser = argparse.ArgumentParser(description="Build the RAG index")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]), help="Folder to index (default: the lab)")
    args = parser.parse_args()
    if not os.environ.get("GEMINI_API_KEY"):
        sys.exit("GEMINI_API_KEY is not set. Open a NEW terminal after setting it.")

    root = Path(args.root).resolve()
    chunks = rag.collect_chunks(root)
    files = Counter(c["source"] for c in chunks)
    print(f"Indexing {root}\n{len(chunks)} chunks from {len(files)} files "
          f"(avg {sum(len(c['text']) for c in chunks) // max(len(chunks), 1)} chars per chunk)")

    t = time.time()
    index = rag.build_index(root, rag.gemini_embedder(genai.Client()))
    rag.save_index(index, INDEX_FILE)
    print(f"Embedded with {rag.EMBED_MODEL} in {time.time() - t:.1f}s -> {INDEX_FILE.name} "
          f"({INDEX_FILE.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
