"""Sharing a list of mods: what Export writes and what Import reads (docs/mod-list.md).

The file names each GameBanana mod (its id and file ids, never a path on this computer), which of its folders are ticked, and the
files left out of them. Everything here is plain data in, plain data out; the Api (mod_manager.py) does the downloading and ticking.
A file from another person is untrusted: parse_mod_list() checks every field before the Api uses any of it in a path.
"""
import json
import re

FORMAT = "mk8dx-mod-list"
VERSION = 1
NOT_INCLUDED = "Custom icons, voices and your notes are not included."

_RECORD_TYPES = ("Mod", "Sound")
_MAX_MODS = 2000
_MAX_UNITS = 500
_MAX_LEFT_OUT = 5000


def _norm(path):
    return str(path).replace("\\", "/").strip("/").lower()


def build_mod_list(gb_mods, ticked_keys, excluded, folder_of, app_version, now):
    """The document to write, for the ticked units `ticked_keys` (their keys are "<category>/<item>/<mod>[/<inner folders>]").

    gb_mods     the GameBanana records, {item: [record]} (gamebanana-mods.json)
    excluded    the files left out, {unit key: {normalized path: {"path", "reason", "kept_from"}}} (excluded-files.json)
    folder_of   function(file entry) -> the downloaded folder of that file as a key prefix ("characters/Birdo/Wii Remotes"), or None
    A ticked unit with no GameBanana record (added by hand, or a record that was cleared) goes to "not_shared" with the reason."""
    index = []        # (folder prefix, item, record, file entry) for every downloaded file
    for item, records in (gb_mods or {}).items():
        for record in records or []:
            for f in record.get("files", []):
                if f.get("download_status") != "downloaded" or not f.get("downloaded_to"):
                    continue
                folder = folder_of(f)
                if folder:
                    index.append((folder, item, record, f))
    index.sort(key=lambda row: -len(row[0]))              # (the deepest folder wins when one holds another)

    mods = {}
    not_shared = []
    for key in sorted(ticked_keys):
        low = _norm(key)
        hit = next((row for row in index if low == _norm(row[0]) or low.startswith(_norm(row[0]) + "/")), None)
        if hit is None:
            not_shared.append({"key": key, "reason": "Not downloaded through the app (added by hand), so there is no link to share."})
            continue
        folder, item, record, f = hit
        sub = key.replace("\\", "/").strip("/")[len(folder.strip("/")):].strip("/")
        entry = mods.setdefault((item, record["mod_id"], record.get("record_type", "Mod")), {
            "item": item, "category": key.replace("\\", "/").split("/")[0], "mod_id": record["mod_id"],
            "record_type": record.get("record_type", "Mod"), "name": record.get("name") or "", "author": record.get("author") or "",
            "url": record.get("profile_url") or "", "files": {}, "units": [],
        })
        entry["files"][f["file_id"]] = {"file_id": f["file_id"], "name": f.get("name") or ""}
        left_out = [{"path": e.get("path", n), "reason": e.get("reason", "manual"), "kept_from": e.get("kept_from")}
                    for n, e in sorted((excluded or {}).get(key, {}).items())]
        entry["units"].append({"file_id": f["file_id"], "sub": sub, "left_out": left_out})

    listed = []
    for entry in mods.values():
        entry["files"] = list(entry["files"].values())
        listed.append(entry)
    listed.sort(key=lambda m: (m["category"], m["item"].lower(), m["name"].lower()))
    return {
        "format": FORMAT, "version": VERSION, "app_version": app_version, "exported_at": now, "note": NOT_INCLUDED,
        "mods": listed, "not_shared": not_shared,
    }


def _text(value, limit=300):
    return isinstance(value, str) and 0 < len(value) <= limit and not re.search(r"[\x00-\x1f]", value)


def _clean_sub(sub):
    """An inner folder path from the file: "" or "a/b" - never absolute, never leaving the mod's folder."""
    if not isinstance(sub, str) or len(sub) > 500 or re.search(r"[\x00-\x1f:]", sub):
        return None
    parts = [p for p in sub.replace("\\", "/").split("/") if p]
    if any(p in (".", "..") for p in parts) or sub.startswith(("/", "\\")):
        return None
    return "/".join(parts)


