#!/usr/bin/env python3
"""
Multi-agent text-to-SQL: 3 agen spesialis + 1 orkestrator (kode Python biasa).

Pipeline:

    pertanyaan user
        |
        v
    [1] SCHEMA ANALYST   (tools: list_tables, get_schema)
        output: JSON {tables, notes} -- konteks schema yang relevan
        |
        v
    [2] SQL WRITER       (tools: run_query)
        output: query SQL + hasil eksekusi
        |            ^
        |            |  retry (maks 2x) dengan feedback
        v            |
    [3] DATA VALIDATOR    (tanpa tools -- murni reasoning)
        verdict OK  -> jawab user
        verdict FIX -> kirim feedback kembali ke SQL WRITER

Pelajaran utama dibanding agent.py:
- agen berkomunikasi lewat STRUKTUR (JSON), bukan obrolan bebas
- least privilege: tiap agen hanya dapat tool yang ia butuhkan
- orkestrator = kode deterministik dengan anggaran retry
- validator butuharkan kualitas: hasil kosong / tidak menjawab = FIX

Jalankan:
    python3 agent_multi.py "Genre apa yang paling banyak terjual per negara?"
"""

import json
import re
import sqlite3
import sys

from anthropic import Anthropic

DB_PATH = "data/Chinook.db"
MODEL = "claude-sonnet-4-5"
MAX_RETRIES = 2  # berapa kali validator boleh mengembalikan pekerjaan ke penulis

client = Anthropic()


# ================================================================
# TOOLS DATABASE (implementasi yang sama untuk semua agen;
# yang membedakan adalah TOOL MANA yang boleh dipakai tiap agen)
# ================================================================

def list_tables() -> str:
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    con.close()
    return ", ".join(r[0] for r in rows)


def get_schema(table: str) -> str:
    con = sqlite3.connect(DB_PATH)
    row = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    con.close()
    return row[0] if row else f"Tabel '{table}' tidak ditemukan."


def run_query(sql: str) -> str:
    if not sql.strip().upper().startswith("SELECT"):
        return "DITOLAK: hanya SELECT yang diizinkan."
    con = sqlite3.connect(DB_PATH)
    try:
        rows = con.execute(sql).fetchmany(50)
        cols = [d[0] for d in con.description]
        if not rows:
            return "(hasil kosong)"
        return " | ".join(cols) + "\n" + "\n".join(
            " | ".join(str(v) for v in r) for r in rows
        )
    except Exception as e:
        return f"SQL ERROR: {e}"
    finally:
        con.close()


SPEC_LIST_TABLES = {
    "name": "list_tables",
    "description": "Lihat daftar tabel di database",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}
SPEC_GET_SCHEMA = {
    "name": "get_schema",
    "description": "Lihat struktur/kolom sebuah tabel",
    "input_schema": {
        "type": "object",
        "properties": {"table": {"type": "string"}},
        "required": ["table"],
    },
}
SPEC_RUN_QUERY = {
    "name": "run_query",
    "description": "Jalankan query SQL SELECT dan kembalikan hasilnya",
    "input_schema": {
        "type": "object",
        "properties": {"sql": {"type": "string"}},
        "required": ["sql"],
    },
}

IMPL = {"list_tables": list_tables, "get_schema": get_schema, "run_query": run_query}


# ================================================================
# MESIN AGEN GENERIK: satu fungsi loop untuk semua agen.
# Beda agen = beda (nama, system prompt, daftar tool).
# ================================================================

def run_agent(name: str, system: str, tools: list, user_msg: str,
              max_turns: int = 6) -> str:
    """Jalankan satu agen sampai selesai; kembalikan teks finalnya."""
    messages = [{"role": "user", "content": user_msg}]
    print(f"\n{'=' * 60}\n🤖 AGENT AKTIF: {name}\n{'=' * 60}")
    for turn in range(1, max_turns + 1):
        resp = client.messages.create(
            model=MODEL, max_tokens=1500, system=system,
            tools=tools, messages=messages,
        )
        for block in resp.content:
            if block.type == "text" and block.text.strip():
                print(f"[{name} | putaran {turn}] {block.text.strip()[:400]}")
        if resp.stop_reason != "tool_use":
            return "".join(b.text for b in resp.content if b.type == "text")

        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for block in resp.content:
            if block.type == "tool_use":
                out = IMPL[block.name](**block.input)
                print(f"  >> {block.name}({json.dumps(block.input, ensure_ascii=False)[:120]})")
                results.append({"type": "tool_result",
                                "tool_use_id": block.id, "content": str(out)})
        messages.append({"role": "user", "content": results})
    return "(batas putaran tercapai tanpa jawaban final)"


def extract_json(text: str) -> dict:
    """Pars JSON secara toleran: ambil {..} pertama-sampai-terakhir."""
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {}


# ================================================================
# [1] SCHEMA ANALYST: petakan schema, serahkan konteksnya
# ================================================================

