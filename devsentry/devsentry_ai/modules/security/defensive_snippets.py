"""
Kumpulan snippet kode defensif siap-tempel yang bisa dipanggil langsung
dari UI tanpa harus memanggil AI (lebih cepat & konsisten untuk kebutuhan umum).
"""

SNIPPETS = {
    "password_hashing": {
        "label": "Hashing Password (Werkzeug/argon2)",
        "code": '''from werkzeug.security import generate_password_hash, check_password_hash

# Saat registrasi:
hashed = generate_password_hash(password_plaintext, method="scrypt")
# simpan `hashed` ke database, JANGAN simpan password asli

# Saat login:
if check_password_hash(hashed, password_input):
    print("Password cocok")
''',
    },
    "sql_parameterized": {
        "label": "Query Terparameter (anti SQL Injection)",
        "code": '''import sqlite3

conn = sqlite3.connect("app.db")
cur = conn.cursor()

# AMAN: gunakan placeholder "?", jangan f-string/format string untuk query
cur.execute("SELECT * FROM users WHERE username = ? AND status = ?", (username, "active"))
row = cur.fetchone()
''',
    },
    "input_validation": {
        "label": "Validasi & Sanitasi Input (Flask)",
        "code": '''from markupsafe import escape
import re

def validate_username(username: str) -> bool:
    return bool(re.fullmatch(r"[a-zA-Z0-9_]{3,20}", username))

@app.route("/profile")
def profile():
    name = request.args.get("name", "")
    safe_name = escape(name)  # mencegah XSS saat ditampilkan di template
    return render_template("profile.html", name=safe_name)
''',
    },
    "csrf_protection": {
        "label": "Proteksi CSRF (Flask-WTF)",
        "code": '''from flask_wtf import CSRFProtect

app = Flask(__name__)
app.config["SECRET_KEY"] = "ganti-dengan-random-string"
csrf = CSRFProtect(app)

# Di template:
# <form method="POST">
#   {{ csrf_token() }}
#   ...
# </form>
''',
    },
    "rate_limiting": {
        "label": "Rate Limiting (Flask-Limiter)",
        "code": '''from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(get_remote_address, app=app, default_limits=["200 per day", "50 per hour"])

@app.route("/login", methods=["POST"])
@limiter.limit("5 per minute")
def login():
    ...
''',
    },
    "secure_headers": {
        "label": "Secure HTTP Headers",
        "code": '''@app.after_request
def set_secure_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response
''',
    },
    "env_secrets": {
        "label": "Memuat Secret dari .env (jangan hardcode)",
        "code": '''# .env (JANGAN commit file ini ke git — tambahkan ke .gitignore)
# SECRET_KEY=isi-random-panjang
# DATABASE_URL=sqlite:///app.db

# app.py
from dotenv import load_dotenv
import os

load_dotenv()
SECRET_KEY = os.environ["SECRET_KEY"]
''',
    },
}


def list_snippets():
    return [{"id": k, "label": v["label"]} for k, v in SNIPPETS.items()]


def get_snippet(snippet_id):
    return SNIPPETS.get(snippet_id)
