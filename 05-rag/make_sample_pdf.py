"""
Write simple text PDFs with no extra libraries (the PDF format is just
structured text). Used by the tests, and to create a sample PDF to index:

    python make_sample_pdf.py      # creates ../library/agent-glossary.pdf

The glossary covers terms that are NOT in the lab notes, so if the agent
answers them with a page citation, the answer can only come from the PDF.
"""

from pathlib import Path


def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(path: Path, pages: list[str]) -> None:
    """One text page per string; '\\n' starts a new line."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>"]
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(len(pages)))
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>")
    objs.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for i, text in enumerate(pages):
        lines = " ".join(f"({_escape(l)}) Tj T*" for l in text.split("\n")) if text else ""
        body = f"BT /F1 11 Tf 15 TL 60 740 Td {lines} ET"
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                    f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * i} 0 R >>")
        objs.append(f"<< /Length {len(body)} >>\nstream\n{body}\nendstream")

    out, offsets = "%PDF-1.4\n", []
    for n, obj in enumerate(objs, 1):
        offsets.append(len(out.encode("latin-1")))
        out += f"{n} 0 obj\n{obj}\nendobj\n"
    xref = len(out.encode("latin-1"))
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(out.encode("latin-1"))


GLOSSARY = [
    "Agent Glossary (sample PDF for the RAG stage)\n\n"
    "This short document defines agent terms that are not covered\n"
    "in the lab notes. Page 2 covers reasoning patterns.\n"
    "Page 3 covers risks.",

    "Reasoning patterns\n\n"
    "ReAct (Reason + Act): a prompting pattern from a 2022 paper by Yao et al.\n"
    "The model alternates between writing a short reasoning step (Thought),\n"
    "taking an action such as a tool call (Action), and reading the result\n"
    "(Observation), repeating until it can answer. Most tool-calling agent\n"
    "loops are a descendant of this idea.\n\n"
    "Plan-and-execute: the model first writes a full plan, then carries out\n"
    "the steps, revising the plan only when a step fails.",

    "Risks\n\n"
    "Context rot: answer quality tends to drop as the context grows very long,\n"
    "even when it is far below the model's limit. Relevant details get lost\n"
    "among irrelevant ones, which is one reason to compact or retrieve.\n\n"
    "Tool poisoning: hidden instructions placed in a tool's description or\n"
    "output (for example by a malicious MCP server) that try to make the\n"
    "agent do something the user never asked for.",
]


if __name__ == "__main__":
    target = Path(__file__).resolve().parents[1] / "library" / "agent-glossary.pdf"
    make_pdf(target, GLOSSARY)
    print(f"Created {target} ({len(GLOSSARY)} pages)")
