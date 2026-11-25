"""
Skill Manager — mengimpor "Skill" (SKILL.md) dari GitHub atau ZIP.
Semuanya diproses di memori (BytesIO) — tidak pernah ditulis ke disk lokal,
karena Vercel Functions tidak punya filesystem persisten. Hasil akhirnya
(nama, deskripsi, isi SKILL.md) langsung disimpan sebagai teks di Postgres.
"""

import io
import re
import zipfile

import requests


class SkillError(Exception):
    pass


def _parse_skill_md(content: str):
    name = None
    description = None
    fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if fm_match:
        fm = fm_match.group(1)
        name_match = re.search(r"^name:\s*(.+)$", fm, re.MULTILINE)
        desc_match = re.search(r"^description:\s*(.+)$", fm, re.MULTILINE)
        if name_match:
            name = name_match.group(1).strip().strip('"\'')
        if desc_match:
            description = desc_match.group(1).strip().strip('"\'')
    if not name:
        h_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        name = h_match.group(1).strip() if h_match else "Skill Tanpa Nama"
    if not description:
        description = "(Tidak ada deskripsi di SKILL.md)"
    return name, description


def _find_skill_md_members(zf: zipfile.ZipFile):
    """Cari semua anggota ZIP yang namanya SKILL.md (bisa beberapa skill per repo)."""
    return [m for m in zf.namelist() if m.upper().rstrip("/").endswith("SKILL.MD")]


def _validate_content(content: str):
    if len(content.strip()) < 10:
        return False, "SKILL.md kosong atau terlalu pendek"
    return True, "Valid"


def _import_from_zip_bytes(zip_bytes, source):
    from . import database

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        raise SkillError("File ZIP tidak valid.")

    members = _find_skill_md_members(zf)
    if not members:
        raise SkillError("Tidak ditemukan file SKILL.md di dalam repository/ZIP ini.")

    imported = []
    for member in members:
        try:
            content = zf.read(member).decode("utf-8", errors="ignore")
        except (KeyError, zipfile.BadZipFile):
            continue

        is_valid, message = _validate_content(content)
        if not is_valid:
            continue

        name, description = _parse_skill_md(content)
        skill_id = database.add_skill(name=name, description=description, source=source, skill_md=content)
        imported.append({"id": skill_id, "name": name, "description": description})

    if not imported:
        raise SkillError("SKILL.md ditemukan tapi tidak ada yang valid.")

    return imported


def import_from_zip(file_storage):
    """file_storage: objek file Flask (request.files['file'])."""
    data = file_storage.read()
    return _import_from_zip_bytes(data, source="zip")


def import_from_github(github_url: str):
    """Mendukung URL repo biasa, mis. https://github.com/user/repo."""
    match = re.match(r"https?://github\.com/([^/]+)/([^/]+?)(\.git)?/?$", github_url.strip())
    if not match:
        raise SkillError("URL GitHub tidak valid. Gunakan format https://github.com/user/repo")

    owner, repo = match.group(1), match.group(2)
    last_error = None

    for branch in ["main", "master"]:
        zip_url = f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{branch}"
        try:
            resp = requests.get(zip_url, timeout=30)
            if resp.status_code == 200:
                return _import_from_zip_bytes(resp.content, source=github_url)
            last_error = f"HTTP {resp.status_code}"
        except requests.exceptions.RequestException as e:
            last_error = str(e)

    raise SkillError(f"Gagal mengunduh repository dari GitHub ({last_error}).")
