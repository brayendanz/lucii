"""
LAB EDUKATIF KERENTANAN WEB — UNTUK PEMILIK SITUS SAJA.

Modul ini mendemonstrasikan pola kerentanan web klasik (mirip pendekatan
DVWA / OWASP WebGoat) menggunakan database in-memory milik lab ini sendiri.
Setiap kerentanan didampingi versi yang sudah diperbaiki + penjelasan.

ATURAN (versi hosting online):
- Blueprint ini HANYA didaftarkan jika config.SECURITY_LAB_ENABLED = True
  (otomatis aktif hanya jika LAB_ACCESS_CODE di-set di environment variable).
- Setiap request ke /lab/* WAJIB melewati gerbang kode akses (lihat
  before_request di app.py) sebelum bisa menyentuh route di file ini.
  Ini penting karena situs ini publik: tanpa kunci ini, endpoint XSS/SQLi
  rentan bisa disalahgunakan orang lain sebagai alat menyerang pihak ketiga
  (mis. mengirim link berisi payload ke korban).
- Tidak ada fungsi di sini yang menjangkau jaringan luar atau sistem lain.
- Jangan bagikan LAB_ACCESS_CODE ke orang lain.
"""

import sqlite3
from flask import Blueprint, request, render_template_string, jsonify

vuln_lab_bp = Blueprint("vuln_lab", __name__, url_prefix="/lab")

# --- Database in-memory khusus lab, terpisah dari database utama aplikasi ---
_lab_db = sqlite3.connect(":memory:", check_same_thread=False)
_lab_db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, password TEXT)")
_lab_db.executemany(
    "INSERT INTO users (username, password) VALUES (?, ?)",
    [("admin", "lab_password_123"), ("guest", "guest123")],
)
_lab_db.commit()


LAB_INDEX = """
<h2>Lab Kerentanan Web (Edukatif, Localhost-only)</h2>
<ul>
  <li><a href="/lab/sqli">1. SQL Injection — rentan vs aman</a></li>
  <li><a href="/lab/xss">2. Cross-Site Scripting (XSS) — rentan vs aman</a></li>
</ul>
<p>Setiap halaman menampilkan dua versi kode: yang rentan (untuk dipelajari polanya)
dan yang sudah diperbaiki. Jangan pernah menyalin versi rentan ke aplikasi produksi.</p>
"""


@vuln_lab_bp.route("/")
def lab_index():
    return LAB_INDEX


# =========================================================
# 1. SQL INJECTION DEMO
# =========================================================

SQLI_PAGE = """
<h2>Demo SQL Injection</h2>
<form method="get">
  Username: <input name="username" value="{{ username }}">
  <button type="submit" formaction="/lab/sqli/vulnerable">Coba versi RENTAN</button>
  <button type="submit" formaction="/lab/sqli/secure">Coba versi AMAN</button>
</form>

<p>Contoh payload untuk dicoba di versi rentan: <code>' OR '1'='1</code></p>

<h3>Hasil</h3>
<pre>{{ result }}</pre>

<h3>Kode versi RENTAN (JANGAN dipakai di produksi)</h3>
<pre>
query = f"SELECT id, username FROM users WHERE username = '{{'{'}}username{{'}'}}'"
cursor.execute(query)
</pre>

<h3>Kode versi AMAN</h3>
<pre>
cursor.execute("SELECT id, username FROM users WHERE username = ?", (username,))
</pre>

<p>{{ explanation }}</p>
"""


@vuln_lab_bp.route("/sqli")
def sqli_page():
    return render_template_string(SQLI_PAGE, username="", result="", explanation="")


@vuln_lab_bp.route("/sqli/vulnerable")
def sqli_vulnerable():
    username = request.args.get("username", "")
    # SENGAJA RENTAN untuk tujuan demonstrasi — string concatenation langsung ke query
    try:
        query = f"SELECT id, username FROM users WHERE username = '{username}'"
        cur = _lab_db.execute(query)
        rows = cur.fetchall()
        result = f"Query dijalankan: {query}\nHasil: {rows}"
    except sqlite3.Error as e:
        result = f"Query error: {e}"
    explanation = (
        "Perhatikan: input digabung langsung ke query. Payload seperti "
        "\"' OR '1'='1\" bisa mengubah logika query dan membocorkan seluruh "
        "baris tabel. Ini contoh kelas kerentanan CWE-89 (SQL Injection)."
    )
    return render_template_string(SQLI_PAGE, username=username, result=result, explanation=explanation)


@vuln_lab_bp.route("/sqli/secure")
def sqli_secure():
    username = request.args.get("username", "")
    # AMAN — parameterized query, input tidak pernah jadi bagian dari struktur SQL
    cur = _lab_db.execute("SELECT id, username FROM users WHERE username = ?", (username,))
    rows = cur.fetchall()
    result = f"Hasil (parameterized): {rows}"
    explanation = (
        "Dengan parameterized query, payload seperti \"' OR '1'='1\" hanya "
        "diperlakukan sebagai teks biasa, bukan bagian dari perintah SQL — "
        "serangan yang sama tidak akan berhasil."
    )
    return render_template_string(SQLI_PAGE, username=username, result=result, explanation=explanation)


# =========================================================
# 2. XSS DEMO
# =========================================================

XSS_PAGE = """
<h2>Demo Cross-Site Scripting (XSS)</h2>
<form method="get">
  Komentar: <input name="comment" value="{{ raw_comment }}">
  <button type="submit" formaction="/lab/xss/vulnerable">Kirim ke versi RENTAN</button>
  <button type="submit" formaction="/lab/xss/secure">Kirim ke versi AMAN</button>
</form>

<p>Contoh payload untuk dicoba: <code>&lt;script&gt;alert('xss')&lt;/script&gt;</code></p>

<h3>Output halaman</h3>
<div style="border:1px solid #ccc; padding:8px;">{{ rendered|safe }}</div>

<h3>Kode versi RENTAN</h3>
<pre>return f"&lt;div&gt;{comment}&lt;/div&gt;"   # comment dirender apa adanya</pre>

<h3>Kode versi AMAN</h3>
<pre>from markupsafe import escape
return f"&lt;div&gt;{escape(comment)}&lt;/div&gt;"   # karakter HTML di-escape</pre>

<p>{{ explanation }}</p>
"""


@vuln_lab_bp.route("/xss")
def xss_page():
    return render_template_string(XSS_PAGE, raw_comment="", rendered="", explanation="")


@vuln_lab_bp.route("/xss/vulnerable")
def xss_vulnerable():
    comment = request.args.get("comment", "")
    # SENGAJA RENTAN — output comment tanpa escaping
    rendered = f"<div>{comment}</div>"
    explanation = (
        "Komentar dirender langsung sebagai HTML. Jika pengguna memasukkan "
        "tag &lt;script&gt;, browser akan mengeksekusinya. Ini CWE-79 (XSS)."
    )
    return render_template_string(XSS_PAGE, raw_comment=comment, rendered=rendered, explanation=explanation)


@vuln_lab_bp.route("/xss/secure")
def xss_secure():
    from markupsafe import escape
    comment = request.args.get("comment", "")
    rendered = f"<div>{escape(comment)}</div>"
    explanation = (
        "Dengan escape(), karakter seperti &lt; dan &gt; diubah menjadi entitas "
        "HTML (&amp;lt; dst) sehingga browser menampilkannya sebagai teks biasa, "
        "bukan menjalankannya sebagai kode."
    )
    return render_template_string(XSS_PAGE, raw_comment=comment, rendered=rendered, explanation=explanation)
