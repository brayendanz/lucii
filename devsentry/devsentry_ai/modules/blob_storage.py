"""
Wrapper tipis di atas SDK resmi Vercel Blob (paket `vercel-blob` di PyPI),
dipakai untuk menyimpan isi file Code Workspace. Vercel Functions tidak
punya filesystem persisten, jadi file project/kode disimpan di sini,
bukan di disk lokal.
"""

import requests
import config


class BlobError(Exception):
    pass


def _check_token():
    if not config.BLOB_READ_WRITE_TOKEN:
        raise BlobError(
            "BLOB_READ_WRITE_TOKEN belum diset. Tambahkan di Environment Variables "
            "Vercel (dibuat otomatis saat kamu membuat Blob Store di dashboard Vercel)."
        )


def upload(pathname: str, content: bytes) -> str:
    """Upload/replace isi file, mengembalikan URL publik blob tersebut."""
    _check_token()
    try:
        from vercel.blob import sync as blob
    except ImportError:
        raise BlobError("Package 'vercel-blob' belum terinstall di server.")

    result = blob.put_blob(pathname, content, access="public", allow_overwrite=True)
    return result.url


def read_text(blob_url: str) -> str:
    """Ambil isi file (sebagai teks) dari URL blob publik."""
    try:
        resp = requests.get(blob_url, timeout=30)
        resp.raise_for_status()
        return resp.text
    except requests.exceptions.RequestException as e:
        raise BlobError(f"Gagal membaca file dari Blob: {e}")


def read_bytes(blob_url: str) -> bytes:
    try:
        resp = requests.get(blob_url, timeout=30)
        resp.raise_for_status()
        return resp.content
    except requests.exceptions.RequestException as e:
        raise BlobError(f"Gagal membaca file dari Blob: {e}")


def delete(blob_url: str):
    _check_token()
    try:
        from vercel.blob import sync as blob
        blob.delete_blob(blob_url)
    except ImportError:
        raise BlobError("Package 'vercel-blob' belum terinstall di server.")
    except Exception:
        # Kalau blob sudah tidak ada / URL tidak valid, abaikan saja —
        # tujuannya memang menghapus, jadi hasil akhir yang diinginkan tetap tercapai.
        pass
