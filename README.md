# Belajar Bikin Agent Pengolah Database — Chinook

Database: **Chinook** (toko musik digital, lisensi terbuka, standar latihan industri).
11 tabel · 3.503 lagu · 59 customer · 412 invoice. Source: github.com/lerocha/chinook-database

## Struktur Folder

```
agent-learning/
├── agent.py          # agent text-to-SQL pertama Anda (~140 baris, tanpa framework)
├── README.md         # file ini — kerjakan berurutan dari atas
└── data/
    ├── Chinook.db    # database SQLite siap pakai
    └── Chinook_Sqlite.sql  # dump sumber (untuk reset: sqlite3 data/Chinook.db < data/Chinook_Sqlite.sql)
```

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

## Pertanyaan Latihan untuk Agent

- "Customer dari negara mana yang paling sering beli?"
- "10 lagu terlaris beserta artisnya"
- "Employee mana yang punya total penjualan tertinggi?"
- "Rata-rata nilai invoice per negara, urutkan dari terbesar"

## Reset Database (kalau eksperimen merusak data)

```bash
sqlite3 data/Chinook.db < data/Chinook_Sqlite.sql
```
