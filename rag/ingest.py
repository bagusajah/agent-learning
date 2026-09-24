"""Ingest: file -> chunks -> embeddings -> vector store. Tahap "menulis" RAG.

Pemakaian:
    from rag.ingest import ingest_path
    ingest_path("docs/handbook.pdf")

CLI-nya ada di rag/__main__.py (rag ingest <file>).
"""

from __future__ import annotations

from pathlib import Path

from rag.config import BATCH_SIZE
from rag.embeddings import embed
from rag.loaders import chunk_pages, load_pages
from rag.store import VectorStore


def ingest_path(path: str | Path, store: VectorStore | None = None) -> int:
    """Ingest satu file, return jumlah chunk tersimpan.

    Idempoten: file yang sama di-ingest ulang akan menimpa chunk lamanya
    (lihat VectorStore.upsert_chunks).
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    own_store = store is None
    store = store or VectorStore()

    pages = load_pages(p)
    chunks = chunk_pages(pages)
    if not chunks:
        print(f"  !! {p.name}: tidak ada teks terbaca (PDF scan? coba OCR)")
        return 0

    texts = [c[1] for c in chunks]
    vectors: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        vectors.extend(embed(batch))
        print(f"  embedded {min(i + len(batch), len(texts))}/{len(texts)}")

    n = store.upsert_chunks(p.name, chunks, vectors)
    if own_store:
        store.close()
    return n
