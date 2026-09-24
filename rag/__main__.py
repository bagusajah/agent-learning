"""CLI paket RAG. Satu pintu untuk semua sub-perintah:

    .venv/bin/python -m rag ingest docs/handbook.pdf
    .venv/bin/python -m rag ingest docs/           # satu folder .pdf/.txt/.md
    .venv/bin/python -m rag list
    .venv/bin/python -m rag search "cara reset password" -k 5
    .venv/bin/python -m rag ask    "bagaimana cara reset password?"
    .venv/bin/python -m rag delete docs/handbook.pdf

Kenapa argparse biasa, bukan click/typer? Nol dependensi tambahan —
paket ini sengaja cuma butuh sqlite-vec + pypdf.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rag.config import DEFAULT_K, LMSTUDIO_EMBED_MODEL, RAG_DB
from rag.embeddings import EmbeddingError
from rag.ingest import ingest_path
from rag.store import VectorStore

SUPPORTED = {".pdf", ".txt", ".md"}


def cmd_ingest(args: argparse.Namespace) -> int:
    store = VectorStore()
    try:
        target = Path(args.path)
        files = (
            sorted(p for p in target.iterdir() if p.suffix.lower() in SUPPORTED)
            if target.is_dir()
            else [target]
        )
        if not files:
            print(f"Tidak ada file {'/'.join(sorted(SUPPORTED))} di {target}")
            return 1
        total = 0
        for f in files:
            print(f"[ingest] {f.name}")
            total += ingest_path(f, store)
        print(f"\nOK: {total} potongan tersimpan di {store.db_path}")
        return 0 if total else 1
    finally:
        store.close()


def cmd_list(_args: argparse.Namespace) -> int:
    store = VectorStore()
    try:
        docs = store.documents()
        if not docs:
            print(f"Store kosong ({store.db_path}). Jalankan `rag ingest` dulu.")
            return 1
        print(f"{RAG_DB} — {store.count()} chunk, {len(docs)} dokumen:\n")
        for name, n in docs:
            print(f"  {n:>5}  {name}")
        return 0
    finally:
        store.close()


def cmd_search(args: argparse.Namespace) -> int:
    from rag.retrieve import search

    hits = search(args.query, k=args.k)
    if not hits:
        print("Tidak ada hasil (store kosong?)")
        return 1
    for i, h in enumerate(hits, 1):
        print(f"[{i}] {h.cite}  jarak={h.distance:.4f}  mirip={h.similarity:.4f}")
        print(f"    {h.content[:180].replace(chr(10), ' ')}...")
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    from rag.retrieve import ask

    print(ask(args.question, k=args.k))
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    store = VectorStore()
    try:
        n = store.delete_document(Path(args.document).name)
        print(f"Dihapus: {n} potongan ({args.document})" if n
              else f"Tidak ditemukan: {args.document}")
        return 0 if n else 1
    finally:
        store.close()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rag", description="RAG lokal: dokumen -> sqlite-vec -> jawaban"
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    ing = sub.add_parser("ingest", help="masukkan file/folder ke vector store")
    ing.add_argument("path")
    ing.set_defaults(func=cmd_ingest)

    lst = sub.add_parser("list", help="daftar dokumen di store")
    lst.set_defaults(func=cmd_list)

    sea = sub.add_parser("search", help="retrieval saja (tanpa LLM)")
    sea.add_argument("query")
    sea.add_argument("-k", type=int, default=DEFAULT_K)
    sea.set_defaults(func=cmd_search)

    ask_p = sub.add_parser("ask", help="retrieval + LLM lokal = jawaban")
    ask_p.add_argument("question")
    ask_p.add_argument("-k", type=int, default=DEFAULT_K)
    ask_p.set_defaults(func=cmd_ask)

    dele = sub.add_parser("delete", help="hapus satu dokumen dari store")
    dele.add_argument("document")
    dele.set_defaults(func=cmd_delete)
    return p


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.func(args)
    except EmbeddingError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    main()
