// ============================================================
// State global
// ============================================================
let currentConversationId = null;
let selectedDocumentIds = new Set();
let currentProject = null;
let currentFile = null;
let availableModels = [];

// ============================================================
// Tab navigation
// ============================================================
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
  });
});

// ============================================================
// CHAT
// ============================================================
const chatWindow = document.getElementById("chat-window");
const chatInput = document.getElementById("chat-input");
const sendBtn = document.getElementById("send-btn");
const newChatBtn = document.getElementById("new-chat-btn");
const modeSelect = document.getElementById("mode-select");
const conversationList = document.getElementById("conversation-list");
const snippetList = document.getElementById("snippet-list");
const docUploadInput = document.getElementById("doc-upload-input");
const docAsKb = document.getElementById("doc-as-kb");
const docUploadBtn = document.getElementById("doc-upload-btn");
const docList = document.getElementById("doc-list");
const docSummarizeBtn = document.getElementById("doc-summarize-btn");
const docCompareBtn = document.getElementById("doc-compare-btn");
const compareToggle = document.getElementById("compare-toggle");
const compareModelPicker = document.getElementById("compare-model-picker");

function appendMessage(role, content, sources) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = content;
  if (sources && sources.length) {
    const src = document.createElement("div");
    src.className = "msg-sources";
    src.textContent = "Sumber: " + [...new Set(sources)].join(", ");
    div.appendChild(src);
  }
  chatWindow.appendChild(div);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function appendCompareResult(results) {
  const wrap = document.createElement("div");
  wrap.className = "compare-block";
  Object.entries(results).forEach(([model, data]) => {
    const col = document.createElement("div");
    col.className = "compare-col";
    const h4 = document.createElement("h4");
    h4.textContent = model;
    col.appendChild(h4);
    const body = document.createElement("div");
    body.textContent = data.reply || `Error: ${data.error}`;
    col.appendChild(body);
    wrap.appendChild(col);
  });
  chatWindow.appendChild(wrap);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

async function renderConversationList() {
  conversationList.innerHTML = "";
  // Data percakapan di-render dari variabel global yang diisi saat index.html load
  // (lihat initialConversations di bawah) ditambah percakapan baru yang dibuat di sesi ini.
  window.__conversations.forEach((c) => addConversationItem(c));
}

function addConversationItem(c) {
  const item = document.createElement("div");
  item.className = "conversation-item";
  item.dataset.id = c.id;

  const titleSpan = document.createElement("span");
  titleSpan.className = "conv-title";
  titleSpan.textContent = c.title;
  titleSpan.title = c.mode;
  titleSpan.addEventListener("click", () => loadConversation(c.id, c.mode));

  const renameBtn = document.createElement("button");
  renameBtn.className = "conv-btn";
  renameBtn.textContent = "✎";
  renameBtn.addEventListener("click", async (e) => {
    e.stopPropagation();
    const newTitle = prompt("Judul baru:", c.title);
    if (newTitle && newTitle.trim()) {
      await fetch(`/api/conversations/${c.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: newTitle.trim() }),
      });
      c.title = newTitle.trim();
      titleSpan.textContent = c.title;
    }
  });

  const delBtn = document.createElement("button");
  delBtn.className = "conv-btn";
  delBtn.textContent = "✕";
  delBtn.addEventListener("click", async (e) => {
    e.stopPropagation();
    if (!confirm("Hapus percakapan ini?")) return;
    await fetch(`/api/conversations/${c.id}`, { method: "DELETE" });
    item.remove();
    window.__conversations = window.__conversations.filter((x) => x.id !== c.id);
    if (currentConversationId === c.id) {
      currentConversationId = null;
      chatWindow.innerHTML = "";
    }
  });

  item.appendChild(titleSpan);
  item.appendChild(renameBtn);
  item.appendChild(delBtn);
  conversationList.appendChild(item);
}

async function createConversation() {
  const mode = modeSelect.value;
  const res = await fetch("/api/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: `Percakapan - ${mode}`, mode }),
  });
  const data = await res.json();
  currentConversationId = data.id;
  chatWindow.innerHTML = "";
  window.__conversations.unshift(data);
  conversationList.innerHTML = "";
  renderConversationList();
}

async function loadConversation(id, mode) {
  currentConversationId = id;
  modeSelect.value = mode;
  const res = await fetch(`/api/conversations/${id}/messages`);
  const messages = await res.json();
  chatWindow.innerHTML = "";
  messages.forEach((m) => appendMessage(m.role, m.content));
}

async function sendMessage(overrideMessage) {
  const message = (overrideMessage !== undefined ? overrideMessage : chatInput.value).trim();
  if (!message) return;

  if (!currentConversationId) {
    await createConversation();
  }

  appendMessage("user", message);
  chatInput.value = "";

  const thinkingEl = document.createElement("div");
  thinkingEl.className = "msg assistant";
  thinkingEl.textContent = "Memproses...";
  chatWindow.appendChild(thinkingEl);
  chatWindow.scrollTop = chatWindow.scrollHeight;

  const compareModels = compareToggle.checked
    ? Array.from(compareModelPicker.querySelectorAll("input:checked")).map((el) => el.value)
    : [];

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        conversation_id: currentConversationId,
        mode: modeSelect.value,
        message,
        document_ids: Array.from(selectedDocumentIds),
        compare_models: compareModels,
      }),
    });
    const data = await res.json();
    thinkingEl.remove();
    if (data.error) {
      appendMessage("assistant", `Error: ${data.error}`);
    } else if (data.compare) {
      appendCompareResult(data.compare);
    } else {
      appendMessage("assistant", data.reply, data.sources);
    }
  } catch (err) {
    thinkingEl.remove();
    appendMessage("assistant", `Gagal terhubung ke server: ${err}`);
  }
}

async function loadSnippets() {
  const res = await fetch("/api/security/snippets");
  const snippets = await res.json();
  snippetList.innerHTML = "";
  snippets.forEach((s) => {
    const btn = document.createElement("button");
    btn.className = "snippet-btn";
    btn.textContent = s.label;
    btn.addEventListener("click", async () => {
      const r = await fetch(`/api/security/snippets/${s.id}`);
      const detail = await r.json();
      appendMessage("assistant", `${detail.label}\n\n${detail.code}`);
    });
    snippetList.appendChild(btn);
  });
}

async function uploadDocument() {
  const file = docUploadInput.files[0];
  if (!file) { alert("Pilih file dulu."); return; }

  const formData = new FormData();
  formData.append("file", file);
  formData.append("as_knowledge_base", docAsKb.checked ? "true" : "false");

  docUploadBtn.disabled = true;
  docUploadBtn.textContent = "Mengunggah...";
  try {
    const res = await fetch("/api/documents", { method: "POST", body: formData });
    const data = await res.json();
    if (data.error) alert(data.error);
    else { docUploadInput.value = ""; await loadDocuments(); }
  } catch (err) {
    alert(`Gagal mengunggah: ${err}`);
  } finally {
    docUploadBtn.disabled = false;
    docUploadBtn.textContent = "Unggah Dokumen";
  }
}

async function loadDocuments() {
  const res = await fetch("/api/documents");
  const docs = await res.json();
  docList.innerHTML = "";
  docs.forEach((d) => {
    const item = document.createElement("div");
    item.className = "doc-item";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = selectedDocumentIds.has(d.id);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) selectedDocumentIds.add(d.id); else selectedDocumentIds.delete(d.id);
    });
    const label = document.createElement("div");
    label.style.flex = "1";
    const kbTag = d.is_knowledge_base ? " [KB]" : "";
    label.innerHTML = `${d.filename}${kbTag}<span class="doc-meta">${d.filetype.toUpperCase()}</span>`;
    const delBtn = document.createElement("button");
    delBtn.className = "doc-delete";
    delBtn.textContent = "✕";
    delBtn.addEventListener("click", async () => {
      await fetch(`/api/documents/${d.id}`, { method: "DELETE" });
      selectedDocumentIds.delete(d.id);
      await loadDocuments();
    });
    item.appendChild(checkbox);
    item.appendChild(label);
    item.appendChild(delBtn);
    docList.appendChild(item);
  });
}

docUploadBtn.addEventListener("click", uploadDocument);
docSummarizeBtn.addEventListener("click", () => {
  if (selectedDocumentIds.size === 0) { alert("Pilih minimal satu dokumen."); return; }
  modeSelect.value = "document_analysis";
  sendMessage("Tolong ringkas isi dokumen ini secara jelas dan padat.");
});
docCompareBtn.addEventListener("click", () => {
  if (selectedDocumentIds.size < 2) { alert("Pilih minimal dua dokumen."); return; }
  modeSelect.value = "document_analysis";
  sendMessage("Tolong bandingkan dokumen-dokumen ini: apa persamaan dan perbedaan utamanya?");
});

sendBtn.addEventListener("click", () => sendMessage());
chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});
newChatBtn.addEventListener("click", createConversation);

compareToggle.addEventListener("change", () => {
  compareModelPicker.classList.toggle("hidden", !compareToggle.checked);
});

async function loadModelsForCompare() {
  const res = await fetch("/api/models");
  availableModels = await res.json();
  compareModelPicker.innerHTML = "";
  availableModels.forEach((m) => {
    const label = document.createElement("label");
    label.className = "checkbox-row";
    label.innerHTML = `<input type="checkbox" value="${m.id}"> ${m.label}`;
    compareModelPicker.appendChild(label);
  });

  // isi juga dropdown Model Manager di tab Settings
  const settingSelect = document.getElementById("setting-active-model");
  if (settingSelect && settingSelect.options.length === 0) {
    availableModels.forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m.id; opt.textContent = m.label;
      settingSelect.appendChild(opt);
    });
  }
}

// ============================================================
// CODE WORKSPACE
// ============================================================
const projectList = document.getElementById("project-list");
const fileList = document.getElementById("file-list");
const codeEditor = document.getElementById("code-editor");
const currentFileLabel = document.getElementById("current-file-label");

async function loadProjects() {
  const res = await fetch("/api/workspace/projects");
  const projects = await res.json();
  projectList.innerHTML = "";
  projects.forEach((p) => {
    const item = document.createElement("div");
    item.className = "project-item" + (p === currentProject ? " active" : "");
    item.innerHTML = `<span>${p}</span>`;
    item.addEventListener("click", () => selectProject(p));
    const del = document.createElement("button");
    del.className = "del-btn"; del.textContent = "✕";
    del.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!confirm(`Hapus proyek '${p}' beserta semua filenya?`)) return;
      await fetch(`/api/workspace/projects/${p}`, { method: "DELETE" });
      if (currentProject === p) { currentProject = null; fileList.innerHTML = ""; codeEditor.value = ""; }
      loadProjects();
    });
    item.appendChild(del);
    projectList.appendChild(item);
  });
}

async function selectProject(p) {
  currentProject = p;
  currentFile = null;
  codeEditor.value = "";
  currentFileLabel.textContent = "Belum ada file dipilih";
  await loadProjects();
  await loadFiles();
}

async function loadFiles() {
  if (!currentProject) return;
  const res = await fetch(`/api/workspace/projects/${currentProject}/files`);
  const files = await res.json();
  fileList.innerHTML = "";
  files.forEach((f) => {
    const item = document.createElement("div");
    item.className = "file-item" + (f === currentFile ? " active" : "");
    item.innerHTML = `<span>${f}</span>`;
    item.addEventListener("click", () => openFile(f));
    const del = document.createElement("button");
    del.className = "del-btn"; del.textContent = "✕";
    del.addEventListener("click", async (e) => {
      e.stopPropagation();
      await fetch(`/api/workspace/projects/${currentProject}/files/${f}`, { method: "DELETE" });
      if (currentFile === f) { currentFile = null; codeEditor.value = ""; currentFileLabel.textContent = "Belum ada file dipilih"; }
      loadFiles();
    });
    item.appendChild(del);
    fileList.appendChild(item);
  });
}

async function openFile(f) {
  currentFile = f;
  currentFileLabel.textContent = `${currentProject}/${f}`;
  const res = await fetch(`/api/workspace/projects/${currentProject}/files/${f}`);
  const data = await res.json();
  codeEditor.value = data.content || "";
  loadFiles();
}

document.getElementById("create-project-btn").addEventListener("click", async () => {
  const name = document.getElementById("new-project-name").value.trim();
  if (!name) return;
  const res = await fetch("/api/workspace/projects", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }),
  });
  const data = await res.json();
  if (data.error) { alert(data.error); return; }
  document.getElementById("new-project-name").value = "";
  await selectProject(name);
});

document.getElementById("create-file-btn").addEventListener("click", async () => {
  if (!currentProject) { alert("Pilih/buat proyek dulu."); return; }
  const path = document.getElementById("new-file-path").value.trim();
  if (!path) return;
  await fetch(`/api/workspace/projects/${currentProject}/files/${path}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ content: "" }),
  });
  document.getElementById("new-file-path").value = "";
  await openFile(path);
});

