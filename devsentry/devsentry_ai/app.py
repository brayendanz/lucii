import os
import io
import json
import uuid
from functools import wraps
from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify, render_template, abort, session, redirect, url_for, send_file

import config
from modules import database
from modules import ai_client
from modules import documents as doc_module
from modules import code_workspace
from modules import skill_manager
from modules import plugin_manager
from modules import memory
from modules import knowledge_base
from modules import context_builder
from modules import agent
from modules.personas import MODES
from modules.security import defensive_snippets

app = Flask(__name__)
app.config["SECRET_KEY"] = config.SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = max(config.MAX_UPLOAD_SIZE_MB, config.MAX_WORKSPACE_FILE_SIZE_MB) * 1024 * 1024

# Inisialisasi tabel Postgres. Dibungkus try/except supaya aplikasi tetap bisa
# start (dan menunjukkan pesan error yang jelas di tiap endpoint) walaupun
# DATABASE_URL belum diset, alih-alih membuat seluruh app gagal diimpor.
try:
    database.init_db()
except database.DatabaseError as e:
    print(f"[PERINGATAN] {e}")


# ---------------------------------------------------------
# Admin gate — melindungi Skill & Plugin Manager jika situs publik
# ---------------------------------------------------------
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if config.SKILLS_PLUGINS_PUBLIC:
            return f(*args, **kwargs)
        if session.get("admin_unlocked"):
            return f(*args, **kwargs)
        return jsonify({"error": "Perlu kode akses admin untuk mengelola Skill/Plugin. Buka /admin/login."}), 403
    return wrapper


@app.route("/admin/login", methods=["GET"])
def admin_login_page():
    return """
    <h3>Masuk sebagai Admin (Skill & Plugin Manager)</h3>
    <form method="post" action="/admin/do-login">
      <input type="password" name="code" placeholder="Kode akses admin">
      <button type="submit">Masuk</button>
    </form>
    """


@app.route("/admin/do-login", methods=["POST"])
def admin_do_login():
    code = request.form.get("code", "")
    if config.ADMIN_ACCESS_CODE and code == config.ADMIN_ACCESS_CODE:
        session["admin_unlocked"] = True
        return redirect("/")
    return redirect(url_for("admin_login_page"))


# ---------------------------------------------------------
# Lab keamanan edukatif - dikunci kode akses (situs ini publik/online)
# ---------------------------------------------------------
if config.SECURITY_LAB_ENABLED:
    from modules.security.vuln_lab import vuln_lab_bp

    @app.before_request
    def restrict_lab_with_access_code():
        if request.path.startswith("/lab"):
            if request.path in ("/lab/login", "/lab/do-login"):
                return
            if not session.get("lab_unlocked"):
                return redirect(url_for("lab_login"))

    @app.route("/lab/login", methods=["GET"])
    def lab_login():
        return """
        <h3>Masuk ke Lab Kerentanan</h3>
        <form method="post" action="/lab/do-login">
          <input type="password" name="code" placeholder="Kode akses">
          <button type="submit">Masuk</button>
        </form>
        """

    @app.route("/lab/do-login", methods=["POST"])
    def lab_do_login():
        code = request.form.get("code", "")
        if code and code == config.LAB_ACCESS_CODE:
            session["lab_unlocked"] = True
            return redirect("/lab/")
        return redirect(url_for("lab_login"))

    app.register_blueprint(vuln_lab_bp)


# ---------------------------------------------------------
# Halaman utama
# ---------------------------------------------------------
@app.route("/")
def index():
    conversations = database.list_conversations()
    modes = list(MODES.keys())
    settings = database.get_all_settings()
    return render_template(
        "index.html",
        conversations=conversations,
        modes=modes,
        lab_enabled=config.SECURITY_LAB_ENABLED,
        available_models=config.AVAILABLE_MODELS,
        settings=settings,
    )


