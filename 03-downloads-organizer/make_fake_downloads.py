"""
Creates a realistic, messy, FAKE Downloads folder to practice on.

    python make_fake_downloads.py                 # creates ../../sandbox/fake-downloads
    python make_fake_downloads.py C:/some/folder  # or anywhere you choose

All files are tiny and made up, so nothing private ever reaches the model.
"""

import os
import sys
import time
from pathlib import Path

DEFAULT = Path(__file__).resolve().parents[2] / "sandbox" / "fake-downloads"

# name -> content. Same content = a real duplicate.
FILES = {
    "invoice_2026_03_acme.pdf": b"%PDF fake invoice march",
    "invoice_2026_04_acme.pdf": b"%PDF fake invoice april",
    "invoice_2026_04_acme (1).pdf": b"%PDF fake invoice april",  # duplicate
    "bank_statement_sep.pdf": b"%PDF fake bank statement",
    "tax_return_2025.pdf": b"%PDF fake tax return",
    "Resume_final_v3.docx": b"PK fake resume v3",
    "Resume_final_v3 (1).docx": b"PK fake resume v3",  # duplicate
    "cover_letter.docx": b"PK fake cover letter",
    "meeting_notes.txt": b"Notes: discuss roadmap, follow up Friday.",
    "todo.txt": b"- buy milk\n- renew passport\n",
    "budget_2026.xlsx": b"PK fake spreadsheet",
    "IMG_20260912_101530.jpg": b"\xff\xd8\xff fake photo 1",
    "IMG_20260912_101544.jpg": b"\xff\xd8\xff fake photo 2",
    "IMG_20260912_101544 (1).jpg": b"\xff\xd8\xff fake photo 2",  # duplicate
    "Screenshot 2026-10-01 093012.png": b"\x89PNG fake screenshot 1",
    "Screenshot 2026-10-02 141055.png": b"\x89PNG fake screenshot 2",
    "goa_trip_beach.jpg": b"\xff\xd8\xff fake beach",
    "vscode-setup-x64-1.104.exe": b"MZ fake installer vscode",
    "python-3.13.0-amd64.exe": b"MZ fake installer python",
    "zoom_installer.msi": b"fake msi zoom",
    "project_backup.zip": b"PK fake zip backup",
    "photos_goa.zip": b"PK fake zip photos",
    "presentation_q3.pptx": b"PK fake slides",
    "song_demo.mp3": b"ID3 fake audio",
    "tutorial_video.mp4": b"fake mp4 video",
    "random_download": b"no extension, unknown content",
    "data_export.csv": b"id,name\n1,Alice\n2,Bob\n",
    "agent_paper.pdf": b"%PDF fake research paper on agents",
}


def main():
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    if target.exists() and any(target.iterdir()):
        sys.exit(f"{target} already has files. Delete it or pick another folder.")
    target.mkdir(parents=True, exist_ok=True)

    now = time.time()
    for i, (name, content) in enumerate(FILES.items()):
        p = target / name
        p.write_bytes(content)
        days_ago = (i * 7) % 120  # spread modified dates over ~4 months
        os.utime(p, (now - days_ago * 86400, now - days_ago * 86400))

    print(f"Created {len(FILES)} fake files in {target}")


if __name__ == "__main__":
    main()