document.getElementById("save-file-btn").addEventListener("click", async () => {
  if (!currentProject || !currentFile) { alert("Pilih file dulu."); return; }
  await fetch(`/api/workspace/projects/${currentProject}/files/${currentFile}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ content: codeEditor.value }),
  });
});

document.getElementById("delete-file-btn").addEventListener("click", async () => {
  if (!currentProject || !currentFile) return;
  await fetch(`/api/workspace/projects/${currentProject}/files/${currentFile}`, { method: "DELETE" });
  currentFile = null; codeEditor.value = ""; currentFileLabel.textContent = "Belum ada file dipilih";
  loadFiles();
});

document.getElementById("download-project-btn").addEventListener("click", () => {
  if (!currentProject) { alert("Pilih proyek dulu."); return; }
  window.open(`/api/workspace/projects/${currentProject}/download`, "_blank");
});

// ============================================================
// SKILL MANAGER
// ============================================================
async function loadSkills() {
  const res = await fetch("/api/skills");
  const skills = await res.json();
  const list = document.getElementById("skill-manager-list");
  list.innerHTML = "";
  skills.forEach((s) => {
    const item = document.createElement("div");
    item.className = "manager-item";
    item.innerHTML = `<div class="mi-main"><div class="mi-name">${s.name}</div><div class="mi-desc">${s.description}</div></div>`;
    const toggleBtn = document.createElement("button");
    toggleBtn.textContent = s.enabled ? "Nonaktifkan" : "Aktifkan";
    toggleBtn.addEventListener("click", async () => {
      await fetch(`/api/skills/${s.id}/toggle`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled: !s.enabled }),
      });
      loadSkills();
    });
    const delBtn = document.createElement("button");
    delBtn.className = "mi-delete"; delBtn.textContent = "Hapus";
    delBtn.addEventListener("click", async () => {
      if (!confirm(`Hapus skill '${s.name}'?`)) return;
      await fetch(`/api/skills/${s.id}`, { method: "DELETE" });
      loadSkills();
    });
    item.appendChild(toggleBtn);
    item.appendChild(delBtn);
    list.appendChild(item);
  });
}

document.getElementById("import-skill-github-btn").addEventListener("click", async () => {
  const url = document.getElementById("skill-github-url").value.trim();
  if (!url) return;
  const res = await fetch("/api/skills/import/github", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url }),
  });
  const data = await res.json();
  if (data.error) alert(data.error); else { document.getElementById("skill-github-url").value = ""; loadSkills(); }
});

document.getElementById("import-skill-zip-btn").addEventListener("click", async () => {
  const file = document.getElementById("skill-zip-input").files[0];
  if (!file) { alert("Pilih file ZIP dulu."); return; }
  const formData = new FormData(); formData.append("file", file);
  const res = await fetch("/api/skills/import/zip", { method: "POST", body: formData });
  const data = await res.json();
  if (data.error) alert(data.error); else { document.getElementById("skill-zip-input").value = ""; loadSkills(); }
});

// ============================================================
// PLUGIN MANAGER
// ============================================================
async function loadPlugins() {
  const res = await fetch("/api/plugins");
  const plugins = await res.json();
  const list = document.getElementById("plugin-manager-list");
  list.innerHTML = "";
  plugins.forEach((p) => {
    const item = document.createElement("div");
    item.className = "manager-item";
    item.innerHTML = `<div class="mi-main"><div class="mi-name">${p.name} <span style="color:#8a8fa3;font-size:11px;">v${p.version}</span></div><div class="mi-desc">${p.description}</div></div>`;
    const toggleBtn = document.createElement("button");
    toggleBtn.textContent = p.enabled ? "Nonaktifkan" : "Aktifkan";
    toggleBtn.addEventListener("click", async () => {
      await fetch(`/api/plugins/${p.id}/toggle`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled: !p.enabled }),
      });
      loadPlugins();
    });
    const delBtn = document.createElement("button");
    delBtn.className = "mi-delete"; delBtn.textContent = "Hapus";
    delBtn.addEventListener("click", async () => {
      if (!confirm(`Hapus plugin '${p.name}'?`)) return;
      await fetch(`/api/plugins/${p.id}`, { method: "DELETE" });
      loadPlugins();
    });
    item.appendChild(toggleBtn);
    item.appendChild(delBtn);
    list.appendChild(item);
  });
}

document.getElementById("import-plugin-github-btn").addEventListener("click", async () => {
  const url = document.getElementById("plugin-github-url").value.trim();
  if (!url) return;
  const res = await fetch("/api/plugins/import/github", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url }),
  });
  const data = await res.json();
  if (data.error) alert(data.error); else { document.getElementById("plugin-github-url").value = ""; loadPlugins(); }
});

document.getElementById("import-plugin-zip-btn").addEventListener("click", async () => {
  const file = document.getElementById("plugin-zip-input").files[0];
  if (!file) { alert("Pilih file ZIP dulu."); return; }
  const formData = new FormData(); formData.append("file", file);
  const res = await fetch("/api/plugins/import/zip", { method: "POST", body: formData });
  const data = await res.json();
  if (data.error) alert(data.error); else { document.getElementById("plugin-zip-input").value = ""; loadPlugins(); }
});

// ============================================================
// AI MEMORY
// ============================================================
async function loadMemory() {
  const res = await fetch("/api/memory");
  const facts = await res.json();
  const list = document.getElementById("memory-list");
  list.innerHTML = "";
  facts.forEach((f) => {
    const item = document.createElement("div");
    item.className = "manager-item";
    item.innerHTML = `<div class="mi-main"><div class="mi-desc">${f.content}</div></div>`;
    const delBtn = document.createElement("button");
    delBtn.className = "mi-delete"; delBtn.textContent = "Hapus";
    delBtn.addEventListener("click", async () => {
      await fetch(`/api/memory/${f.id}`, { method: "DELETE" });
      loadMemory();
    });
    item.appendChild(delBtn);
    list.appendChild(item);
  });
}

document.getElementById("add-memory-btn").addEventListener("click", async () => {
  const input = document.getElementById("new-memory-input");
  const content = input.value.trim();
  if (!content) return;
  await fetch("/api/memory", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ content }),
  });
  input.value = "";
  loadMemory();
});

document.getElementById("clear-memory-btn").addEventListener("click", async () => {
  if (!confirm("Hapus semua memory?")) return;
  await fetch("/api/memory/clear", { method: "POST" });
  loadMemory();
});

// ============================================================
// AI AGENT
// ============================================================
function renderAgentPlan(taskId, plan) {
  const list = document.getElementById("agent-plan-list");
  list.innerHTML = "";
  plan.forEach((step, idx) => {
    const div = document.createElement("div");
    div.className = "agent-step";
    div.innerHTML = `
      <div class="step-title">Langkah ${step.step}: ${step.tool}</div>
      <div class="step-desc">${step.description}</div>
      <div class="step-status ${step.status}">${step.status}</div>
      ${step.result ? `<div class="step-result">${step.result}</div>` : ""}
    `;
    if (step.status === "pending") {
      const actions = document.createElement("div");
      actions.className = "step-actions";
      const approveBtn = document.createElement("button");
      approveBtn.textContent = step.tool === "note" ? "Lanjut" : "Setujui & Jalankan";
      approveBtn.addEventListener("click", async () => {
        const res = await fetch(`/api/agent/tasks/${taskId}/steps/${idx}/approve`, { method: "POST" });
        const data = await res.json();
        const task = await (await fetch(`/api/agent/tasks/${taskId}`)).json();
        renderAgentPlan(taskId, task.plan);
      });
      const skipBtn = document.createElement("button");
      skipBtn.className = "skip-btn"; skipBtn.textContent = "Lewati";
      skipBtn.addEventListener("click", async () => {
        await fetch(`/api/agent/tasks/${taskId}/steps/${idx}/skip`, { method: "POST" });
        const task = await (await fetch(`/api/agent/tasks/${taskId}`)).json();
        renderAgentPlan(taskId, task.plan);
      });
      actions.appendChild(approveBtn);
      actions.appendChild(skipBtn);
      div.appendChild(actions);
    }
    list.appendChild(div);
  });
}

document.getElementById("agent-plan-btn").addEventListener("click", async () => {
  const goal = document.getElementById("agent-goal-input").value.trim();
  if (!goal) return;
  const btn = document.getElementById("agent-plan-btn");
  btn.disabled = true; btn.textContent = "Membuat rencana...";
  try {
    const res = await fetch("/api/agent/plan", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ goal }),
    });
    const data = await res.json();
    if (data.error) { alert(data.error); return; }
    renderAgentPlan(data.task_id, data.plan);
  } finally {
    btn.disabled = false; btn.textContent = "Buat Rencana";
  }
});

// ============================================================
// SETTINGS
// ============================================================
async function loadSettings() {
  const res = await fetch("/api/settings");
  const s = await res.json();
  document.getElementById("setting-active-model").value = s.active_model;
  document.getElementById("setting-temperature").value = s.temperature;
  document.getElementById("temp-value").textContent = s.temperature;
  document.getElementById("setting-max-tokens").value = s.max_tokens;
  document.getElementById("setting-response-style").value = s.response_style;
  document.getElementById("setting-response-language").value = s.response_language;
  document.getElementById("setting-display-name").value = s.display_name;
  document.getElementById("setting-theme").value = s.theme;
}

document.getElementById("setting-temperature").addEventListener("input", (e) => {
  document.getElementById("temp-value").textContent = e.target.value;
});

document.getElementById("save-settings-btn").addEventListener("click", async () => {
  const payload = {
    active_model: document.getElementById("setting-active-model").value,
    temperature: document.getElementById("setting-temperature").value,
    max_tokens: document.getElementById("setting-max-tokens").value,
    response_style: document.getElementById("setting-response-style").value,
    response_language: document.getElementById("setting-response-language").value,
    display_name: document.getElementById("setting-display-name").value,
    theme: document.getElementById("setting-theme").value,
  };
  await fetch("/api/settings", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  });
  alert("Pengaturan disimpan.");
});

document.getElementById("clear-history-btn").addEventListener("click", async () => {
  if (!confirm("Hapus SEMUA riwayat percakapan? Tindakan ini tidak bisa dibatalkan.")) return;
  await fetch("/api/settings/clear-history", { method: "POST" });
  window.__conversations = [];
  conversationList.innerHTML = "";
  chatWindow.innerHTML = "";
  currentConversationId = null;
});

// ============================================================
// INIT
// ============================================================
window.__conversations = window.__initialConversations || [];
renderConversationList();
loadSnippets();
loadDocuments();
loadModelsForCompare();
loadProjects();
loadSkills();
loadPlugins();
loadMemory();
loadSettings();