# ---------------------------------------------------------
# API: percakapan
# ---------------------------------------------------------
@app.route("/api/conversations", methods=["POST"])
def api_create_conversation():
    data = request.get_json(force=True)
    title = data.get("title", "Percakapan baru")
    mode = data.get("mode", "general")
    conv_id = database.create_conversation(title, mode)
    return jsonify({"id": conv_id, "title": title, "mode": mode})


@app.route("/api/conversations/<int:conv_id>", methods=["PATCH"])
def api_rename_conversation(conv_id):
    data = request.get_json(force=True)
    new_title = data.get("title", "").strip()
    if not new_title:
        return jsonify({"error": "Judul tidak boleh kosong"}), 400
    database.rename_conversation(conv_id, new_title)
    return jsonify({"id": conv_id, "title": new_title})


@app.route("/api/conversations/<int:conv_id>", methods=["DELETE"])
def api_delete_conversation(conv_id):
    database.delete_conversation(conv_id)
    return jsonify({"deleted": conv_id})


@app.route("/api/conversations/<int:conv_id>/messages", methods=["GET"])
def api_get_messages(conv_id):
    return jsonify(database.get_messages(conv_id))


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(force=True)
    conv_id = data.get("conversation_id")
    mode = data.get("mode", "general")
    user_message = data.get("message", "").strip()
    document_ids = data.get("document_ids") or []
    compare_models = data.get("compare_models") or []  # fitur Multi-Model Intelligence

    if not user_message:
        return jsonify({"error": "Pesan kosong"}), 400
    if not conv_id:
        return jsonify({"error": "conversation_id wajib diisi"}), 400

    base_prompt = MODES.get(mode, MODES["general"])

    # Sisipkan dokumen terpilih (Document Analysis) ke system prompt permintaan ini saja
    if document_ids:
        docs = database.get_documents_by_ids(document_ids)
        if docs:
            context_parts = []
            per_doc_limit = max(config.MAX_DOC_CHARS_FOR_AI // max(len(docs), 1), 2000)
            for d in docs:
                text = doc_module.truncate_for_ai(d["extracted_text"], per_doc_limit)
                context_parts.append(f"=== DOKUMEN: {d['filename']} ===\n{text}")
            base_prompt = base_prompt + "\n\n--- DOKUMEN TERLAMPIR ---\n" + "\n\n".join(context_parts)

    # Gabungkan dengan Skill aktif, Plugin aktif, AI Memory, dan Knowledge Base/RAG
    system_prompt, kb_sources = context_builder.build_system_prompt(
        base_prompt, user_message, use_knowledge_base=(mode != "document_analysis")
    )

    history = database.get_messages(conv_id)
    database.add_message(conv_id, "user", user_message)
    messages = history + [{"role": "user", "content": user_message}]

    settings = database.get_all_settings()
    temperature = float(settings.get("temperature", 0.4))
    max_tokens = int(settings.get("max_tokens", 4096))
    active_model = settings.get("active_model")

    # --- Multi-Model Intelligence: bandingkan beberapa model sekaligus ---
    if compare_models:
        results = ai_client.chat_multi_model(
            messages, system_prompt=system_prompt, model_ids=compare_models,
            temperature=temperature, max_tokens=max_tokens,
        )
        # simpan hasil model utama saja ke riwayat supaya percakapan tetap koheren
        primary = compare_models[0]
        if "reply" in results.get(primary, {}):
            database.add_message(conv_id, "assistant", results[primary]["reply"])
        return jsonify({"compare": results, "sources": kb_sources})

    try:
        reply = ai_client.chat(messages, system_prompt=system_prompt, model=active_model,
                                temperature=temperature, max_tokens=max_tokens)
    except ai_client.AIError as e:
        return jsonify({"error": str(e)}), 503

    database.add_message(conv_id, "assistant", reply)
    return jsonify({"reply": reply, "sources": kb_sources})


# ---------------------------------------------------------
# API: snippet keamanan defensif siap pakai
# ---------------------------------------------------------
@app.route("/api/security/snippets", methods=["GET"])
def api_list_snippets():
    return jsonify(defensive_snippets.list_snippets())


@app.route("/api/security/snippets/<snippet_id>", methods=["GET"])
def api_get_snippet(snippet_id):
    snippet = defensive_snippets.get_snippet(snippet_id)
    if not snippet:
        return jsonify({"error": "Snippet tidak ditemukan"}), 404
    return jsonify(snippet)


# ---------------------------------------------------------
# API: Document Analysis — upload, list, lihat, hapus
# ---------------------------------------------------------
@app.route("/api/documents", methods=["POST"])
def api_upload_document():
    if "file" not in request.files:
        return jsonify({"error": "Tidak ada file yang diunggah"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "Nama file kosong"}), 400

    if not doc_module.allowed_file(file.filename):
        return jsonify({"error": "Format file tidak didukung. Gunakan PDF, DOCX, TXT, CSV, atau JSON."}), 400

    mark_as_kb = request.form.get("as_knowledge_base", "false").lower() == "true"
    original_name = secure_filename(file.filename)
    ext = doc_module.get_extension(original_name)

    file_bytes = file.read()

    try:
        text, meta = doc_module.extract_text(file_bytes, ext)
    except doc_module.DocumentError as e:
        return jsonify({"error": str(e)}), 500

    doc_id = database.add_document(
        filename=original_name,
        filetype=ext,
        extracted_text=text,
        meta_json=json.dumps(meta, ensure_ascii=False),
        is_knowledge_base=1 if mark_as_kb else 0,
    )

    chunks_indexed = 0
    if mark_as_kb:
        chunks_indexed = knowledge_base.index_document(doc_id, text)

    return jsonify({
        "id": doc_id,
        "filename": original_name,
        "filetype": ext,
        "meta": meta,
        "preview": text[:500],
        "is_knowledge_base": mark_as_kb,
        "chunks_indexed": chunks_indexed,
    })


@app.route("/api/documents", methods=["GET"])
def api_list_documents():
    kb_only = request.args.get("knowledge_base_only", "false").lower() == "true"
    docs = database.list_documents(knowledge_base_only=kb_only)
    for d in docs:
        d["meta"] = json.loads(d.pop("meta_json"))
    return jsonify(docs)


@app.route("/api/documents/<int:doc_id>", methods=["GET"])
def api_get_document(doc_id):
    d = database.get_document(doc_id)
    if not d:
        return jsonify({"error": "Dokumen tidak ditemukan"}), 404
    return jsonify({
        "id": d["id"],
        "filename": d["filename"],
        "filetype": d["filetype"],
        "meta": json.loads(d["meta_json"]),
        "preview": d["extracted_text"][:2000],
        "is_knowledge_base": bool(d["is_knowledge_base"]),
    })


@app.route("/api/documents/<int:doc_id>", methods=["DELETE"])
def api_delete_document(doc_id):
    database.delete_document(doc_id)
    return jsonify({"deleted": doc_id})


# ---------------------------------------------------------
# API: Code Workspace — proyek & file
# ---------------------------------------------------------
@app.route("/api/workspace/projects", methods=["GET"])
def api_list_projects():
    return jsonify(code_workspace.list_projects())


@app.route("/api/workspace/projects", methods=["POST"])
def api_create_project():
    data = request.get_json(force=True)
    name = data.get("name", "").strip()
    try:
        code_workspace.create_project(name)
        return jsonify({"created": name})
    except code_workspace.WorkspaceError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/workspace/projects/<project>", methods=["DELETE"])
def api_delete_project(project):
    code_workspace.delete_project(project)
    return jsonify({"deleted": project})


@app.route("/api/workspace/projects/<project>/files", methods=["GET"])
def api_list_project_files(project):
    try:
        return jsonify(code_workspace.list_files(project))
    except code_workspace.WorkspaceError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/workspace/projects/<project>/files/<path:rel_path>", methods=["GET"])
def api_read_file(project, rel_path):
    try:
        content = code_workspace.read_file(project, rel_path)
        return jsonify({"path": rel_path, "content": content})
    except code_workspace.WorkspaceError as e:
        return jsonify({"error": str(e)}), 404


@app.route("/api/workspace/projects/<project>/files/<path:rel_path>", methods=["PUT"])
def api_write_file(project, rel_path):
    data = request.get_json(force=True)
    content = data.get("content", "")
    try:
        code_workspace.write_file(project, rel_path, content)
        return jsonify({"saved": rel_path})
    except code_workspace.WorkspaceError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/workspace/projects/<project>/files/<path:rel_path>", methods=["DELETE"])
def api_delete_file(project, rel_path):
    try:
        code_workspace.delete_file(project, rel_path)
        return jsonify({"deleted": rel_path})
    except code_workspace.WorkspaceError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/workspace/projects/<project>/download", methods=["GET"])
def api_download_project(project):
    try:
        zip_bytes = code_workspace.zip_project_bytes(project)
        return send_file(
            io.BytesIO(zip_bytes),
            as_attachment=True,
            download_name=f"{project}.zip",
            mimetype="application/zip",
        )
    except code_workspace.WorkspaceError as e:
        return jsonify({"error": str(e)}), 400


# ---------------------------------------------------------
# API: Skill Manager
# ---------------------------------------------------------
@app.route("/api/skills", methods=["GET"])
def api_list_skills():
    return jsonify(database.list_skills())


@app.route("/api/skills/import/github", methods=["POST"])
@admin_required
def api_import_skill_github():
    data = request.get_json(force=True)
    url = data.get("url", "")
    try:
        imported = skill_manager.import_from_github(url)
        return jsonify({"imported": imported})
    except skill_manager.SkillError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/skills/import/zip", methods=["POST"])
@admin_required
def api_import_skill_zip():
    if "file" not in request.files:
        return jsonify({"error": "Tidak ada file ZIP"}), 400
    try:
        imported = skill_manager.import_from_zip(request.files["file"])
        return jsonify({"imported": imported})
    except skill_manager.SkillError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/skills/<int:skill_id>/toggle", methods=["POST"])
@admin_required
def api_toggle_skill(skill_id):
    data = request.get_json(force=True)
    database.set_skill_enabled(skill_id, data.get("enabled", True))
    return jsonify({"id": skill_id, "enabled": data.get("enabled", True)})


@app.route("/api/skills/<int:skill_id>", methods=["DELETE"])
@admin_required
def api_delete_skill(skill_id):
    database.delete_skill(skill_id)
    return jsonify({"deleted": skill_id})


# ---------------------------------------------------------
# API: Plugin Manager
# ---------------------------------------------------------
@app.route("/api/plugins", methods=["GET"])
def api_list_plugins():
    return jsonify(database.list_plugins())


@app.route("/api/plugins/import/github", methods=["POST"])
@admin_required
def api_import_plugin_github():
    data = request.get_json(force=True)
    url = data.get("url", "")
    try:
        imported = plugin_manager.import_from_github(url)
        return jsonify({"imported": imported})
    except plugin_manager.PluginError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/plugins/import/zip", methods=["POST"])
@admin_required
def api_import_plugin_zip():
    if "file" not in request.files:
        return jsonify({"error": "Tidak ada file ZIP"}), 400
    try:
        imported = plugin_manager.import_from_zip(request.files["file"])
        return jsonify({"imported": imported})
    except plugin_manager.PluginError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/plugins/<int:plugin_id>/toggle", methods=["POST"])
@admin_required
def api_toggle_plugin(plugin_id):
    data = request.get_json(force=True)
    database.set_plugin_enabled(plugin_id, data.get("enabled", True))
    return jsonify({"id": plugin_id, "enabled": data.get("enabled", True)})


@app.route("/api/plugins/<int:plugin_id>", methods=["DELETE"])
@admin_required
def api_delete_plugin(plugin_id):
    database.delete_plugin(plugin_id)
    return jsonify({"deleted": plugin_id})


# ---------------------------------------------------------
# API: AI Memory
# ---------------------------------------------------------
@app.route("/api/memory", methods=["GET"])
def api_list_memory():
    return jsonify(memory.list_all())


@app.route("/api/memory", methods=["POST"])
def api_add_memory():
    data = request.get_json(force=True)
    content = data.get("content", "")
    fact_id = memory.remember(content)
    if fact_id is None:
        return jsonify({"error": "Konten kosong"}), 400
    return jsonify({"id": fact_id, "content": content})


@app.route("/api/memory/<int:fact_id>", methods=["DELETE"])
def api_delete_memory(fact_id):
    memory.forget(fact_id)
    return jsonify({"deleted": fact_id})


@app.route("/api/memory/clear", methods=["POST"])
def api_clear_memory():
    memory.forget_all()
    return jsonify({"cleared": True})


# ---------------------------------------------------------
# API: Knowledge Base langsung (pencarian manual, untuk debugging/transparansi)
# ---------------------------------------------------------
@app.route("/api/knowledge/search", methods=["GET"])
def api_search_knowledge():
    query = request.args.get("q", "")
    results = knowledge_base.search(query)
    return jsonify(results)


# ---------------------------------------------------------
# API: Model Manager & Settings
# ---------------------------------------------------------
@app.route("/api/models", methods=["GET"])
def api_list_models():
    return jsonify(config.AVAILABLE_MODELS)


@app.route("/api/settings", methods=["GET"])
def api_get_settings():
    return jsonify(database.get_all_settings())


@app.route("/api/settings", methods=["POST"])
def api_update_settings():
    data = request.get_json(force=True)
    allowed_keys = {"active_model", "temperature", "max_tokens", "response_language",
                     "response_style", "theme", "display_name"}
    for key, value in data.items():
        if key in allowed_keys:
            database.set_setting(key, value)
    return jsonify(database.get_all_settings())


@app.route("/api/settings/clear-history", methods=["POST"])
def api_clear_history():
    database.clear_all_history()
    return jsonify({"cleared": True})


# ---------------------------------------------------------
# API: AI Agent
# ---------------------------------------------------------
@app.route("/api/agent/plan", methods=["POST"])
def api_agent_plan():
    data = request.get_json(force=True)
    goal = data.get("goal", "").strip()
    if not goal:
        return jsonify({"error": "Tujuan tugas tidak boleh kosong"}), 400
    try:
        task_id, plan = agent.create_plan(goal)
        return jsonify({"task_id": task_id, "plan": plan})
    except agent.AgentError as e:
        return jsonify({"error": str(e)}), 500
    except ai_client.AIError as e:
        return jsonify({"error": str(e)}), 503


@app.route("/api/agent/tasks/<int:task_id>", methods=["GET"])
def api_agent_get_task(task_id):
    try:
        return jsonify(agent.get_task(task_id))
    except agent.AgentError as e:
        return jsonify({"error": str(e)}), 404


@app.route("/api/agent/tasks/<int:task_id>/steps/<int:step_index>/approve", methods=["POST"])
def api_agent_approve_step(task_id, step_index):
    try:
        result = agent.execute_step(task_id, step_index)
        return jsonify(result)
    except agent.AgentError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/agent/tasks/<int:task_id>/steps/<int:step_index>/skip", methods=["POST"])
def api_agent_skip_step(task_id, step_index):
    try:
        result = agent.skip_step(task_id, step_index)
        return jsonify(result)
    except agent.AgentError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/agent/tasks", methods=["GET"])
def api_agent_list_tasks():
    return jsonify(database.list_agent_tasks())


@app.route("/healthz")
def healthz():
    """Endpoint sederhana untuk health check platform hosting."""
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
