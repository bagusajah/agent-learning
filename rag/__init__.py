"""Paket RAG lokal: dokumen -> vector store (sqlite-vec) -> retrieval.

Alur lengkap (baca berurutan, mirip agent.py):

    ingest : loaders -> chunking -> embeddings (LM Studio / bge-m3) -> store
    search : embeddings(query) -> store.knn -> potongan paling relevan
    ask    : search + LLM lokal -> jawaban dengan sitasi [1][2]

Semua jalan di laptop: tidak ada API key, tidak ada cloud.
Jalankan: .venv/bin/python -m rag --help
"""

from rag.config import RAG_DB, LMSTUDIO_BASE_URL, LMSTUDIO_EMBED_MODEL
from rag.store import VectorStore

__all__ = ["RAG_DB", "LMSTUDIO_BASE_URL", "LMSTUDIO_EMBED_MODEL", "VectorStore"]
