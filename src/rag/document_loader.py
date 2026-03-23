"""
Document loader for the RTV Agriculture Handbook.

Supports both DOCX and PDF formats with section-aware chunking.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Known handbook filenames
HANDBOOK_PATTERNS = [
    "Copy of RTV_IMP_Handbook*.pdf",
    "RTV_IMP_Handbook*.pdf",
    "*.docx",
]


def find_handbook() -> Path | None:
    """Locate the Agriculture Handbook file in the project root."""
    for pattern in HANDBOOK_PATTERNS:
        matches = list(PROJECT_ROOT.glob(pattern))
        if matches:
            return matches[0]
    return None


def load_pdf(path: Path) -> list[dict]:
    """Load a PDF file and return list of {text, metadata} dicts."""
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ImportError("pypdf is required: pip install pypdf")

    reader = PdfReader(str(path))
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            pages.append({
                "text": text,
                "metadata": {
                    "source": path.name,
                    "page": i + 1,
                    "total_pages": len(reader.pages),
                },
            })

    logger.info("Loaded %d pages from %s", len(pages), path.name)
    return pages


def load_docx(path: Path) -> list[dict]:
    """Load a DOCX file and return list of {text, metadata} dicts."""
    try:
        from docx import Document
    except ImportError:
        raise ImportError("python-docx is required: pip install python-docx")

    doc = Document(str(path))
    sections: list[dict] = []
    current_section = ""
    current_text: list[str] = []

    for para in doc.paragraphs:
        # Detect section headers (Heading styles or ALL CAPS)
        is_heading = (
            para.style.name.startswith("Heading")
            or (para.text.isupper() and len(para.text) > 5)
        )

        if is_heading and current_text:
            sections.append({
                "text": "\n".join(current_text),
                "metadata": {
                    "source": path.name,
                    "section": current_section or "Introduction",
                },
            })
            current_text = []
            current_section = para.text.strip()
        else:
            if para.text.strip():
                current_text.append(para.text.strip())

    # Don't forget the last section
    if current_text:
        sections.append({
            "text": "\n".join(current_text),
            "metadata": {
                "source": path.name,
                "section": current_section or "Final Section",
            },
        })

    logger.info("Loaded %d sections from %s", len(sections), path.name)
    return sections


def load_handbook(path: Path | None = None) -> list[dict]:
    """Load the handbook from the given path (auto-detects format)."""
    if path is None:
        path = find_handbook()
    if path is None:
        raise FileNotFoundError(
            "Agriculture Handbook not found. Place it in the project root."
        )

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return load_pdf(path)
    elif suffix == ".docx":
        return load_docx(path)
    else:
        raise ValueError(f"Unsupported file format: {suffix}")


def chunk_documents(
    documents: list[dict],
    chunk_size: int = 900,
    chunk_overlap: int = 180,
) -> list[dict]:
    """Split documents into chunks with section-aware metadata.

    Uses RecursiveCharacterTextSplitter with custom separators
    optimized for agricultural handbook content.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=[
            "\n\n\n",    # Major section breaks
            "\n\n",       # Paragraph breaks
            "\n",         # Line breaks
            ". ",         # Sentence boundaries
            ", ",         # Clause boundaries
            " ",          # Word boundaries
        ],
        length_function=len,
    )

    chunks: list[dict] = []
    for doc in documents:
        text = doc["text"]
        metadata = doc["metadata"]

        splits = splitter.split_text(text)
        for i, chunk_text in enumerate(splits):
            chunk_text = chunk_text.strip()
            if not chunk_text or len(chunk_text) < 50:
                continue

            chunks.append({
                "text": chunk_text,
                "metadata": {
                    **metadata,
                    "chunk_index": i,
                    "chunk_total": len(splits),
                    "char_count": len(chunk_text),
                },
            })

    logger.info(
        "Created %d chunks from %d documents (size=%d, overlap=%d)",
        len(chunks), len(documents), chunk_size, chunk_overlap,
    )
    return chunks
