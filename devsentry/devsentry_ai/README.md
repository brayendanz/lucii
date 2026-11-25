# DevSentry AI

Asisten coding & AI assistant lengkap — berjalan sebagai website serverless
di **Vercel**, ditenagai Anthropic API (Claude). Dirancang khusus supaya
bisa dideploy **100% tanpa kartu kredit**:

| Komponen | Layanan | Kartu kredit? |
|---|---|---|
| Hosting aplikasi | Vercel (Hobby plan) | Tidak perlu |
| Database | Neon Postgres (free tier) | Tidak perlu |
| Penyimpanan file (Code Workspace) | Vercel Blob | Tidak perlu |
| AI engine | Anthropic API | Perlu billing aktif di akun Anthropic (bayar sesuai pemakaian token) |

## Cara Deploy (semua lewat browser, tanpa terminal)

### 1. Buat database di Neon

1. Buka https://neon.tech → daftar (bisa pakai akun GitHub, tanpa kartu).
2. Buat project baru. Neon otomatis kasih **connection string** Postgres.
3. Salin connection string itu (bentuknya `postgresql://user:pass@ep-xxxx.../dbname?sslmode=require`) — nanti dipakai sebagai `DATABASE_URL`.

### 2. Upload project ke GitHub

1. Daftar di github.com (gratis, tanpa kartu).
2. Buat repository baru, upload semua isi folder `devsentry_ai` (drag-and-drop lewat halaman web repo).

### 3. Deploy ke Vercel

1. Buka https://vercel.com → daftar pakai akun GitHub-mu (tanpa kartu).
2. "Add New..." → "Project" → pilih repository yang baru kamu upload.
3. Di bagian **Environment Variables**, tambahkan:
   - `ANTHROPIC_API_KEY` — dari https://console.anthropic.com
   - `DATABASE_URL` — connection string Neon dari langkah 1
   - `SECRET_KEY` — string acak bebas
   - (opsional) `LAB_ACCESS_CODE`, `ADMIN_ACCESS_CODE`, `SKILLS_PLUGINS_PUBLIC`
4. Klik **Deploy**.

### 4. Tambahkan Vercel Blob (untuk Code Workspace)

1. Di dashboard project Vercel-mu → tab **Storage** → **Create Database** → pilih **Blob**.
2. Beri nama, buat. Vercel otomatis menambahkan env var `BLOB_READ_WRITE_TOKEN` ke project-mu.
3. Redeploy project (Vercel biasanya menawarkan ini otomatis setelah storage ditambahkan).

Setelah ini selesai, project akan punya URL publik seperti `https://devsentry-ai.vercel.app` — bisa langsung dibuka, tanpa instalasi apa pun di komputermu.

## Status Fitur vs Roadmap

| # | Fitur | Status |
|---|---|---|
| 1-3 | AI Chat, Context, Conversation History (buat/buka/ganti judul/hapus) | Selesai |
| 4-8 | Code Generation/Explanation/Debugging/Language Detection, **Code Workspace** (editor + file manager, disimpan di Vercel Blob) | Selesai |
| 9-11 | Document Upload/Reader/Analysis (PDF/DOCX/TXT/CSV/JSON) | Selesai |
| 12-15 | **Skill Manager** (import GitHub/ZIP, AI menerapkan skill relevan) | Selesai |
| 16-19 | **Plugin Manager** (import GitHub/ZIP) | Selesai — versi deklaratif, lihat catatan keamanan |
| 20 | **AI Memory** | Selesai |
| 21-22 | **Knowledge Base & RAG** | Selesai — retrieval keyword/TF-IDF ringan |
| 23 | **Model Manager** | Selesai |
| 24-25 | **AI Settings & User Settings** | Selesai |
| 26 | **Multi-Model Intelligence** | Selesai |
| 27 | **AI Agent** | Selesai — tools terbatas + approval |
| 28 | AI Model Training | Di luar scope (butuh infrastruktur GPU terpisah) |

## Kenapa Arsitekturnya Begini (Postgres + Blob, bukan SQLite + disk)

Vercel menjalankan kode sebagai **serverless functions** — tidak ada server
yang terus menyala dengan filesystem permanen seperti di Render/VPS biasa.
Setiap request bisa dijalankan di instance yang "bersih", jadi:
- **SQLite tidak bisa dipakai** (filenya akan hilang kapan saja) → diganti **Neon Postgres**.
- **File Code Workspace tidak bisa disimpan di disk lokal** → diganti **Vercel Blob**.
- Dokumen yang diupload (Document Analysis) dan Skill/Plugin yang diimpor **tidak perlu disimpan sebagai file terpisah** — isinya (teks SKILL.md, manifest plugin, hasil ekstraksi dokumen) langsung disimpan sebagai teks di Postgres, jadi tidak perlu Blob untuk ini.

