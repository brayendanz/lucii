"""
AI Memory — menyimpan fakta/preferensi yang relevan lintas percakapan, dan
menyuntikkannya ke system prompt supaya AI "mengingat" hal itu di sesi lain.
Pengguna punya kontrol penuh: lihat, hapus satu, atau hapus semua.
"""

from . import database

MAX_FACTS_IN_CONTEXT = 30


def remember(content: str):
    content = content.strip()
    if not content:
        return None
    return database.add_memory_fact(content)


def list_all():
    return database.list_memory_facts()


def forget(fact_id: int):
    database.delete_memory_fact(fact_id)


def forget_all():
    database.clear_memory_facts()


def build_memory_context():
    facts = database.list_memory_facts()[:MAX_FACTS_IN_CONTEXT]
    if not facts:
        return ""
    lines = [f"- {f['content']}" for f in facts]
    return "Hal-hal yang perlu diingat tentang pengguna (dari sesi sebelumnya):\n" + "\n".join(lines)
