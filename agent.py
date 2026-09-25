#!/usr/bin/env python3
"""
Agent mini: text-to-SQL untuk database Chinook.

Ini agent PERTAMA untuk belajar. Strukturnya sengaja sederhana agar bisa
dibaca dari atas ke bawah:

    LLM + Tools + Loop
    (pikir -> panggil tool -> lihat hasil -> ulangi -> jawab final)

Jalankan:
    pip install anthropic
    export ANTHROPIC_API_KEY=sk-...
    python3 agent.py "Siapa 5 customer dengan total belanja terbesar?"
"""

import json
import sqlite3
import sys

from anthropic import Anthropic

DB_PATH = "data/Chinook.db"
MODEL = "qwen/qwen3.5-9b"
BASE_URL = "http://localhost:1234"  # URL Anthropic API (opsional, default: cloud)
API_KEY = "none"  # ganti dengan API key

client = Anthropic(base_url=BASE_URL, api_key=API_KEY)  # membaca ANTHROPIC_API_KEY dari environment


# ---------------------------------------------------------------
# 1) TOOLS: fungsi Python biasa yang boleh dipakai agent
# ---------------------------------------------------------------

def list_tables() -> str:
    """Tool 1: lihat daftar tabel yang tersedia."""
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    con.close()
    return ", ".join(r[0] for r in rows)


def get_schema(table: str) -> str:
    """Tool 2: lihat struktur satu tabel (nama kolom & tipe)."""
    con = sqlite3.connect(DB_PATH)
    row = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    con.close()
    return row[0] if row else f"Tabel '{table}' tidak ditemukan."


def run_query(sql: str) -> str:
    """Tool 3: jalankan query SELECT. Hanya SELECT — ini pagar keamanan."""
    if not sql.strip().upper().startswith("SELECT"):
        return "DITOLAK: hanya query SELECT yang diizinkan."
    con = sqlite3.connect(DB_PATH)
    try:
        cur = con.execute(sql)
        rows = cur.fetchmany(50)  # batasi hasil agar hemat token
        cols = [d[0] for d in cur.description] if cur.description else []
        if not rows:
            return "(hasil kosong)"
        table = " | ".join(cols) + "\n" + "\n".join(
            " | ".join(str(v) for v in r) for r in rows
        )
        return table
    except Exception as e:  # error query dikembalikan ke LLM supaya dia bisa
        return f"SQL ERROR: {e}"  # memperbaiki sendiri — ini inti pembelajarannya
    finally:
        con.close()


TOOLS = {
    "list_tables": (lambda: list_tables(), "Lihat daftar tabel di database"),
    "get_schema": (lambda table: get_schema(table), "Lihat struktur/kolom sebuah tabel"),
    "run_query": (lambda sql: run_query(sql), "Jalankan query SQL SELECT dan kembalikan hasilnya"),
}

# Skema tool dalam format API (yang dikirim ke LLM)
TOOL_SPECS = [
    {
        "name": "list_tables",
        "description": "Lihat daftar tabel di database",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_schema",
        "description": "Lihat struktur/kolom sebuah tabel",
        "input_schema": {
            "type": "object",
            "properties": {"table": {"type": "string"}},
            "required": ["table"],
        },
    },
    {
        "name": "run_query",
        "description": "Jalankan query SQL SELECT dan kembalikan hasilnya",
        "input_schema": {
            "type": "object",
            "properties": {"sql": {"type": "string"}},
            "required": ["sql"],
        },
    },
]


# ---------------------------------------------------------------
# 2) LOOP: pikir -> aksi -> observasi -> ulangi -> jawab final
# ---------------------------------------------------------------

def ask(question: str, max_turns: int = 15) -> None:
    messages = [{"role": "user", "content": question}]
    seen_queries = set()
    for turn in range(1, max_turns + 1):
        resp = client.messages.create(
            model=MODEL, max_tokens=4096, tools=TOOL_SPECS, messages=messages
        )
        # tampilkan apa yang agent "pikirkan" (teks) — biar belajar dari prosesnya
        for block in resp.content:
            if block.type == "text" and block.text.strip():
                print(f"\n[agent, putaran {turn}] {block.text.strip()}")

        if resp.stop_reason != "tool_use":  # tidak minta tool = jawaban final
            return

        # eksekusi semua tool yang diminta, lalu kirim hasilnya kembali
        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for block in resp.content:
            if block.type == "tool_use":
                if block.name == "run_query":
                    query_key = " ".join(block.input["sql"].split()).casefold()
                    if query_key in seen_queries:
                        print("  !! loop guard: query yang sama dipanggil lagi; hentikan loop.")
                        return
                    seen_queries.add(query_key)
                fn = TOOLS[block.name][0]
                out = fn(**block.input) if block.input else fn()
                print(f"  >> {block.name}({json.dumps(block.input, ensure_ascii=False)})")
                results.append({"type": "tool_result",
                                "tool_use_id": block.id, "content": str(out)})
        messages.append({"role": "user", "content": results})

    print("\n(hentian: batas putaran tercapai)")


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or input("Pertanyaan untuk agent: ")
    ask(q)
