"""
Structured answers: the schema the model must follow, and code that checks
the model's citations against the actual files instead of trusting them.
"""

import json
import re
from pathlib import Path

import rag

# The shape every final answer must have. The API enforces it (response_format).
ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "found_in_notes": {
            "type": "boolean",
            "description": "true if the answer comes from the user's notes; false if from general knowledge or unknown",
        },
        "answer": {"type": "string", "description": "The answer for the user, in plain prose"},
        "citations": {
            "type": "array",
            "description": "One entry per source used. Empty when found_in_notes is false.",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Exactly as shown by search_notes, e.g. 'notes.md:12-30' or 'paper.pdf p.3'"},
                    "quote": {"type": "string", "description": "A short passage copied WORD FOR WORD from that source"},
                },
                "required": ["source", "quote"],
            },
        },
    },
    "required": ["found_in_notes", "answer", "citations"],
}


def parse_answer(text: str) -> dict | None:
    """The API guarantees the shape, but we still check: never assume."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    ok = (isinstance(data, dict) and isinstance(data.get("found_in_notes"), bool)
          and isinstance(data.get("answer"), str) and isinstance(data.get("citations"), list))
    return data if ok else None

# --------------------------------------------------------------------------
# Citation checking
# --------------------------------------------------------------------------

SOURCE = re.compile(r"^(?P<path>.+?)(?:\s+p\.(?P<page>\d+)|:(?P<start>\d+)-(?P<end>\d+))?$")
LINE_SLACK = 3  # allow the quote to sit a few lines outside the cited range


def _norm(s: str) -> str:
    """Compare text, not formatting: case, quotes, markdown symbols and whitespace don't count."""
    s = s.lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"[*`_#>]", "", s)
    return " ".join(s.split())


def source_text(source: str, root: Path) -> tuple[str | None, str]:
    """Read the part of the real file that a citation points at."""
    m = SOURCE.match(source.strip().strip("[]").strip())
    if not m:
        return None, "can't parse the source"
    path = (root / m["path"]).resolve()
    if root.resolve() not in path.parents or not path.is_file():
        return None, f"no such file: {m['path']}"
    if path.suffix.lower() == ".pdf":
        pages = rag.read_pdf_pages(path)
        if m["page"]:
            n = int(m["page"])
            if not 1 <= n <= len(pages):
                return None, f"the PDF has no page {n}"
            return pages[n - 1], ""
        return "\n".join(pages), ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if m["start"]:
        start, end = int(m["start"]), int(m["end"])
        return "\n".join(lines[max(start - 1 - LINE_SLACK, 0):end + LINE_SLACK]), ""
    return "\n".join(lines), ""


def check_citation(citation: dict, root: Path) -> tuple[bool, str]:
    """Is the quote really in the cited place? Returns (ok, reason)."""
    quote = citation.get("quote", "")
    pieces = [p for p in re.split(r"\.\.\.|…", quote) if p.strip()]  # allow "..." between parts
    if not pieces or any(len(_norm(p)) < 8 for p in pieces):
        return False, "quote too short to verify"
    text, reason = source_text(citation.get("source", ""), root)
    if text is None:
        return False, reason
    haystack = _norm(text)
    missing = [p for p in pieces if _norm(p) not in haystack]
    return (False, "quote not found at that location") if missing else (True, "")


def check_answer(answer: dict, root: Path) -> list[tuple[dict, bool, str]]:
    return [(c, *check_citation(c, root)) for c in answer.get("citations", [])]


def failure_feedback(checks) -> str:
    """What we tell the model when citations fail, so it can fix them."""
    bad = [f"- {c.get('source')}: {why}" for c, ok, why in checks if not ok]
    return ("Your citations were checked against the actual files and these failed:\n" + "\n".join(bad) +
            "\nFix them: copy the quote word for word from a passage that search_notes returned, use its source "
            "exactly as shown, or remove the citation. Reply with the corrected JSON answer.")


def render(answer: dict, checks) -> str:
    """Show the answer with honest verification marks."""
    origin = "from your notes" if answer["found_in_notes"] else "NOT from your notes (general knowledge or unknown)"
    out = [answer["answer"], "", f"  [{origin}]"]
    if checks:
        ok_count = sum(ok for _, ok, _ in checks)
        out.append(f"  citations: {ok_count}/{len(checks)} verified")
        for c, ok, why in checks:
            mark = "✓" if ok else f"✗ {why}"
            out.append(f"    {mark}  {c.get('source')}  \"{c.get('quote', '')[:80]}\"")
    return "\n".join(out)
