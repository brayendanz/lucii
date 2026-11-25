"""
Plugin Manager — mengimpor plugin.json dari GitHub/ZIP, diproses full
di memori (tidak pernah ditulis ke disk lokal).

CATATAN KEAMANAN: Plugin BERSIFAT DEKLARATIF — hanya metadata + instruksi
tambahan untuk AI (field "instructions"), BUKAN kode yang dieksekusi di
server. Lihat README untuk penjelasan lengkap kenapa ini sengaja dibuat
begini pada situs yang publik.
"""

import io
import json
import re
import zipfile

import requests


class PluginError(Exception):
    pass


REQUIRED_FIELDS = ["name", "version", "description"]


def _find_manifest_members(zf: zipfile.ZipFile):
    return [m for m in zf.namelist() if m.lower().rstrip("/").endswith("plugin.json")]


def validate_manifest_content(content: str):
    try:
        manifest = json.loads(content)
    except json.JSONDecodeError as e:
        return False, f"plugin.json tidak valid: {e}", None

    missing = [f for f in REQUIRED_FIELDS if f not in manifest]
    if missing:
        return False, f"Field wajib hilang: {', '.join(missing)}", None

    if not isinstance(manifest.get("name"), str) or not manifest["name"].strip():
        return False, "Field 'name' tidak valid", None

    instructions = manifest.get("instructions", "")
    if not isinstance(instructions, str):
        return False, "Field 'instructions' harus berupa teks", None
    if len(instructions) > 8000:
        return False, "Field 'instructions' terlalu panjang (maks 8000 karakter)", None

    return True, "Valid", manifest


def _import_from_zip_bytes(zip_bytes, source):
    from . import database

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        raise PluginError("File ZIP tidak valid.")

    members = _find_manifest_members(zf)
    if not members:
        raise PluginError("Tidak ditemukan file plugin.json di dalam repository/ZIP ini.")

    imported = []
    for member in members:
        try:
            content = zf.read(member).decode("utf-8", errors="ignore")
        except (KeyError, zipfile.BadZipFile):
            continue

        is_valid, message, manifest = validate_manifest_content(content)
        if not is_valid:
            continue

        plugin_id = database.add_plugin(
            name=manifest["name"],
            version=manifest.get("version", "0.0.0"),
            description=manifest.get("description", ""),
            manifest_json=json.dumps(manifest, ensure_ascii=False),
        )
        imported.append({"id": plugin_id, "name": manifest["name"]})

    if not imported:
        raise PluginError("plugin.json ditemukan tapi tidak ada yang valid.")

    return imported


def import_from_zip(file_storage):
    data = file_storage.read()
    return _import_from_zip_bytes(data, source="zip")


def import_from_github(github_url: str):
    match = re.match(r"https?://github\.com/([^/]+)/([^/]+?)(\.git)?/?$", github_url.strip())
    if not match:
        raise PluginError("URL GitHub tidak valid. Gunakan format https://github.com/user/repo")

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

    raise PluginError(f"Gagal mengunduh repository dari GitHub ({last_error}).")
