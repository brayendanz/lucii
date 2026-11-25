"""
Menggabungkan berbagai sumber konteks (Skill aktif, Plugin aktif, AI Memory,
Knowledge Base/RAG) ke dalam satu system prompt final sebelum dikirim ke AI.
"""

from . import database
from . import memory
from . import knowledge_base

MAX_SKILL_CONTENT_CHARS = 6000


def _relevant_skills(user_message, skills):
    """Heuristik sederhana: skill selalu dikenalkan lewat deskripsi singkat;
    isi penuh SKILL.md hanya disertakan jika ada kata kunci dari nama/deskripsi
    skill yang muncul di pesan pengguna (mirip 'AI memilih Skill sesuai kebutuhan')."""
    msg_lower = user_message.lower()
    relevant = []
    for s in skills:
        keywords = (s["name"] + " " + s["description"]).lower().split()
        if any(len(k) > 3 and k in msg_lower for k in keywords):
            relevant.append(s)
    return relevant


def build_system_prompt(base_prompt, user_message, use_knowledge_base=True):
    parts = [base_prompt]

    # --- AI Memory ---
    mem_context = memory.build_memory_context()
    if mem_context:
        parts.append(mem_context)

    # --- Skills ---
    skills = database.get_enabled_skills()
    if skills:
        skill_index = "\n".join(f"- {s['name']}: {s['description']}" for s in skills)
        parts.append(f"Skill yang tersedia (aktif):\n{skill_index}")

        relevant = _relevant_skills(user_message, skills)
        for s in relevant:
            content = s["skill_md"][:MAX_SKILL_CONTENT_CHARS]
            parts.append(f"--- Instruksi Skill '{s['name']}' (diterapkan karena relevan) ---\n{content}")

    # --- Plugins (deklaratif) ---
    plugins = database.get_enabled_plugins()
    if plugins:
        for p in plugins:
            import json
            manifest = json.loads(p["manifest_json"])
            instructions = manifest.get("instructions", "")
            if instructions:
                parts.append(f"--- Instruksi tambahan dari Plugin '{p['name']}' ---\n{instructions}")

    # --- Knowledge Base / RAG ---
    sources = []
    if use_knowledge_base:
        kb_context, sources = knowledge_base.build_context_with_citations(user_message)
        if kb_context:
            parts.append(
                "--- Potongan relevan dari Knowledge Base (sertakan nama sumber saat menjawab) ---\n"
                + kb_context
            )

    return "\n\n".join(parts), sources
