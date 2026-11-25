"""
Entry point untuk Vercel Python Functions.
Vercel mendeteksi objek WSGI bernama `app` di file dalam folder /api dan
menjalankannya sebagai serverless function. File ini hanya menjembatani
ke aplikasi Flask sesungguhnya yang ada di app.py (root proyek).
"""

import os
import sys

# Pastikan root proyek (satu level di atas folder api/) ada di sys.path,
# supaya "import config", "from modules import ..." di app.py bisa ditemukan.
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app import app  # noqa: E402
