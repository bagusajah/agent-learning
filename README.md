# Belajar Bikin Agent Pengolah Database — Chinook

Database: **Chinook** (toko musik digital, lisensi terbuka, standar latihan industri).
11 tabel · 3.503 lagu · 59 customer · 412 invoice. Source: github.com/lerocha/chinook-database

## Struktur Folder

```
agent-learning/
├── agent.py          # agent single: 3 tool + 1 loop (~140 baris) — mulai di sini
├── agent_multi.py    # multi-agent: 3 spesialis + orkestrator + retry
├── rag/              # PAKET RAG: dokumen -> sqlite-vec -> jawaban (lihat bawah)
├── README.md         # file ini — kerjakan berurutan dari atas
└── data/
    ├── Chinook.db    # database SQLite siap pakai
    ├── Chinook_Sqlite.sql  # dump sumber (untuk reset: sqlite3 data/Chinook.db < data/Chinook_Sqlite.sql)
    └── vectorstore/  # (di-git-ignore) chunks.db hasil `rag ingest`
```

---

# Paket RAG: Dokumen → Vector Store → Retrieval (100% lokal)

Tahap ketiga learning path: setelah agent bisa MEMBACA database, sekarang dia
belajar MENGINGAT dokumen. Vektor disimpan di **sqlite-vec** (ekstensi SQLite —
satu file .db, tanpa server), embedding via **LM Studio** (`text-embedding-bge-m3`,
multilingual, 1024 dim), jawaban via model chat lokal.

```
ingest : PDF/.txt/.md -> chunking (800 char, overlap 120) -> bge-m3 -> chunks.db
search : pertanyaan -> bge-m3 -> KNN cosine (dihitung sqlite-vec, bukan Python)
ask    : search + prompt bersitasi -> model chat LM Studio -> jawaban [1][2]
```

## Setup (sekali)

1. LM Studio → tab **Developer** → **Start Server** (port 1234) dengan
   `text-embedding-bge-m3` + satu model chat sudah di-load.
2. Python: framework python.org di macOS tidak bisa load ekstensi SQLite,
   jadi pakai Python Homebrew untuk venv:

```bash
/opt/homebrew/bin/python3.13 -m venv .venv
.venv/bin/pip install -r rag/requirements.txt
```

## Pakai

```bash
cd ~/agent-learning
.venv/bin/python -m rag ingest data/notes-example.md       # satu file
.venv/bin/python -m rag ingest docs/                        # satu folder pdf/txt/md
.venv/bin/python -m rag list
.venv/bin/python -m rag search "berapa lama cuti melahirkan?" -k 3
.venv/bin/python -m rag ask    "ringkas isi dokumen ini"
.venv/bin/python -m rag delete data/notes-example.md
```

Peta file (baca berurutan, masing-masing < 200 baris):

```
rag/
├── config.py      # semua konstanta: URL LM Studio, ukuran chunk, path db
├── loaders.py     # baca PDF/teks -> potongan chunk
├── embeddings.py  # teks -> vektor via POST /v1/embeddings
├── store.py       # VectorStore: tabel chunks + vtable vec0, KNN SQL
├── ingest.py      # pipeline menulis: loader -> embed -> store
├── retrieve.py    # pipeline baca: search() dan ask() (RAG penuh)
└── __main__.py    # CLI: ingest / list / search / ask / delete
```

## Kurikulum Mandiri (RAG)

1. **Lihat store-nya langsung** — `sqlite3 data/vectorstore/chunks.db
   "SELECT document, chunk_index, substr(content,1,60) FROM chunks LIMIT 5"`.
   Vector store hanyalah tabel SQLite biasa + virtual table vec0.
2. **Rasakan retrieval tanpa LLM** — bandingkan `rag search` vs `rag ask`
   untuk pertanyaan yang sama. Kesimpulan: LLM tidak "tahu" apa pun,
   ia hanya merangkai potongan yang ditemukan retrieval.
3. **Eksperimen ukuran chunk** — ubah `CHUNK_SIZE`/`CHUNK_OVERLAP` di
   `config.py`, ingest ulang, bandingkan kualitas `search`. Terlalu kecil =
   konteks terpotong; terlalu besar = tidak fokus.
4. **Eksperimen k** — tanya hal yang butuh fakta dari 2 halaman berbeda
   dengan `-k 1` vs `-k 6`. Ini trade-off presisi vs cakupan.
5. **Tes kegagalan (hallucination guard)** — tanya hal yang TIDAK ada di
   dokumen. Prompt sudah memerintahkan "katakan tidak tahu" — apakah
   model patuh? Kalau tidak, perkuat prompt di `retrieve.py`.
6. **Filter per dokumen** — tambah `WHERE c.document = ?` pada query KNN
   di `store.py` (vec0 mendukung kolom metadata & partisi — eksperimen!).
