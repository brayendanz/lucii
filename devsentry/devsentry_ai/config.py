"""
Konfigurasi global DevSentry AI - versi Vercel (serverless, tanpa kartu kredit).

Semua penyimpanan data dipindah ke layanan eksternal karena Vercel Functions
tidak punya filesystem persisten:
- Database      -> Neon Postgres (DATABASE_URL)
- File Code Workspace -> Vercel Blob (BLOB_READ_WRITE_TOKEN)

Nilai sensitif selalu dari Environment Variables di dashboard Vercel,
JANGAN ditulis langsung di file ini.
"""

import os

# --- AI Provider (Anthropic API) ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")

# --- Flask ---
SECRET_KEY = os.environ.get("SECRET_KEY", "ganti-ini-lewat-env-var-di-vercel")
DEBUG = False

# --- Database: Neon Postgres (wajib diisi, tanpa kartu kredit) ---
# Contoh: postgresql://user:password@ep-xxxx.region.aws.neon.tech/dbname?sslmode=require
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# --- Vercel Blob: penyimpanan file untuk Code Workspace (wajib diisi) ---
BLOB_READ_WRITE_TOKEN = os.environ.get("BLOB_READ_WRITE_TOKEN", "")

# --- Document Analysis ---
MAX_UPLOAD_SIZE_MB = int(os.environ.get("MAX_UPLOAD_SIZE_MB", 10))
MAX_DOC_CHARS_FOR_AI = int(os.environ.get("MAX_DOC_CHARS_FOR_AI", 40000))

# --- Code Workspace ---
MAX_WORKSPACE_FILE_SIZE_MB = int(os.environ.get("MAX_WORKSPACE_FILE_SIZE_MB", 4))

# --- Skill & Plugin Manager ---
SKILLS_PLUGINS_PUBLIC = os.environ.get("SKILLS_PLUGINS_PUBLIC", "false").lower() == "true"
ADMIN_ACCESS_CODE = os.environ.get("ADMIN_ACCESS_CODE", "")

# --- Model Manager ---
AVAILABLE_MODELS = [
    {"id": "claude-haiku-4-5", "label": "Claude Haiku (cepat & hemat)"},
    {"id": "claude-sonnet-4-5", "label": "Claude Sonnet (seimbang, default)"},
    {"id": "claude-opus-4-1", "label": "Claude Opus (paling mendalam)"},
]

# --- Lab Keamanan (edukatif) ---
SECURITY_LAB_ENABLED = bool(os.environ.get("LAB_ACCESS_CODE", ""))
LAB_ACCESS_CODE = os.environ.get("LAB_ACCESS_CODE", "")
