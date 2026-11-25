"""
AI Agent — menyelesaikan tugas secara bertahap.

Desain keamanan: agent TIDAK pernah menjalankan perintah shell atau kode
sembarang secara otomatis. Agent hanya boleh memakai "tools" yang eksplisit
didefinisikan di sini (membuat/menyunting file di Code Workspace, mencari
Knowledge Base), dan SETIAP tindakan yang mengubah sesuatu (menulis/menghapus
file) wajib mendapat persetujuan pengguna dulu sebelum dieksekusi — sesuai
prinsip "Approval Engine" yang kamu minta.
"""

import json
import re

from . import ai_client
from . import database
from . import code_workspace
from . import knowledge_base

AGENT_SYSTEM_PROMPT = """Kamu adalah perencana tugas AI Agent di DevSentry AI.
Tugasmu memecah permintaan pengguna menjadi langkah-langkah konkret yang bisa
dieksekusi oleh tools berikut:
- "create_file": membuat/menulis file di Code Workspace. Parameter: project, path, content.
- "search_knowledge": mencari informasi di Knowledge Base. Parameter: query.
- "note": langkah informasional saja (penjelasan ke pengguna), tanpa tool.

WAJIB balas HANYA dalam format JSON array seperti ini, tanpa teks lain:
[
  {"step": 1, "tool": "create_file", "description": "penjelasan singkat", "params": {"project": "...", "path": "...", "content": "..."}},
  {"step": 2, "tool": "note", "description": "penjelasan singkat", "params": {}}
]

Tindakan "create_file" dianggap tindakan penting dan akan dimintakan
persetujuan terpisah ke pengguna sebelum dieksekusi — jadi rencanakan dengan
jelas apa isi filenya di tahap ini."""

ALLOWED_TOOLS = {"create_file", "search_knowledge", "note"}


class AgentError(Exception):
    pass


def _extract_json_array(text):
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        raise AgentError("AI tidak mengembalikan rencana dalam format yang bisa dibaca.")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise AgentError(f"Rencana dari AI tidak valid (JSON error: {e}).")


def create_plan(goal: str):
    messages = [{"role": "user", "content": goal}]
    raw = ai_client.chat(messages, system_prompt=AGENT_SYSTEM_PROMPT, temperature=0.2)
    plan = _extract_json_array(raw)

    for step in plan:
        if step.get("tool") not in ALLOWED_TOOLS:
            step["tool"] = "note"
        step["status"] = "pending"

    task_id = database.create_agent_task(goal, json.dumps(plan, ensure_ascii=False))
    return task_id, plan


def get_task(task_id):
    task = database.get_agent_task(task_id)
    if not task:
        raise AgentError("Task tidak ditemukan.")
    task["plan"] = json.loads(task["plan_json"])
    return task


def execute_step(task_id, step_index):
    """Eksekusi satu langkah SETELAH disetujui pengguna. Mengembalikan hasil eksekusi."""
    task = get_task(task_id)
    plan = task["plan"]

    if step_index < 0 or step_index >= len(plan):
        raise AgentError("Langkah tidak valid.")

    step = plan[step_index]
    tool = step.get("tool")
    params = step.get("params", {})
    result = None

    try:
        if tool == "create_file":
            project = params.get("project", "agent-output")
            path = params.get("path", "output.txt")
            content = params.get("content", "")
            code_workspace.create_project(project)
            code_workspace.write_file(project, path, content)
            result = f"File '{path}' dibuat di proyek '{project}'."

        elif tool == "search_knowledge":
            query = params.get("query", "")
            context, sources = knowledge_base.build_context_with_citations(query)
            result = f"Ditemukan {len(sources)} sumber relevan: {', '.join(sources) if sources else '(tidak ada)'}"

        elif tool == "note":
            result = step.get("description", "Langkah informasional.")

        step["status"] = "done"
        step["result"] = result
    except Exception as e:
        step["status"] = "failed"
        step["result"] = str(e)

    database.update_agent_task(task_id, plan_json=json.dumps(plan, ensure_ascii=False))

    all_done = all(s["status"] in ("done", "failed", "skipped") for s in plan)
    if all_done:
        database.update_agent_task(task_id, status="completed")

    return step


def skip_step(task_id, step_index):
    task = get_task(task_id)
    plan = task["plan"]
    if 0 <= step_index < len(plan):
        plan[step_index]["status"] = "skipped"
        plan[step_index]["result"] = "Dilewati oleh pengguna."
    database.update_agent_task(task_id, plan_json=json.dumps(plan, ensure_ascii=False))
    return plan[step_index]
