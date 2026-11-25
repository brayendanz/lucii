"""
Knowledge Base & RAG (Retrieval-Augmented Generation) — versi ringan.

Alih-alih memakai vector database + embedding API (dependency tambahan &
biaya API ekstra), modul ini memakai scoring kata kunci sederhana (mirip
TF-IDF) yang cukup efektif untuk knowledge base berskala kecil-menengah
dan tidak butuh API/model tambahan apa pun.
"""

import math
import re
from collections import Counter

from . import database

CHUNK_SIZE = 1200  # karakter per chunk
CHUNK_OVERLAP = 150


def chunk_text(text: str, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    chunks = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + chunk_size, length)
        chunks.append(text[start:end])
        if end == length:
            break
        start = end - overlap
    return chunks


def _tokenize(text: str):
    return re.findall(r"[a-zA-Z0-9]+", text.lower())


def index_document(document_id, text):
    """Pecah dokumen jadi chunk dan simpan ke tabel knowledge_chunks."""
    database.delete_knowledge_chunks(document_id)
    chunks = chunk_text(text)
    if chunks:
        database.add_knowledge_chunks(document_id, chunks)
    return len(chunks)


def _score(query_tokens, chunk_tokens, idf):
    tf = Counter(chunk_tokens)
    total = len(chunk_tokens) or 1
    score = 0.0
    for t in query_tokens:
        if t in tf:
            score += (tf[t] / total) * idf.get(t, 0)
    return score


def search(query: str, top_k=4):
    """
    Mengembalikan list of {"filename", "chunk_text", "score"} yang paling
    relevan dengan query, diurutkan dari skor tertinggi.
    """
    all_chunks = database.get_all_knowledge_chunks()
    if not all_chunks:
        return []

    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    # hitung IDF sederhana
    doc_freq = Counter()
    tokenized_chunks = []
    for c in all_chunks:
        tokens = _tokenize(c["chunk_text"])
        tokenized_chunks.append(tokens)
        for t in set(tokens):
            doc_freq[t] += 1

    n_docs = len(all_chunks)
    idf = {t: math.log((n_docs + 1) / (df + 1)) + 1 for t, df in doc_freq.items()}

    scored = []
    for c, tokens in zip(all_chunks, tokenized_chunks):
        s = _score(query_tokens, tokens, idf)
        if s > 0:
            scored.append({"filename": c["filename"], "chunk_text": c["chunk_text"], "score": s})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def build_context_with_citations(query: str, top_k=4):
    """Mengembalikan (context_string, sources_list) untuk disisipkan ke prompt AI."""
    results = search(query, top_k=top_k)
    if not results:
        return "", []

    parts = []
    sources = []
    for i, r in enumerate(results, start=1):
        parts.append(f"[Sumber {i}: {r['filename']}]\n{r['chunk_text']}")
        sources.append(r["filename"])

    context = "\n\n".join(parts)
    return context, sources
