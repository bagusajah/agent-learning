"""Konfigurasi terpusat paket RAG. Semua bisa dioverride lewat environment variable.

Kenapa file terpisah? Supaya konstanta "ajaib" tidak tersebar di banyak file —
kalau ganti model embedding, cukup ubah di sini (atau set env var).
"""

import os

# --- LM Studio (server OpenAI-compatible di localhost) ---------------------
# Jalankan LM Studio -> tab Developer -> Start Server (port default 1234).
LMSTUDIO_BASE_URL = os.environ.get(
    "LMSTUDIO_BASE_URL", "http://localhost:1234/v1"
)
# Nama model persis seperti di `curl localhost:1234/v1/models`.
LMSTUDIO_EMBED_MODEL = os.environ.get("LMSTUDIO_EMBED_MODEL", "text-embedding-bge-m3")
# Model chat untuk `rag ask`. Kosong = auto-pilih model non-embedding pertama.
LMSTUDIO_CHAT_MODEL = os.environ.get("LMSTUDIO_CHAT_MODEL", "")

# --- Vector store ----------------------------------------------------------
# Satu file SQLite biasa — bisa dibuka sqlite3 CLI, dicopy, di-backup.
RAG_DB = os.environ.get("RAG_DB", "data/vectorstore/chunks.db")

# --- Chunking --------------------------------------------------------------
CHUNK_SIZE = 800    # target panjang potongan (karakter)
CHUNK_OVERLAP = 120  # tumpang tindih antar potongan agar konteks tidak terpotong
BATCH_SIZE = 16      # berapa potongan dikirim per request embedding (hemat waktu)

# --- Retrieval -------------------------------------------------------------
DEFAULT_K = 4  # jumlah potongan yang diambil untuk satu pertanyaan
