"""Retrieval + generation: pertanyaan -> KNN -> LLM lokal -> jawaban bersitasi.

Retrieval (cari potongan) dan generation (menjawab) dipisah tegas:
- search() berguna sendiri — ini bagian "R" dari RAG
- ask() = search + prompt + LLM — ini bagian lengkapnya

Latihan: matikan bagian generation, bandingkan apa yang retrieval temukan
vs apa yang LLM jawab. Kebanyakan jawaban RAG yang "salah" sebenarnya
retrieval yang tidak menemukan potongan yang tepat.
"""

from __future__ import annotations

import json
import urllib.request

from rag.config import DEFAULT_K, LMSTUDIO_BASE_URL, LMSTUDIO_CHAT_MODEL
from rag.embeddings import EmbeddingError, embed, first_chat_model
from rag.store import Hit, VectorStore


def search(query: str, k: int = DEFAULT_K, store: VectorStore | None = None) -> list[Hit]:
    """R dari RAG: vektor-kan pertanyaan, ambil k potongan terdekat."""
    own = store is None
    store = store or VectorStore()
    try:
        qvec = embed([query])[0]
        return store.knn(qvec, k=k)
    finally:
        if own:
            store.close()


_PROMPT = """Jawab pertanyaan user HANYA berdasarkan konteks berikut.
Kutip sumber dengan format [1], [2] sesuai nomor konteks.
Kalau konteks tidak memuat jawabannya, katakan tidak tahu — jangan mengarang.

Konteks:
{context}

Pertanyaan: {question}
"""


def _build_context(hits: list[Hit]) -> str:
    """Potongan bernomor [1..n] — nomor inilah sitasi di jawaban."""
    return "\n\n".join(
        f"[{i}] ({h.cite})\n{h.content}" for i, h in enumerate(hits, 1)
    )


def _chat(prompt: str, model: str) -> str:
    req = urllib.request.Request(
        f"{LMSTUDIO_BASE_URL}/chat/completions",
        data=json.dumps(
            {"model": model, "messages": [{"role": "user", "content": prompt}],
             "temperature": 0.2}
        ).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.load(resp)["choices"][0]["message"]["content"]


def ask(question: str, k: int = DEFAULT_K, store: VectorStore | None = None) -> str:
    """RAG lengkap: retrieval -> prompt -> LLM lokal -> jawaban + sitasi."""
    hits = search(question, k=k, store=store)
    if not hits:
        return "(vector store kosong — jalankan `rag ingest` dulu)"
    model = LMSTUDIO_CHAT_MODEL or first_chat_model()
    prompt = _PROMPT.format(context=_build_context(hits), question=question)
    try:
        return _chat(prompt, model)
    except EmbeddingError:
        raise
    except Exception as e:
        return (
            f"[retrieval OK — {len(hits)} potongan ditemukan, tapi LLM gagal: {e}]\n"
            "Coba `rag search` untuk melihat potongan yang ditemukan."
        )