def clean_entry(entry, categories):
    """One mod of a list, checked and rebuilt from only the fields the app uses: (entry, None), or (None, why it can't be used)."""
    if not isinstance(entry, dict):
        return None, "not a mod entry"
    item, category, record_type, mod_id = entry.get("item"), entry.get("category"), entry.get("record_type", "Mod"), entry.get("mod_id")
    if not _text(item, 200) or "/" in item or "\\" in item:
        return None, "its character, course or part name is missing or unusable"
    if category not in categories:
        return None, f"it is filed under an unknown category ({str(category)[:40]})"
    if record_type not in _RECORD_TYPES:
        return None, "its kind is unknown"
    if not isinstance(mod_id, int) or isinstance(mod_id, bool) or mod_id <= 0:
        return None, "its GameBanana id is missing"
    files = []
    for f in entry.get("files") or []:
        file_id = f.get("file_id") if isinstance(f, dict) else None
        if not isinstance(file_id, int) or isinstance(file_id, bool) or file_id <= 0:
            return None, "one of its file ids is unusable"
        files.append({"file_id": file_id, "name": f.get("name") if isinstance(f.get("name"), str) else ""})
    if not files:
        return None, "it lists no files"
    ids = {f["file_id"] for f in files}
    units = []
    for u in (entry.get("units") or [])[:_MAX_UNITS]:
        sub = _clean_sub(u.get("sub", "")) if isinstance(u, dict) else None
        if sub is None or u.get("file_id") not in ids:
            return None, "one of its ticked folders is unusable"
        left_out = []
        for lo in (u.get("left_out") or [])[:_MAX_LEFT_OUT]:
            path = _clean_sub(lo.get("path")) if isinstance(lo, dict) else None
            if not path:
                return None, "one of its left-out files is unusable"
            kept = lo.get("kept_from")
            left_out.append({"path": path, "reason": "conflict" if lo.get("reason") == "conflict" else "manual",
                             "kept_from": kept if _text(kept, 500) else None})
        units.append({"file_id": u["file_id"], "sub": sub, "left_out": left_out})
    if not units:
        return None, "it has no ticked folders"
    return {
        "item": item, "category": category, "mod_id": mod_id, "record_type": record_type,
        "name": entry.get("name") if _text(entry.get("name")) else f"Mod {mod_id}",
        "author": entry.get("author") if _text(entry.get("author")) else "",
        "url": entry.get("url") if _text(entry.get("url"), 500) else "", "files": files, "units": units,
    }, None


def parse_mod_list(text, categories):
    """(document, None) for the text of a list file, or (None, why not). Entries that can't be used are returned in
    "unusable" with the reason instead of failing the whole file."""
    try:
        doc = json.loads(text)
    except ValueError:
        return None, "That isn't a mod list file (it isn't readable as JSON)."
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        return None, "That isn't a mod list exported from this app."
    version = doc.get("version")
    if not isinstance(version, int) or version > VERSION:
        return None, "That list was made by a newer version of the app. Update the app, then try again."
    raw = doc.get("mods")
    if not isinstance(raw, list):
        return None, "That mod list has no mods in it."
    mods, unusable = [], []
    for entry in raw[:_MAX_MODS]:
        clean, why = clean_entry(entry, categories)
        if clean:
            mods.append(clean)
        else:
            unusable.append({"name": (entry.get("name") if isinstance(entry, dict) and isinstance(entry.get("name"), str) else "A mod")[:80],
                             "reason": why})
    return {
        "mods": mods, "unusable": unusable, "app_version": str(doc.get("app_version") or "")[:20],
        "exported_at": str(doc.get("exported_at") or "")[:30],
        "not_shared": [n for n in (s.get("key") for s in doc.get("not_shared") or [] if isinstance(s, dict)) if isinstance(n, str)][:500],
    }, None
