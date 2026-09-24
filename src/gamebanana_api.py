"""
Thin wrapper around GameBanana's public API - browsing categories/mods and
downloading+extracting files. No pywebview dependency here; mod_manager.py's
Api class calls into this and handles persistence/state.

Uses only the standard library (urllib) so no new pip dependency is needed.
"""

import hashlib
import json
import re
import shutil
import subprocess
import urllib.request
import urllib.error
import urllib.parse
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

USER_AGENT = "mk8dx-mod-manager (personal local tool)"
API_V13 = "https://gamebanana.com/apiv13"
API_V11 = "https://gamebanana.com/apiv11"

_TAG_RE = re.compile(r"<[^>]+>")
# ".../mods/<id>" is the normal profile-page URL; ".../mods/download/<id>"
# is what "copy link" on a specific file on that page gives you instead (the
# id is still the mod's, a "#FileInfo_<file id>" fragment just scrolls to
# one particular file - that fragment isn't parsed here, so a link copied
# this way still needs the right file picked out by hand once fetched).
_MOD_URL_RE = re.compile(r"gamebanana\.com/mods/(?:download/)?(\d+)")
# GameBanana's audio packs (e.g. character voice mods) are a separate content
# type from Mod, with their own id space and URL prefix, but the ProfilePage
# API shape is otherwise identical (same _sName/_sText/_aFiles/etc.).
_SOUND_URL_RE = re.compile(r"gamebanana\.com/sounds/(\d+)")


class GameBananaError(Exception):
    pass


def _get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as e:
        raise GameBananaError(f"Couldn't reach GameBanana: {e}") from e
    except json.JSONDecodeError as e:
        raise GameBananaError(f"GameBanana returned unexpected data: {e}") from e


def strip_html(text):
    """GameBanana's mod descriptions come back as rendered HTML. We only ever
    display plain text in the app (never innerHTML on remote content), so
    strip tags down to readable text rather than showing raw markup."""
    if not text:
        return ""
    text = re.sub(r"(?i)</p>|<br\s*/?>", "\n", text)
    text = _TAG_RE.sub("", text)
    return unescape(text).strip()


