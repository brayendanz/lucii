"""
Code Workspace — file manager untuk proyek multi-file.
Isi file disimpan di Vercel Blob; nama proyek & path file dicatat di Postgres
(tabel workspace_projects / workspace_files) supaya bisa di-list tanpa
bergantung pada fitur list-by-prefix Blob.
"""

import io
import zipfile

from . import database
from . import blob_storage


class WorkspaceError(Exception):
    pass


def _validate_name(name):
    if not name or "/" in name or "\\" in name or ".." in name:
        raise WorkspaceError("Nama proyek tidak valid.")


def _validate_rel_path(rel_path):
    parts = rel_path.replace("\\", "/").split("/")
    if ".." in parts or rel_path.startswith("/"):
        raise WorkspaceError("Path file tidak valid.")


def list_projects():
    return database.ws_list_projects()


def create_project(project_name):
    _validate_name(project_name)
    database.ws_create_project(project_name)
    return project_name


def delete_project(project_name):
    blob_urls = database.ws_delete_project(project_name)
    for url in blob_urls:
        blob_storage.delete(url)


def list_files(project_name):
    return database.ws_list_files(project_name)


def read_file(project_name, rel_path):
    _validate_rel_path(rel_path)
    blob_url = database.ws_get_file(project_name, rel_path)
    if not blob_url:
        raise WorkspaceError("File tidak ditemukan.")
    return blob_storage.read_text(blob_url)


def write_file(project_name, rel_path, content):
    _validate_rel_path(rel_path)
    size_mb = len(content.encode("utf-8")) / (1024 * 1024)
    import config
    if size_mb > config.MAX_WORKSPACE_FILE_SIZE_MB:
        raise WorkspaceError(f"File melebihi batas {config.MAX_WORKSPACE_FILE_SIZE_MB} MB.")

    database.ws_create_project(project_name)  # pastikan proyek tercatat
    pathname = f"projects/{project_name}/{rel_path}"
    blob_url = blob_storage.upload(pathname, content.encode("utf-8"))
    database.ws_upsert_file(project_name, rel_path, blob_url)


def delete_file(project_name, rel_path):
    blob_url = database.ws_delete_file(project_name, rel_path)
    if blob_url:
        blob_storage.delete(blob_url)


def zip_project_bytes(project_name):
    """Mengembalikan bytes ZIP berisi semua file proyek (dibuat in-memory)."""
    files = list_files(project_name)
    if not files:
        raise WorkspaceError("Proyek tidak ditemukan atau belum punya file.")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel_path in files:
            blob_url = database.ws_get_file(project_name, rel_path)
            if blob_url:
                content = blob_storage.read_bytes(blob_url)
                zf.writestr(rel_path, content)
    buf.seek(0)
    return buf.read()