7. **Hybrid search** — gabungkan KNN dengan `MATCH` full-text search FTS5
   (juga bawaan SQLite). BM25 + vektor = teknik yang dipakai produk riil.
8. **Ganti backend embedding** — endpoint sudah OpenAI-compatible; coba
   `LMSTUDIO_BASE_URL` ke provider lain, atau tambahkan `fastembed` (lokal,
   onnx) sebagai backend kedua di `embeddings.py`.

## Hubungan dengan Modul Sebelumnya

| Modul | Yang dipelajari | Analogi |
|---|---|---|
| `agent.py` | LLM + tools + loop | agent yang BERTANYA ke database |
| `agent_multi.py` | handoff JSON, least privilege, validator | agent yang BERBAGI KERJA |
| `rag/` | embedding, vector store, retrieval | agent yang MENGINGAT dokumen |

Langkah alami berikutnya: gabungkan — beri agent.py tool tambahan
`search_docs(query)` yang memanggil `rag.retrieve.search` → agent yang bisa
bertanya ke database DAN mengingat dokumen.

---

# Modul Text-to-SQL (agent.py & agent_multi.py)

## Setup (sekali)

```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...
cd ~/agent-learning
```

## Jalankan Agent Pertama

```bash
python3 agent.py "Siapa 5 customer dengan total belanja terbesar?"
python3 agent.py "Genre musik apa yang paling banyak terjual?"
python3 agent.py "Bandingkan penjualan tahun 2025 vs 2026 per bulan"
```

Lihat prosesnya: agent membaca daftar tabel → membuka schema → menulis SQL →
dapat error → memperbaiki sendiri → menjawab. Itulah seluruh esensi "agent".

## Kurikulum Mandiri (kerjakan berurutan)

1. **Pahami alurnya** — baca `agent.py` dari atas ke bawah. Cuma 3 tool:
   `list_tables`, `get_schema`, `run_query`. Cuma 1 loop.
2. **Latihan error-recovery** — tanya sesuatu yang butuh tabel yang salah namanya.
   Perhatikan agent menerima `SQL ERROR` lalu mencoba lagi. Itu agentic behavior.
3. **Tambah tool sendiri** — tambahkan `top_customers(n)` yang menjalankan query
   jadi dan mengembalikan hasil terformat. Rasakan bedanya tool spesifik vs generic.
4. **Tambahkan pagr keamanan** — larang query yang mengandung `DROP`, `DELETE`,
   `UPDATE` (regex sederhana di `run_query` cukup).
5. **Hemat token** — cukup 3.503 baris? Agent sekarang mengambil `fetchmany(50)`.
   Eksperimen: bagaimana kalau tabel jutaan baris? (petunjuk: tool `count_first`.)
6. **Naik level: ganti ke framework** — port agent ini ke `pydantic-ai` atau
   `smolagents`. Anda akan tahu persis apa yang framework lakukan di balik layar.
7. **Multi-agent** — jalankan `python3 agent_multi.py "Genre apa yang paling
   banyak terjual per negara?"` lalu bandingkan dengan `agent.py`. Pelajari tiga
   pola barunya: (a) handoff terstruktur via JSON antar agen, (b) least privilege
   — tiap agen hanya punya tool yang ia butuhkan, (c) validator yang boleh
   menolak karya penulis dan memicu retry beranggaran (maks 2x).

## Arsitektur Multi-Agent (agent_multi.py)

```
pertanyaan -> SCHEMA ANALYST (list_tables, get_schema)
                  | handoff JSON {tables, notes}
                  v
              SQL WRITER (run_query) <---- feedback (retry maks 2x)
                  | SQL + hasil               |
                  v                           |
              DATA VALIDATOR (tanpa tool) ----+
                  | verdict OK
                  v
              jawaban final ke user
```

Tugas latihan multi-agent:
- Tambah agen ke-4: `SECURITY GUARD` yang memeriksa SQL sebelum dieksekusi
- Orkestrator saat ini selalu eksekusi ulang SQL — pertimbangkan: bagaimana
  kalau query mahal (jutaan baris)? Tambahkan hasil cache di orkestrator
- Bandingkan token terpakai `agent.py` vs `agent_multi.py` — kapan multi-agent
  TIDAK worth it? (jawabannya ada di pertanyaan sederhana)

## Pertanyaan Latihan untuk Agent

- "Customer dari negara mana yang paling sering beli?"
- "10 lagu terlaris beserta artisnya"
- "Employee mana yang punya total penjualan tertinggi?"
- "Rata-rata nilai invoice per negara, urutkan dari terbesar"

## Reset Database (kalau eksperimen merusak data)

```bash
sqlite3 data/Chinook.db < data/Chinook_Sqlite.sql
```