class _RunsParser(HTMLParser):
    """Turns a description's HTML into plain-text "runs" - [{"text": ...}, {"text": ..., "href": ...}] - so the app can show
    real, clickable links without ever putting remote markup into the page: it builds its own <a> elements from these. Only
    http(s) links (and GameBanana's own relative ones) survive; everything else is just its text."""
    _BREAKS = {"p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "blockquote"}
    _SKIP = {"script", "style"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.runs = []
        self._href = None
        self._skip = 0

    def _add(self, text, href=None):
        if not text:
            return
        if self.runs and self.runs[-1].get("href") == href:
            self.runs[-1]["text"] += text
        else:
            self.runs.append({"text": text, "href": href} if href else {"text": text})

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip += 1
        elif tag == "br":
            self._add("\n")
        elif tag == "a":
            self._href = _safe_href(dict(attrs).get("href"))
        elif tag == "li":
            self._add("\n• ")
        elif tag in self._BREAKS:
            self._add("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag == "a":
            self._href = None
        elif tag in self._BREAKS:
            self._add("\n")

    def handle_data(self, data):
        if not self._skip:
            self._add(data, self._href)


def _safe_href(href):
    href = (href or "").strip()
    if href.startswith("/") and not href.startswith("//"):
        href = "https://gamebanana.com" + href
    return href if re.match(r"^https?://[^\s]+$", href, re.IGNORECASE) else None


def html_to_runs(text):
    """The runs (see _RunsParser) of a description's HTML: its text with the line breaks tidied, and its links kept."""
    if not text:
        return []
    parser = _RunsParser()
    parser.feed(text)
    parser.close()
    runs = parser.runs
    for r in runs:   # never more than one blank line in a row
        r["text"] = re.sub(r"[ \t]*\n(?:[ \t]*\n)+", "\n\n", r["text"])
        r["text"] = re.sub(r"\n\n(?=• )", "\n", r["text"])   # (a list's bullets sit on consecutive lines)
    if runs:   # no blank lines at either end
        runs[0]["text"] = runs[0]["text"].lstrip()
        runs[-1]["text"] = runs[-1]["text"].rstrip()
    tidy = []
    for r in runs:   # a link's own text starts and ends at its first and last letter (not the space the page put inside it)
        if r.get("href"):
            text = r["text"].strip()
            if text and text != r["text"]:
                start = r["text"].index(text[0])
                if start:
                    tidy.append({"text": r["text"][:start]})
                tidy.append({"text": text, "href": r["href"]})
                if start + len(text) < len(r["text"]):
                    tidy.append({"text": r["text"][start + len(text):]})
                continue
        tidy.append(r)
    return [r for r in tidy if r["text"]]


def tag_names(tags):
    """A mod's tags as plain strings. The mod list gives them that way already ("Texture: Custom"); a mod's own page gives
    {"_sTitle": "Texture", "_sValue": "Custom"} objects."""
    names = []
    for tag in tags or []:
        if isinstance(tag, dict):
            title, value = tag.get("_sTitle"), tag.get("_sValue")
            tag = f"{title}: {value}" if title and value else (title or value)
        if isinstance(tag, str) and tag.strip():
            names.append(tag.strip())
    return names


def _added(ts):
    """"Mar 03, 2024" for a GameBanana unix timestamp (None when it has none)."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%b %d, %Y") if ts else None


def parse_mod_ref(url_or_id) -> tuple[str, int]:
    """Accepts a bare id (int or numeric string, assumed to be a Mod), or a
    full GameBanana URL - .../mods/<id> or .../sounds/<id> (with any
    #anchor/query intact). Returns (record_type, id), record_type being
    "Mod" or "Sound"."""
    s = str(url_or_id).strip()
    if s.isdigit():
        return ("Mod", int(s))
    m = _MOD_URL_RE.search(s)
    if m:
        return ("Mod", int(m.group(1)))
    m = _SOUND_URL_RE.search(s)
    if m:
        return ("Sound", int(m.group(1)))
    raise GameBananaError(f"Couldn't find a mod or sound id in '{url_or_id}'.")


def fetch_subcategories(parent_id: int):
    """List every subcategory under a parent category (e.g. every character
    under the Characters category), including empty ones so a character with
    zero current mods still resolves to its subcategory id."""
    url = f"{API_V13}/Mod/Categories?_idCategoryRow={parent_id}&_sSort=a_to_z&_bShowEmpty=true"
    data = _get_json(url)
    return [
        {
            "id": row["_idRow"],
            "name": row["_sName"],
            "item_count": row.get("_nItemCount", 0),
            "icon_url": row.get("_sIconUrl"),
        }
        for row in data
    ]


SORT_ALIASES = {
    "most_liked": "Generic_MostLiked",
    "most_viewed": "Generic_MostViewed",
    "most_downloaded": "Generic_MostDownloaded",
    "newest": "Generic_Newest",
}


def browse_category(category_id: int, page: int = 1, per_page: int = 15, sort: str = "most_liked"):
    sort_alias = SORT_ALIASES.get(sort, SORT_ALIASES["most_liked"])
    url = (
        f"{API_V13}/Mod/Index?_nPerpage={per_page}"
        f"&_aFilters%5BGeneric_Category%5D={category_id}&_nPage={page}&_sSort={sort_alias}"
    )
    data = _get_json(url)
    records = []
    for row in data.get("_aRecords", []):
        screenshot = (row.get("_aPreviewContent") or {}).get("screenshot")
        thumbnail_url = None
        if screenshot:
            thumbnail_url = screenshot["_sBaseUrl"] + "/" + screenshot.get("_sFile220", screenshot["_sFile"])
        records.append({
            "mod_id": row["_idRow"],
            "name": row["_sName"],
            "profile_url": row["_sProfileUrl"],
            "submitter": (row.get("_aSubmitter") or {}).get("_sName", "?"),
            "like_count": row.get("_nLikeCount", 0),
            "view_count": row.get("_nViewCount", 0),
            "thumbnail_url": thumbnail_url,
            "has_content_ratings": row.get("_bHasContentRatings", False),
            "tags": tag_names(row.get("_aTags")),
            "added": _added(row.get("_tsDateAdded")),
        })
    return _page_result(records, data.get("_aMetadata", {}), page, per_page)


def _page_result(records, meta, page, per_page):
    """The shape every browse call returns. `done` = there is nothing after this page."""
    total = meta.get("_nRecordCount", len(records))
    per_page = meta.get("_nPerpage", per_page) or per_page
    return {
        "records": records,
        "total": total,
        "is_complete": meta.get("_bIsComplete", True),
        "done": bool(meta.get("_bIsComplete", True)) or page * per_page >= total,
        "per_page": per_page,
        "page": page,
        "next_page": page + 1,
    }


MK8DX_GAME_ID = 6507  # GameBanana's "Mario Kart 8 Deluxe" (Switch)


def fetch_mod_detail(mod_id: int, record_type: str = "Mod"):
    # ProfilePage returns the whole record with no _csvProperties allowlist -
    # simpler than the old Mod/{id}?_csvProperties=... call, and (unlike that
    # endpoint) actually includes _aTags without an UNKNOWN_PROPERTY error.
    # Works identically for record_type="Sound" (GameBanana's audio packs) -
    # same ProfilePage shape, just a different content type/id space.
    url = f"{API_V11}/{record_type}/{mod_id}/ProfilePage"
    data = _get_json(url)
    if "_sName" not in data:
        kind = "sound" if record_type == "Sound" else "mod"
        raise GameBananaError(f"GameBanana has no {kind} #{mod_id} (or it's private/removed).")

    updated_at = None
    ts = data.get("_tsDateModified")
    if ts:
        updated_at = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%b %d, %Y")

    thumbnail_url = None
    thumbnail_url_large = None
    images = (data.get("_aPreviewMedia") or {}).get("_aImages") or []
    if images:
        img = images[0]
        thumbnail_url = img["_sBaseUrl"] + "/" + img.get("_sFile220", img["_sFile"])
        thumbnail_url_large = img["_sBaseUrl"] + "/" + img.get("_sFile530", img.get("_sFile220", img["_sFile"]))

    # Full screenshot gallery (not just the lead thumbnail above) - used to
    # let the user pick a source image for a generated course-select icon
    # when a mod doesn't bundle its own (see Api.generate_course_icon()).
    # "_sFile" (no size suffix) is the original upload, used as the actual
    # crop/encode source; "_sFile220" is just for a fast picker thumbnail.
    screenshots = [
        {
            "thumb_url": img["_sBaseUrl"] + "/" + img.get("_sFile220", img["_sFile"]),
            "full_url": img["_sBaseUrl"] + "/" + img["_sFile"],
        }
        for img in images
    ]

    files = [
        {
            "file_id": f["_idRow"],
            "name": f["_sFile"],
            "size": f["_nFilesize"],
            "download_url": f["_sDownloadUrl"],
            "md5": f.get("_sMd5Checksum"),
            # Per-file caption GameBanana shows next to each download option on
            # the site - often just a version label ("Version 1.1 [Current]"),
            # sometimes a real note about what that particular file is.
            "description": strip_html(f.get("_sDescription")) or None,
        }
        for f in data.get("_aFiles", [])
    ]

    default_url_path = "sounds" if record_type == "Sound" else "mods"
    # ProfilePage's own category fields (verified live - NOT "_aSubCategory",
    # which is what the separate search endpoint uses instead): _aCategory is
    # this mod's own (sub)category - for a character mod that's literally the
    # character's name one level under _aSuperCategory "Characters"
    # (id 10529, matches CHARACTERS_CATEGORY_ID); for a course mod
    # _aCategory is one of COURSE_SEARCH_SUBCATEGORIES under _aSuperCategory
    # "Courses". Used by Api.gb_identify_mod() to guess what a freshly-pasted
    # link should be tracked as, without the user having to say so themselves.
    category = data.get("_aCategory") or {}
    super_category = data.get("_aSuperCategory") or {}
    return {
        "mod_id": mod_id,
        "record_type": record_type,
        "name": data["_sName"],
        "description": strip_html(data.get("_sText")),
        "description_runs": html_to_runs(data.get("_sText")),
        "profile_url": data.get("_sProfileUrl", f"https://gamebanana.com/{default_url_path}/{mod_id}"),
        "thumbnail_url": thumbnail_url,
        "thumbnail_url_large": thumbnail_url_large,
        "screenshots": screenshots,
        "author": (data.get("_aSubmitter") or {}).get("_sName", "?"),
        "version": data.get("_sVersion") or None,
        "updated_at": updated_at,
        "download_count": data.get("_nDownloadCount", 0),
        "view_count": data.get("_nViewCount", 0),
        "like_count": data.get("_nLikeCount", 0),
        "tags": tag_names(data.get("_aTags")),
        "files": files,
        "category_name": category.get("_sName"),
        "category_id": category.get("_idRow"),
        "super_category_id": super_category.get("_idRow"),
        # Which GameBanana game this is filed under. GameBanana keeps
        # "Mario Kart 8" (Wii U, id 5709) and "Mario Kart 8 Deluxe" (Switch,
        # id 6507) as separate games with near-identical category trees, and
        # pasting a link doesn't stop a Wii U mod from being added - see
        # MK8DX_GAME_ID and the "wrong game" warnings built on it.
        "game_id": (data.get("_aGame") or {}).get("_idRow"),
        "game_name": (data.get("_aGame") or {}).get("_sName"),
    }


# Only these mod subcategories are for things that actually replace/edit a
# course - matches what the user's own manual research process filtered to.
COURSE_SEARCH_SUBCATEGORIES = {"Course Edits", "Course Retextures", "Custom Race Courses"}


def search_mods(query: str, game_id: int = 6507, page: int = 1, per_page: int = 15):
    """GameBanana's full-text search (same engine as the site's search box) -
    unlike browse_category, this matches against a mod's description too, not
    just its title, which is essential for courses since retexture mods
    rarely repeat the base course's name in their own title. It has no sort
    (every sort parameter is ignored - the results are always best-match first)."""
    params = urllib.parse.urlencode({
        "_sSearchString": query,
        "_idGameRow": game_id,
        "_sRecordType": "Mod",
        "_nPage": page,
    })
    url = f"{API_V11}/Util/Search/Results?{params}"
    data = _get_json(url)
    records = []
    for row in data.get("_aRecords", []):
        images = (row.get("_aPreviewMedia") or {}).get("_aImages") or []
        thumbnail_url = None
        if images:
            img = images[0]
            thumbnail_url = img["_sBaseUrl"] + "/" + img.get("_sFile220", img["_sFile"])
        records.append({
            "mod_id": row["_idRow"],
            "name": row["_sName"],
            "profile_url": row["_sProfileUrl"],
            "submitter": (row.get("_aSubmitter") or {}).get("_sName", "?"),
            "like_count": row.get("_nLikeCount", 0),
            "view_count": row.get("_nViewCount", 0),
            "thumbnail_url": thumbnail_url,
            "has_content_ratings": row.get("_bHasContentRatings", False),
            "tags": tag_names(row.get("_aTags")),
            "added": _added(row.get("_tsDateAdded")),
            "subcategory": (row.get("_aSubCategory") or {}).get("_sName"),
        })
    result = _page_result(records, data.get("_aMetadata", {}), page, per_page)
    result["done"] = result["done"] or not records   # (a page past the end comes back empty)
    return result


def search_course_mods(query: str, first_page: int = 1, pages: int = 3):
    """Searches for a course name and keeps only the results in the course-editing subcategories. Most of a page's results
    are something else (other mod kinds, other games' courses), so this reads several search pages at the same time to
    bring back a useful handful in one go. `next_page` is where the next call should start."""
    with ThreadPoolExecutor(max_workers=pages) as pool:
        results = list(pool.map(lambda p: search_mods(query, page=p), range(first_page, first_page + pages)))
    records, seen, done = [], set(), False
    for res in results:
        for rec in res["records"]:
            if rec["mod_id"] not in seen and rec["subcategory"] in COURSE_SEARCH_SUBCATEGORIES:
                seen.add(rec["mod_id"])
                records.append(rec)
        if res["done"]:
            done = True
            break
    return {"records": records, "done": done, "next_page": first_page + pages, "page": first_page,
            "total": results[0]["total"], "per_page": results[0]["per_page"]}


def snippet_around(text: str, needle: str, radius: int = 90) -> str:
    """A short excerpt of text centered on the first occurrence of needle
    (case-insensitive), or just the start of text if needle isn't found."""
    if not text:
        return ""
    lower = text.lower()
    idx = lower.find(needle.lower()) if needle else -1
    if idx == -1:
        return text[:200].strip() + ("…" if len(text) > 200 else "")
    start = max(0, idx - radius)
    end = min(len(text), idx + len(needle) + radius)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return prefix + text[start:end].strip() + suffix


# url -> a copy already fetched by prefetch_files(); download_file() uses (and
# consumes) it instead of downloading again.
_PREFETCHED = {}


def prefetch_files(jobs, cache_dir: Path, workers: int = 4):
    """Downloads several files AT THE SAME TIME into cache_dir (GameBanana serves
    each connection at only ~100-150 KB/s, so one at a time is very slow).
    `jobs` = [(url, expected_size, expected_md5)]. A failed one is simply not
    cached - download_file() then fetches it the normal way and reports the
    error. Returns how many were cached."""
    cache_dir.mkdir(parents=True, exist_ok=True)

    def one(job):
        url, size, md5 = job
        dest = cache_dir / hashlib.md5(url.encode("utf-8")).hexdigest()
        try:
            _download_direct(url, dest, size, md5)
        except GameBananaError:
            return None
        return url, dest

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for res in pool.map(one, jobs):
            if res:
                _PREFETCHED[res[0]] = res[1]
    return sum(1 for j in jobs if j[0] in _PREFETCHED)


def download_file(url: str, dest_path: Path, expected_size=None, expected_md5=None):
    """Downloads to dest_path, verifying size and (if given) MD5 against what
    the API reported. Raises GameBananaError on any mismatch or failure -
    never leaves a half-downloaded file at dest_path on failure. A copy that
    prefetch_files() already fetched is moved into place instead."""
    cached = _PREFETCHED.pop(url, None)
    if cached is not None and cached.exists():
        cached.replace(dest_path)
        return dest_path
    return _download_direct(url, dest_path, expected_size, expected_md5)


def _download_direct(url: str, dest_path: Path, expected_size=None, expected_md5=None):
    tmp_path = dest_path.with_suffix(dest_path.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp, open(tmp_path, "wb") as out:
            shutil.copyfileobj(resp, out)
    except (urllib.error.URLError, OSError) as e:
        tmp_path.unlink(missing_ok=True)
        raise GameBananaError(f"Download failed: {e}") from e

    actual_size = tmp_path.stat().st_size
    if expected_size is not None and actual_size != expected_size:
        tmp_path.unlink(missing_ok=True)
        raise GameBananaError(
            f"Downloaded size ({actual_size} bytes) doesn't match GameBanana's "
            f"reported size ({expected_size} bytes) - possibly a corrupted or partial download."
        )

    if expected_md5:
        actual_md5 = hashlib.md5(tmp_path.read_bytes()).hexdigest()
        if actual_md5 != expected_md5:
            tmp_path.unlink(missing_ok=True)
            raise GameBananaError("Downloaded file's MD5 checksum doesn't match GameBanana's - corrupted download.")

    tmp_path.replace(dest_path)
    return dest_path


def fetch_bytes(url: str, timeout: int = 30) -> bytes:
    """Downloads a URL straight into memory - for a mod's own screenshot
    image (used as a course-icon source, see Api.generate_course_icon()),
    not a whole archive, so there's no size/MD5 to verify against and
    nothing worth persisting to disk on its own."""
    if not url.startswith("https://images.gamebanana.com/"):
        raise GameBananaError("Refusing to fetch an untrusted image URL.")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except (urllib.error.URLError, OSError) as e:
        raise GameBananaError(f"Couldn't download that image: {e}") from e


def find_7zip():
    for candidate in (
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
    ):
        if Path(candidate).is_file():
            return candidate
    found = shutil.which("7z") or shutil.which("7zz") or shutil.which("7z.exe")
    return found


def extract_archive(archive_path: Path, dest_dir: Path):
    """Extracts archive_path into dest_dir (created if needed). Uses Python's
    zipfile for .zip when 7-Zip isn't available; everything else needs 7-Zip."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    sevenzip = find_7zip()

    if sevenzip:
        result = subprocess.run(
            [sevenzip, "x", str(archive_path), f"-o{dest_dir}", "-y"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise GameBananaError(f"7-Zip extraction failed: {result.stdout}\n{result.stderr}")
        return

    if archive_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(archive_path) as zf:
            zf.extractall(dest_dir)
        return

    raise GameBananaError(
        f"Can't extract '{archive_path.name}' - 7-Zip isn't installed and this isn't a .zip file. "
        "Install 7-Zip (7-zip.org) to extract .rar/.7z archives."
    )
