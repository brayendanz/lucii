"""
Lapisan database — Neon Postgres (lewat psycopg3), menggantikan SQLite
karena Vercel Functions tidak punya filesystem persisten.
Semua fungsi publik (nama & signature) dipertahankan sama seperti versi
SQLite sebelumnya supaya modul lain (app.py, agent.py, dll) tidak perlu
diubah.
"""

import json
import time

import psycopg
from psycopg.rows import dict_row

import config


class DatabaseError(Exception):
    pass


def get_conn():
    if not config.DATABASE_URL:
        raise DatabaseError(
            "DATABASE_URL belum diset. Tambahkan koneksi Neon Postgres-mu di "
            "Environment Variables Vercel, lalu redeploy."
        )
    return psycopg.connect(config.DATABASE_URL, row_factory=dict_row)


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            mode TEXT NOT NULL DEFAULT 'general',
            created_at DOUBLE PRECISION NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at DOUBLE PRECISION NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id SERIAL PRIMARY KEY,
            filename TEXT NOT NULL,
            filetype TEXT NOT NULL,
            extracted_text TEXT NOT NULL,
            meta_json TEXT NOT NULL,
            is_knowledge_base INTEGER NOT NULL DEFAULT 0,
            uploaded_at DOUBLE PRECISION NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_chunks (
            id SERIAL PRIMARY KEY,
            document_id INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            chunk_text TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS memory_facts (
            id SERIAL PRIMARY KEY,
            content TEXT NOT NULL,
            created_at DOUBLE PRECISION NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS skills (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            source TEXT NOT NULL,
            skill_md TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            imported_at DOUBLE PRECISION NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS plugins (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            version TEXT NOT NULL,
            description TEXT NOT NULL,
            manifest_json TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            imported_at DOUBLE PRECISION NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS agent_tasks (
            id SERIAL PRIMARY KEY,
            goal TEXT NOT NULL,
            plan_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at DOUBLE PRECISION NOT NULL
        )
    """)
    # Metadata file Code Workspace — isi bytenya sendiri disimpan di Vercel Blob,
    # tabel ini hanya menyimpan pointer (URL blob) + nama project/path.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS workspace_projects (
            name TEXT PRIMARY KEY,
            created_at DOUBLE PRECISION NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS workspace_files (
            id SERIAL PRIMARY KEY,
            project TEXT NOT NULL,
            rel_path TEXT NOT NULL,
            blob_url TEXT NOT NULL,
            updated_at DOUBLE PRECISION NOT NULL,
            UNIQUE (project, rel_path)
        )
    """)
    conn.commit()
    conn.close()


# ---------------------------------------------------------
# Conversations
# ---------------------------------------------------------

def create_conversation(title, mode="general"):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO conversations (title, mode, created_at) VALUES (%s, %s, %s) RETURNING id",
        (title, mode, time.time()),
    )
    conv_id = cur.fetchone()["id"]
    conn.commit()
    conn.close()
    return conv_id


def rename_conversation(conv_id, new_title):
    conn = get_conn()
    conn.execute("UPDATE conversations SET title = %s WHERE id = %s", (new_title, conv_id))
    conn.commit()
    conn.close()


def delete_conversation(conv_id):
    conn = get_conn()
    conn.execute("DELETE FROM messages WHERE conversation_id = %s", (conv_id,))
    conn.execute("DELETE FROM conversations WHERE id = %s", (conv_id,))
    conn.commit()
    conn.close()


def add_message(conversation_id, role, content):
    conn = get_conn()
    conn.execute(
        "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (%s, %s, %s, %s)",
        (conversation_id, role, content, time.time()),
    )
    conn.commit()
    conn.close()


def get_messages(conversation_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT role, content FROM messages WHERE conversation_id = %s ORDER BY id ASC",
        (conversation_id,),
    ).fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def list_conversations():
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, title, mode, created_at FROM conversations ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------
# Documents (Document Analysis + Knowledge Base)
# ---------------------------------------------------------

def add_document(filename, filetype, extracted_text, meta_json, is_knowledge_base=0):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO documents (filename, filetype, extracted_text, meta_json, is_knowledge_base, uploaded_at)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
        (filename, filetype, extracted_text, meta_json, is_knowledge_base, time.time()),
    )
    doc_id = cur.fetchone()["id"]
    conn.commit()
    conn.close()
    return doc_id


def list_documents(knowledge_base_only=False):
    conn = get_conn()
    if knowledge_base_only:
        rows = conn.execute(
            "SELECT id, filename, filetype, meta_json, is_knowledge_base, uploaded_at FROM documents WHERE is_knowledge_base = 1 ORDER BY uploaded_at DESC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, filename, filetype, meta_json, is_knowledge_base, uploaded_at FROM documents ORDER BY uploaded_at DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_document(doc_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM documents WHERE id = %s", (doc_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_documents_by_ids(doc_ids):
    if not doc_ids:
        return []
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM documents WHERE id = ANY(%s)", (list(doc_ids),)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_document(doc_id):
    conn = get_conn()
    conn.execute("DELETE FROM knowledge_chunks WHERE document_id = %s", (doc_id,))
    conn.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------
# Knowledge Base chunks (untuk RAG)
# ---------------------------------------------------------

def add_knowledge_chunks(document_id, chunks):
    conn = get_conn()
    cur = conn.cursor()
    cur.executemany(
        "INSERT INTO knowledge_chunks (document_id, chunk_index, chunk_text) VALUES (%s, %s, %s)",
        [(document_id, i, c) for i, c in enumerate(chunks)],
    )
    conn.commit()
    conn.close()


def get_all_knowledge_chunks():
    conn = get_conn()
    rows = conn.execute("""
        SELECT kc.id, kc.document_id, kc.chunk_text, d.filename
        FROM knowledge_chunks kc
        JOIN documents d ON d.id = kc.document_id
        WHERE d.is_knowledge_base = 1
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_knowledge_chunks(document_id):
    conn = get_conn()
    conn.execute("DELETE FROM knowledge_chunks WHERE document_id = %s", (document_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------
# AI Memory
# ---------------------------------------------------------

def add_memory_fact(content):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO memory_facts (content, created_at) VALUES (%s, %s) RETURNING id",
        (content, time.time()),
    )
    fact_id = cur.fetchone()["id"]
    conn.commit()
    conn.close()
    return fact_id


def list_memory_facts():
    conn = get_conn()
    rows = conn.execute("SELECT id, content, created_at FROM memory_facts ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_memory_fact(fact_id):
    conn = get_conn()
    conn.execute("DELETE FROM memory_facts WHERE id = %s", (fact_id,))
    conn.commit()
    conn.close()


def clear_memory_facts():
    conn = get_conn()
    conn.execute("DELETE FROM memory_facts")
    conn.commit()
    conn.close()


# ---------------------------------------------------------
# Skills (SKILL.md disimpan langsung sebagai teks di Postgres)
# ---------------------------------------------------------

def add_skill(name, description, source, skill_md):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO skills (name, description, source, skill_md, enabled, imported_at)
           VALUES (%s, %s, %s, %s, 1, %s) RETURNING id""",
        (name, description, source, skill_md, time.time()),
    )
    skill_id = cur.fetchone()["id"]
    conn.commit()
    conn.close()
    return skill_id


def list_skills():
    conn = get_conn()
    rows = conn.execute("SELECT id, name, description, source, enabled, imported_at FROM skills ORDER BY imported_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_skill(skill_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM skills WHERE id = %s", (skill_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_enabled_skills():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM skills WHERE enabled = 1").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_skill_enabled(skill_id, enabled):
    conn = get_conn()
    conn.execute("UPDATE skills SET enabled = %s WHERE id = %s", (1 if enabled else 0, skill_id))
    conn.commit()
    conn.close()


def delete_skill(skill_id):
    conn = get_conn()
    conn.execute("DELETE FROM skills WHERE id = %s", (skill_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------
# Plugins (manifest disimpan langsung sebagai teks di Postgres)
# ---------------------------------------------------------

def add_plugin(name, version, description, manifest_json):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO plugins (name, version, description, manifest_json, enabled, imported_at)
           VALUES (%s, %s, %s, %s, 1, %s) RETURNING id""",
        (name, version, description, manifest_json, time.time()),
    )
    plugin_id = cur.fetchone()["id"]
    conn.commit()
    conn.close()
    return plugin_id


def list_plugins():
    conn = get_conn()
    rows = conn.execute("SELECT id, name, version, description, enabled, imported_at FROM plugins ORDER BY imported_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_plugin(plugin_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM plugins WHERE id = %s", (plugin_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_enabled_plugins():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM plugins WHERE enabled = 1").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_plugin_enabled(plugin_id, enabled):
    conn = get_conn()
    conn.execute("UPDATE plugins SET enabled = %s WHERE id = %s", (1 if enabled else 0, plugin_id))
    conn.commit()
    conn.close()


def delete_plugin(plugin_id):
    conn = get_conn()
    conn.execute("DELETE FROM plugins WHERE id = %s", (plugin_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------
# Settings
# ---------------------------------------------------------

DEFAULT_SETTINGS = {
    "active_model": "claude-sonnet-4-5",
    "temperature": "0.4",
    "max_tokens": "4096",
    "response_language": "id",
    "response_style": "normal",
    "theme": "dark",
    "display_name": "",
}


def get_setting(key, default=None):
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key = %s", (key,)).fetchone()
    conn.close()
    if row:
        return row["value"]
    return default if default is not None else DEFAULT_SETTINGS.get(key)


def get_all_settings():
    conn = get_conn()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    result = dict(DEFAULT_SETTINGS)
    result.update({r["key"]: r["value"] for r in rows})
    return result


def set_setting(key, value):
    conn = get_conn()
    conn.execute(
        """INSERT INTO settings (key, value) VALUES (%s, %s)
           ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
        (key, str(value)),
    )
    conn.commit()
    conn.close()


def clear_all_history():
    conn = get_conn()
    conn.execute("DELETE FROM messages")
    conn.execute("DELETE FROM conversations")
    conn.commit()
    conn.close()


# ---------------------------------------------------------
# AI Agent
# ---------------------------------------------------------

def create_agent_task(goal, plan_json):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO agent_tasks (goal, plan_json, status, created_at) VALUES (%s, %s, 'pending', %s) RETURNING id",
        (goal, plan_json, time.time()),
    )
    task_id = cur.fetchone()["id"]
    conn.commit()
    conn.close()
    return task_id


def get_agent_task(task_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM agent_tasks WHERE id = %s", (task_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_agent_task(task_id, plan_json=None, status=None):
    conn = get_conn()
    if plan_json is not None:
        conn.execute("UPDATE agent_tasks SET plan_json = %s WHERE id = %s", (plan_json, task_id))
    if status is not None:
        conn.execute("UPDATE agent_tasks SET status = %s WHERE id = %s", (status, task_id))
    conn.commit()
    conn.close()


def list_agent_tasks():
    conn = get_conn()
    rows = conn.execute("SELECT id, goal, status, created_at FROM agent_tasks ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------
# Code Workspace — metadata proyek & file (isi byte ada di Vercel Blob)
# ---------------------------------------------------------

def ws_create_project(name):
    conn = get_conn()
    conn.execute(
        "INSERT INTO workspace_projects (name, created_at) VALUES (%s, %s) ON CONFLICT (name) DO NOTHING",
        (name, time.time()),
    )
    conn.commit()
    conn.close()


def ws_list_projects():
    conn = get_conn()
    rows = conn.execute("SELECT name FROM workspace_projects ORDER BY name ASC").fetchall()
    conn.close()
    return [r["name"] for r in rows]


def ws_delete_project(name):
    conn = get_conn()
    files = conn.execute("SELECT blob_url FROM workspace_files WHERE project = %s", (name,)).fetchall()
    conn.execute("DELETE FROM workspace_files WHERE project = %s", (name,))
    conn.execute("DELETE FROM workspace_projects WHERE name = %s", (name,))
    conn.commit()
    conn.close()
    return [f["blob_url"] for f in files]


def ws_list_files(project):
    conn = get_conn()
    rows = conn.execute(
        "SELECT rel_path FROM workspace_files WHERE project = %s ORDER BY rel_path ASC", (project,)
    ).fetchall()
    conn.close()
    return [r["rel_path"] for r in rows]


def ws_get_file(project, rel_path):
    conn = get_conn()
    row = conn.execute(
        "SELECT blob_url FROM workspace_files WHERE project = %s AND rel_path = %s", (project, rel_path)
    ).fetchone()
    conn.close()
    return row["blob_url"] if row else None


def ws_upsert_file(project, rel_path, blob_url):
    conn = get_conn()
    conn.execute(
        """INSERT INTO workspace_files (project, rel_path, blob_url, updated_at)
           VALUES (%s, %s, %s, %s)
           ON CONFLICT (project, rel_path) DO UPDATE SET blob_url = EXCLUDED.blob_url, updated_at = EXCLUDED.updated_at""",
        (project, rel_path, blob_url, time.time()),
    )
    conn.commit()
    conn.close()


def ws_delete_file(project, rel_path):
    conn = get_conn()
    row = conn.execute(
        "SELECT blob_url FROM workspace_files WHERE project = %s AND rel_path = %s", (project, rel_path)
    ).fetchone()
    conn.execute("DELETE FROM workspace_files WHERE project = %s AND rel_path = %s", (project, rel_path))
    conn.commit()
    conn.close()
    return row["blob_url"] if row else None