## Catatan Keamanan Penting: Plugin Manager

Plugin **tidak menjalankan kode bebas di server** — plugin.json hanya berisi
metadata + `instructions` (teks instruksi tambahan untuk AI), bukan kode yang
dieksekusi. Ini sengaja: mengizinkan sembarang orang mengunggah "plugin"
berisi kode untuk dieksekusi di server akan membuka celah Remote Code
Execution (RCE) — siapa saja di internet bisa menjalankan kode di server-mu.

**Default**: Skill & Plugin Manager hanya bisa dikelola admin (`ADMIN_ACCESS_CODE`,
login di `/admin/login`). Set `SKILLS_PLUGINS_PUBLIC=true` untuk membuka ke
semua pengunjung — tapi pahami risikonya: siapa pun bisa menambah instruksi
ke AI-mu (potensi prompt injection ke pengunjung lain).

## Environment Variables

Lihat `.env.example` untuk daftar lengkap. Wajib: `ANTHROPIC_API_KEY`,
`DATABASE_URL`, `BLOB_READ_WRITE_TOKEN` (otomatis terisi setelah langkah 4 di atas).

## Struktur Folder

```
devsentry_ai/
├── api/
│   └── index.py              # Entry point Vercel Functions (menjembatani ke app.py)
├── app.py                     # Aplikasi Flask + semua route API
├── config.py                  # Konfigurasi (dari environment variables)
├── vercel.json                 # Routing Vercel
├── requirements.txt
├── .env.example
├── modules/
│   ├── ai_client.py            # Komunikasi dengan Anthropic API (+ multi-model)
│   ├── personas.py             # System prompt per mode
│   ├── database.py             # Semua tabel di Neon Postgres (psycopg3)
│   ├── blob_storage.py          # Wrapper Vercel Blob (untuk Code Workspace)
│   ├── documents.py             # Ekstraksi teks PDF/DOCX/TXT/CSV/JSON (dari bytes)
│   ├── code_workspace.py        # File manager multi-proyek (Postgres + Blob)
│   ├── skill_manager.py         # Import & validasi Skill (SKILL.md), full in-memory
│   ├── plugin_manager.py        # Import & validasi Plugin (plugin.json), deklaratif
│   ├── knowledge_base.py        # Chunking + retrieval RAG ringan
│   ├── memory.py                # AI Memory (fakta lintas sesi)
│   ├── context_builder.py       # Menggabungkan Skill+Plugin+Memory+RAG ke system prompt
│   ├── agent.py                 # AI Agent: planning + approval-gated execution
│   └── security/
│       ├── defensive_snippets.py
│       └── vuln_lab.py
├── templates/index.html
├── static/css/style.css
└── static/js/app.js
```

## Keamanan Bawaan (ringkasan)

- API key & connection string tidak pernah hardcode — selalu dari environment variable.
- Path traversal diblokir di semua fitur file (Code Workspace, Skill/Plugin ZIP extraction).
- Lab kerentanan & Skill/Plugin Manager dikunci kode akses secara default.
- Plugin bersifat deklaratif — tidak ada eksekusi kode pihak ketiga di server.
- AI Agent hanya punya akses ke tools yang eksplisit didefinisikan, dan tindakan penting butuh approval.

## Batasan yang Perlu Diketahui

- **Vercel Hobby plan untuk penggunaan personal/non-komersial.** Untuk penggunaan komersial, perlu upgrade ke Pro (berbayar, perlu kartu).
- **Neon free tier**: batas penyimpanan sekitar 512 MB — cukup untuk ribuan percakapan/dokumen teks, tapi perlu dipantau untuk pemakaian berat.
- **Fungsi serverless punya batas waktu eksekusi** (beberapa menit) — untuk jawaban AI yang sangat panjang/lambat, bisa saja timeout; kurangi `max_tokens` di Settings kalau sering terjadi.
- Belum sempat diuji dengan koneksi Neon/Vercel Blob sungguhan (sandbox pengembangan ini tidak punya akses internet) — sudah diverifikasi lewat simulasi/stub yang meniru perilaku Postgres & Blob, tapi tetap perhatikan log di dashboard Vercel saat pertama kali deploy, siapa tahu ada penyesuaian kecil yang dibutuhkan (misal versi package).