def schema_analyst(question: str) -> str:
    text = run_agent(
        name="SCHEMA ANALYST",
        system=(
            "Kamu analis schema database SQLite. Tugasmu: temukan tabel dan kolom "
            "yang relevan untuk menjawab pertanyaan user. Lihat daftar tabel, buka "
            "schema tabel yang relevan (maksimal 4 tabel). Jangan menulis SQL. "
            "Akhiri dengan HANYA blok JSON:\n"
            '{"tables": ["t1", "t2"], "notes": "kolom kunci & cara join dalam 1-2 kalimat"}'
        ),
        tools=[SPEC_LIST_TABLES, SPEC_GET_SCHEMA],
        user_msg=f"Pertanyaan user: {question}",
    )
    data = extract_json(text)
    if data.get("tables"):
        ctx = json.dumps(data, ensure_ascii=False)
        print(f"\n📤 HANDOFF -> SQL WRITER: {ctx}")
        return ctx
    return text  # fallback: kirim teks mentah kalau JSON tidak terbentuk


# ================================================================
# [2] SQL WRITER: tulis & uji query (boleh kena retry)
# ================================================================

def sql_writer(question: str, schema_ctx: str, feedback: str | None = None) -> str:
    user_msg = (
        f"Pertanyaan user: {question}\n\n"
        f"Konteks schema dari analis:\n{schema_ctx}\n"
    )
    if feedback:
        user_msg += (
            f"\n⚠️ FEEDBACK VALIDATOR (revisi wajib):\n{feedback}\n"
            "Perbaiki SQL-mu sesuai feedback, lalu uji lagi."
        )
    text = run_agent(
        name="SQL WRITER",
        system=(
            "Kamu SQL developer untuk SQLite. Tulis SATU query SELECT yang menjawab "
            "pertanyaan, jalankan dengan tool run_query, dan perbaiki sampai sukses. "
            "Batasi hasil (LIMIT maks 20). Jawaban final harus berformat:\n"
            "```sql\n<query>\n```\nHASIL:\n<ringkasan hasil dalam 1-2 kalimat>"
        ),
        tools=[SPEC_RUN_QUERY],
        user_msg=user_msg,
        max_turns=8,
    )
    m = re.search(r"```sql\s*(.*?)\s*```", text, re.S | re.I)
    if not m:  # fallback: ambil baris SELECT pertama kalau fence hilang
        m2 = re.search(r"(SELECT[\s\S]+?)(?:\n\n|$)", text, re.I)
        return m2.group(1).strip() if m2 else text.strip()
    return m.group(1).strip()


# ================================================================
# [3] DATA VALIDATOR: tanpa tools — hanya menilai dengan kepala
# ================================================================

def validator(question: str, sql: str, result: str) -> tuple[str, str, str]:
    text = run_agent(
        name="DATA VALIDATOR",
        system=(
            "Kamu reviewer data yang ketat tapi adil. Nilai dengan tiga pertanyaan:\n"
            "1. Apakah SQL secara logika menjawab pertanyaan user?\n"
            "2. Apakah hasil masuk akal? (tidak kosong, angka tidak janggal, kolom cocok)\n"
            "3. Apakah ada risiko? (query selain SELECT, LIMIT lupa, dsb)\n"
            "Jawab HANYA blok JSON:\n"
            '{"verdict": "OK" atau "FIX", "feedback": "alasan/revisi (wajib jika FIX)", '
            '"answer": "jawaban final natural untuk user (wajib jika OK)"}'
        ),
        tools=[],  # tanpa tool: murni reasoning — agent tidak selalu butuh akses
        user_msg=f"Pertanyaan: {question}\n\nSQL:\n{sql}\n\nHasil:\n{result}",
        max_turns=2,
    )
    data = extract_json(text)
    verdict = data.get("verdict", "FIX").upper()
    return verdict, data.get("answer", text[:400]), data.get("feedback", "Format tidak valid, perbaiki.")


# ================================================================
# ORKESTRATOR: kode Python biasa — bukan magic, bukan framework
# ================================================================

def answer(question: str) -> None:
    ctx = schema_analyst(question)

    feedback = None
    for attempt in range(1, MAX_RETRIES + 2):
        print(f"\n{'#' * 60}\n▶ PERCOBAAN {attempt}/{MAX_RETRIES + 1}\n{'#' * 60}")
        sql = sql_writer(question, ctx, feedback)
        result = run_query(sql)  # orkestrator mengeksekusi ulang: verifikasi deterministik
        print(f"\n📋 SQL final:\n{sql}\n\n📋 Hasil eksekusi orkestrator:\n{result}")

        verdict, answer_text, feedback = validator(question, sql, result)
        print(f"\n🧾 VERDICT VALIDATOR: {verdict}")
        if verdict == "OK":
            print(f"\n{'✅' * 20}\nJAWABAN FINAL:\n{answer_text}\n{'✅' * 20}")
            return
        print(f"↩️  dikembalikan ke SQL WRITER: {feedback[:200]}")

    print(f"\n❌ Gagal setelah {MAX_RETRIES + 1} percobaan. Feedback terakhir: {feedback}")


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or input("Pertanyaan untuk tim agent: ")
    answer(q)
