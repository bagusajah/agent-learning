"""Vector store di atas sqlite-vec (ekstensi SQLite, KNN in-DB, tanpa server).

Satu file .db menyimpan SEMUA: metadata chunk (tabel biasa) + vektor (virtual
table vec0). vec0 menyediakan `WHERE emb MATCH ? AND k = N` untuk KNN cosine
— database yang menghitung jarak, bukan Python.

Query yang dipakai (dipisah jadi fungsi kecil biar gampang di-experimen):

    INSERT INTO chunks(document, page, chunk_index, content) VALUES (...)
    SELECT c.id, c.document, ..., v.distance
    FROM chunks c JOIN chunks_vec v ON v.id = c.id
    WHERE v.emb MATCH :query_vec AND k = :k
    ORDER BY v.distance
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import sqlite_vec

from rag.config import RAG_DB

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    id          INTEGER PRIMARY KEY,
    document    TEXT NOT NULL,          -- nama file sumber
    page        INTEGER,                -- halaman PDF (NULL utk .txt/.md)
    chunk_index INTEGER NOT NULL,       -- potongan ke-n dalam dokumen
    content     TEXT NOT NULL,
    UNIQUE(document, chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(document);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0(
    id   INTEGER PRIMARY KEY,          -- FK ke chunks.id
    emb  float[1024] distance_metric=cosine
);
"""


@dataclass
class Hit:
    """Satu hasil retrieval — potongan teks + skor kemiripan."""

    id: int
    document: str
    page: int | None
    chunk_index: int
    content: str
    distance: float  # cosine distance: 0 = identik, makin kecil makin mirip

    @property
    def cite(self) -> str:
        page = f" hlm.{self.page}" if self.page is not None else ""
        return f"{self.document}{page} #ch{self.chunk_index}"

    @property
    def similarity(self) -> float:
        return 1.0 - self.distance


def connect(db_path: str = RAG_DB) -> sqlite3.Connection:
    """Buka SQLite + load ekstensi vec0. Import/eksperimen bebas pakai ini."""
    con = sqlite3.connect(db_path)
    con.enable_load_extension(True)   # butuh Python Homebrew/Linux; framework
    sqlite_vec.load(con)              # python.org macOS tidak expose API ini
    con.enable_load_extension(False)
    con.executescript(_SCHEMA)
    return con


class VectorStore:
    """Fasad tipis: upsert chunk+vektor, cari KNN, kelola dokumen."""

    def __init__(self, db_path: str = RAG_DB) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.con = connect(db_path)

    # -- tulis ---------------------------------------------------------------

    def upsert_chunks(
        self, document: str, chunks: list[tuple[int | None, str]],
        vectors: list[list[float]],
    ) -> int:
        """Simpan potongan (halaman, teks) + vektornya (transaksi, idempoten).

        Prinsip: document+chunk_index unik — ingest ulang dokumen yang sama
        menimpa potongan lama, tidak menduplikasi.
        """
        if len(chunks) != len(vectors):
            raise ValueError(f"chunks={len(chunks)} != vectors={len(vectors)}")
        with self.con:  # transaksi otomatis: commit / rollback
            self.con.execute("DELETE FROM chunks WHERE document = ?", (document,))
            for i, ((page, text), vec) in enumerate(zip(chunks, vectors)):
                cur = self.con.execute(
                    "INSERT INTO chunks(document, page, chunk_index, content)"
                    " VALUES (?, ?, ?, ?)",
                    (document, page, i, text),
                )
                self.con.execute(
                    "INSERT INTO chunks_vec(id, emb) VALUES (?, ?)",
                    (cur.lastrowid, _serialize(vec)),
                )
        return len(chunks)

    # -- baca ----------------------------------------------------------------

    def knn(self, query_vec: list[float], k: int = 4) -> list[Hit]:
        """K potongan terdekat — jarak dihitung oleh sqlite-vec, bukan Python."""
        rows = self.con.execute(
            """
            SELECT c.id, c.document, c.page, c.chunk_index, c.content, v.distance
            FROM chunks_vec v
            JOIN chunks c ON c.id = v.id
            WHERE v.emb MATCH :qv AND k = :k
            ORDER BY v.distance
            """,
            {"qv": _serialize(query_vec), "k": k},
        ).fetchall()
        return [Hit(*r) for r in rows]

    def count(self) -> int:
        return self.con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

    def documents(self) -> list[tuple[str, int]]:
        """(nama dokumen, jumlah chunk) — untuk list & filter."""
        return self.con.execute(
            "SELECT document, COUNT(*) FROM chunks GROUP BY document ORDER BY document"
        ).fetchall()

    def delete_document(self, document: str) -> int:
        """Hapus satu dokumen (metadata + vektor). Return jumlah chunk terhapus."""
        with self.con:
            ids = [r[0] for r in self.con.execute(
                "SELECT id FROM chunks WHERE document = ?", (document,)
            )]
            # Tidak ada cascade otomatis antar tabel — hapus vektor dulu,
            # lalu metadata. Urutan ini juga berlaku kalau kamu pakai FK.
            for cid in ids:
                self.con.execute("DELETE FROM chunks_vec WHERE id = ?", (cid,))
            self.con.execute("DELETE FROM chunks WHERE document = ?", (document,))
        return len(ids)

    def close(self) -> None:
        self.con.close()


def _serialize(vec: list[float]) -> bytes:
    """float32 little-endian — format yang diminta kolom vec0."""
    import struct

    return struct.pack(f"<{len(vec)}f", *vec)
