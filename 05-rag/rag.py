"""
The retrieval half of RAG: chunk files, embed chunks, save an index, search it.

No vector database: the index is a JSON file and similarity is plain Python.
That's fine for hundreds of chunks; a vector DB earns its place at many thousands.
"""

import json
import math
import os
import re
import time
from datetime import datetime
from pathlib import Path

EMBED_MODEL = "gemini-embedding-2"  # free tier
DIMENSIONS = 768  # shortened from 3072: ~4x smaller index, little quality loss
MAX_CHARS = 800  # target chunk size
MIN_CHARS = 300  # don't start a new chunk at a heading until we have this much (avoids tiny fragments)
BATCH = 90  # free tier: 100 embeddings per minute, and EACH TEXT in a batch counts as one

INCLUDE = {".md", ".py", ".pdf"}
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", "sandbox"}
SKIP_FILES = {"memory.md"}  # personal; never sent to the free tier

# --------------------------------------------------------------------------
# 1. CHUNKING: split files into passages, remembering where each came from
# --------------------------------------------------------------------------


def _starts_section(path: str, line: str) -> bool:
    if path.endswith(".md"):
        return line.startswith("#")
    return line.startswith(("def ", "class ", "# ----"))  # top-level Python blocks


def chunk_file(path: str, text: str, max_chars: int = MAX_CHARS, min_chars: int | None = None) -> list[dict]:
    """Split one file into chunks of ~max_chars, breaking at headings/defs once a chunk has min_chars."""
    min_chars = MIN_CHARS if min_chars is None else min_chars
    chunks, buf, start, size = [], [], 1, 0
    lines = text.splitlines()

    def emit(end_line):
        body = "\n".join(buf).strip()
        if len(body.replace(" ", "")) >= 20:  # skip near-empty chunks
            chunks.append({"source": path, "start": start, "end": end_line, "text": body})

    for n, line in enumerate(lines, 1):
        if buf and ((_starts_section(path, line) and size >= min_chars) or size + len(line) > max_chars):
            emit(n - 1)
            buf, size, start = [], 0, n
        buf.append(line)
        size += len(line) + 1
    if buf:
        emit(len(lines))
    return chunks


def read_pdf_pages(path: Path) -> list[str]:
    """Extract the text of each page. Scanned PDFs (images of text) give empty pages."""
    from pypdf import PdfReader

    return [page.extract_text() or "" for page in PdfReader(str(path)).pages]


def chunk_pdf(path: str, pages: list[str], max_chars: int = MAX_CHARS) -> list[dict]:
    """Chunk a PDF page by page, so every chunk can be cited by page number."""
    chunks = []
    for page_no, text in enumerate(pages, 1):
        lines = [" ".join(l.split()) for l in text.splitlines()]  # tidy PDF spacing
        buf, size = [], 0
        for line in lines + [None]:  # None = end of page: flush what's left
            if buf and (line is None or size + len(line) > max_chars):
                body = "\n".join(buf).strip()
                if len(body.replace(" ", "")) >= 20:
                    chunks.append({"source": path, "start": page_no, "end": page_no, "unit": "page", "text": body})
                buf, size = [], 0
            if line:
                buf.append(line)
                size += len(line) + 1
    return chunks


