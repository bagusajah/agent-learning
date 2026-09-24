"""Embeddings via LM Studio (endpoint /v1/embeddings, kompatibel OpenAI).

Konsep kunci: embedding = teks -> vektor float (di sini 1024 dim dari bge-m3).
Dua teks yang maknanya mirip akan punya vektor yang "berdekatan" — itu
dasar pencarian semantik (bukan pencarian keyword).

Kenapa tidak pakai SDK openai? Kode requests biasa membuatnya jelas apa yang
sebenarnya dikirim lewat kabel: satu POST JSON per batch.
"""

import json
import urllib.request

from rag.config import LMSTUDIO_BASE_URL, LMSTUDIO_EMBED_MODEL


class EmbeddingError(RuntimeError):
    """Dilempar kalau LM Studio mati / model salah / respons aneh."""


def embed(texts: list[str]) -> list[list[float]]:
    """Kirim batch teks, terima batch vektor (urutan sama dengan input).

    Raises:
        EmbeddingError: server tidak merespons atau menolak request.
    """
    if not texts:
        return []
    req = urllib.request.Request(
        f"{LMSTUDIO_BASE_URL}/embeddings",
        data=json.dumps({"model": LMSTUDIO_EMBED_MODEL, "input": texts}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.load(resp)
    except Exception as e:  # koneksi ditolak = LM Studio server belum jalan
        raise EmbeddingError(
            f"Gagal memanggil {LMSTUDIO_BASE_URL}/embeddings ({e}). "
            "Pastikan LM Studio server sudah Start (tab Developer)."
        ) from e

    # API mengembalikan data[i].embedding; sort by index agar urutan aman.
    items = sorted(payload.get("data", []), key=lambda d: d.get("index", 0))
    if len(items) != len(texts):
        raise EmbeddingError(
            f"Jumlah embedding tidak cocok: kirim {len(texts)}, dapat {len(items)}"
        )
    return [item["embedding"] for item in items]


def first_chat_model() -> str:
    """Auto-pilih model chat (id yang TIDAK mengandung 'embedding')."""
    with urllib.request.urlopen(f"{LMSTUDIO_BASE_URL}/models", timeout=30) as resp:
        data = json.load(resp)["data"]
    for m in data:
        if "embedding" not in m["id"].lower():
            return m["id"]
    raise EmbeddingError("Tidak ada model chat di LM Studio — load satu model dulu.")
