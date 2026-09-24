"""Loaders: baca file -> teks polos -> potongan (chunks).

Sengaja hanya 2 format: PDF (pypdf) dan teks/markdown. Cukup untuk belajar;
menambah format baru = tambah satu fungsi + satu entry di _EXTENSIONS.
"""

from __future__ import annotations

from pathlib import Path

from rag.config import CHUNK_OVERLAP, CHUNK_SIZE


def load_pages(path: str | Path) -> list[tuple[int | None, str]]:
    """Baca file, return [(nomor_halaman_atau_None, teks), ...]."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        return _load_pdf(p)
    if suffix in {".txt", ".md"}:
        return [(None, p.read_text(encoding="utf-8", errors="replace"))]
    raise ValueError(f"Format {suffix} belum didukung (coba .pdf, .txt, .md)")


def _load_pdf(p: Path) -> list[tuple[int | None, str]]:
    from pypdf import PdfReader

    reader = PdfReader(str(p))
    return [(i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages)]


def chunk_pages(
    pages: list[tuple[int | None, str]],
    size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[tuple[int | None, str]]:
    """Potong tiap halaman jadi potongan ~size karakter, tumpang tindih `overlap`.

    Kenapa overlap? Kalau jawaban persis di batas potongan, tanpa overlap
    konteksnya terbelah dua dan retrieval jadi Lemah.
    """
    out: list[tuple[int | None, str]] = []
    for page_no, text in pages:
        text = " ".join(text.split())  # rapikan whitespace & line break PDF
        if not text:
            continue
        start = 0
        while start < len(text):
            piece = text[start : start + size]
            out.append((page_no, piece))
            if start + size >= len(text):
                break
            start += size - overlap
    return out