def collect_chunks(root: Path) -> list[dict]:
    """All chunks under root, with exact duplicates merged.

    The lab has one copy of agent.py per stage, so the same tool code appears
    6 times. Without dedup, a search would return 5 copies of one passage.
    """
    chunks, by_text = [], {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            p = Path(dirpath, name)
            if p.suffix in INCLUDE and name not in SKIP_FILES:
                rel = p.relative_to(root).as_posix()
                if p.suffix == ".pdf":
                    try:
                        file_chunks = chunk_pdf(rel, read_pdf_pages(p))
                    except Exception as e:  # damaged or encrypted PDF: skip it, don't stop indexing
                        print(f"  skipped {rel}: can't read PDF ({type(e).__name__})")
                        continue
                    if not file_chunks:
                        print(f"  skipped {rel}: no text found (scanned PDF? would need OCR)")
                        continue
                else:
                    file_chunks = chunk_file(rel, p.read_text(encoding="utf-8", errors="replace"))
                for c in file_chunks:
                    if c["text"] in by_text:
                        by_text[c["text"]].setdefault("also_in", []).append(f"{rel}:{c['start']}-{c['end']}")
                    else:
                        by_text[c["text"]] = c
                        chunks.append(c)
    return chunks

# --------------------------------------------------------------------------
# 2. EMBEDDING: text -> vector of numbers (similar meaning = similar vectors)
# --------------------------------------------------------------------------


def _normalize(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [round(x / n, 5) for x in v]


def gemini_embedder(client):
    """Returns embed(texts, is_query) -> list of normalized vectors."""
    from google.genai import types

    def call(contents, is_query):
        """One embedding request; on a 429, wait as long as Google asks, up to 3 times."""
        for attempt in range(4):
            try:
                return client.models.embed_content(
                    model=EMBED_MODEL, contents=contents,
                    config={"task_type": "RETRIEVAL_QUERY" if is_query else "RETRIEVAL_DOCUMENT",
                            "output_dimensionality": DIMENSIONS},
                )
            except Exception as e:
                if getattr(e, "code", None) != 429 or attempt == 3:
                    raise
                m = re.search(r"retry in ([\d.]+)s", str(e))
                wait = float(m.group(1)) + 1 if m else 60
                print(f"[rate limit] free tier quota reached; waiting {wait:.0f}s as the API asks")
                time.sleep(wait)

    def embed(texts: list[str], is_query: bool) -> list[list[float]]:
        vectors = []
        for i in range(0, len(texts), BATCH):
            if i > 0:  # stay under 100 texts per minute
                print(f"[rate limit] embedded {i}/{len(texts)}; pausing 60s for the free-tier quota")
                time.sleep(60)
            # Each text must be its own Content, or the API returns ONE vector for the whole list.
            contents = [types.Content(parts=[types.Part(text=t)]) for t in texts[i:i + BATCH]]
            r = call(contents, is_query)
            if len(r.embeddings) != len(contents):
                raise RuntimeError(f"Asked for {len(contents)} embeddings, got {len(r.embeddings)}")
            vectors += [_normalize(e.values) for e in r.embeddings]
        return vectors

    return embed

# --------------------------------------------------------------------------
# 3. THE INDEX: chunks + vectors, saved as JSON
# --------------------------------------------------------------------------


def build_index(root: Path, embed) -> dict:
    chunks = collect_chunks(root)
    # Contextual chunk header: the path tells the embedding what kind of text this is.
    vectors = embed([f"{c['source']}\n{c['text']}" for c in chunks], is_query=False)
    for c, v in zip(chunks, vectors):
        c["vector"] = v
    return {"root": str(root), "built": datetime.now().isoformat(timespec="seconds"),
            "model": EMBED_MODEL, "chunks": chunks}


def save_index(index: dict, path: Path):
    path.write_text(json.dumps(index), encoding="utf-8")


def load_index(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def stale_files(index: dict) -> list[str]:
    """Files changed since the index was built (so the index may be out of date)."""
    built = datetime.fromisoformat(index["built"]).timestamp()
    root = Path(index["root"])
    sources = {c["source"] for c in index["chunks"]}
    return sorted(s for s in sources if (root / s).exists() and (root / s).stat().st_mtime > built)

# --------------------------------------------------------------------------
# 4. SEARCH: embed the question, rank chunks by cosine similarity
# --------------------------------------------------------------------------


def search(index: dict, query: str, embed, top_k: int = 5) -> list[dict]:
    q = embed([query], is_query=True)[0]
    # Vectors are normalized, so cosine similarity is just the dot product.
    scored = [(sum(a * b for a, b in zip(q, c["vector"])), c) for c in index["chunks"]]
    scored.sort(key=lambda sc: sc[0], reverse=True)
    return [{**c, "score": round(s, 3)} for s, c in scored[:top_k]]


def cite(chunk: dict) -> str:
    """How a chunk is cited: lines for text files, pages for PDFs."""
    if chunk.get("unit") == "page":
        return f"{chunk['source']} p.{chunk['start']}"
    return f"{chunk['source']}:{chunk['start']}-{chunk['end']}"


def format_results(results: list[dict]) -> str:
    """What the model sees: numbered passages, each with a citable source."""
    if not results:
        return "No passages found."
    parts = []
    for i, r in enumerate(results, 1):
        also = f" (identical text also in {len(r['also_in'])} other file(s))" if r.get("also_in") else ""
        parts.append(f"[{i}] {cite(r)} (similarity {r['score']}){also}\n{r['text']}")
    return "\n\n".join(parts)
