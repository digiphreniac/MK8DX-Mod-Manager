"""A local, required copy of the base game's own files - the "source of truth" for menu icons/text (ui_setup.py) and
default character voices (voice_api.py), so both features work without the user's extracted game folder staying plugged in,
and without a character needing its own voice mod ticked first.

Only a known, bounded set of files is copied - not the whole RomFS:
  UI/cmn/common.sarc, UI/cmn/menu.sarc                          - menu icons (every character)
  UI/<locale>/message.sarc                                      - menu text, one per language found
  Audio/Driver/Driver_<slot>.bars, Audio/DriverMenu/MenuDriver_<slot>.bars   - each character's own voice
  UI/cmn/menu/ym_CoursePict_<id>_00^u.bntx                      - each course's own course-select picture (about 105, 9 MB;
                                                                  optional - an older copy without them still counts as done)
  UI/cmn/menu/tc_KP_<part>_<variant>^l.bntx                     - the vehicle parts' pictures that are not inside menu.sarc
                                                                  (351 files, 38 MB; see vehicle_icons.py - optional the same way)

Two copies live under <master_root>/game-files/:
  original/  - written once (or replaced whole by "update from a new dump"), never touched again otherwise. The
               disaster-recovery copy: what current/ is reset from if it's ever missing or looks wrong, and what
               "view my original files" opens.
  current/   - what every other part of the app actually reads (find_current() / find_current_voice()).
Nothing today writes into current/ in place - both are identical from the moment they're made - but keeping them as two
separate copies is what makes a blind, cheap reset possible without asking the user to reconnect their dump.

manifest.json (also under game-files/) records what was found: which icon archives, which locales, which voice slots,
where the source folder was (for display only - it does not need to still exist afterward) and when it was copied.
"""
import json
import os
import safe_io
import shutil
from pathlib import Path

import diag

import vehicle_icons

DIRNAME = "game-files"
MANIFEST_FILENAME = "manifest.json"
ICON_RELPATHS = {"common": "UI/cmn/common.sarc", "menu": "UI/cmn/menu.sarc"}
REQUIRED_ICON_IDS = ("common", "menu")
COURSE_PICT_DIR = "UI/cmn/menu"
COURSE_PICT_PREFIX = "ym_CoursePict_"


def _mm():
    import mod_manager            # (imported late: mod_manager imports this module)
    return mod_manager


def _ui():
    import ui_setup
    return ui_setup


class GameFilesError(Exception):
    """Something the user can be told in plain words."""


def _voice_relpath(kind, stem):
    prefix = {"race": "Audio/Driver/Driver_", "menu": "Audio/DriverMenu/MenuDriver_"}[kind]
    return f"{prefix}{stem}.bars"


def _looks_like(path: Path, magic: bytes) -> bool:
    try:
        return path.is_file() and path.read_bytes()[:len(magic)] == magic
    except OSError:
        return False


def discover(source_folder) -> dict:
    """Everything usable found in a folder the user extracted from their own game: {"icons": {archive id: Path} (as
    ui_setup.find_game_files - common/menu/message:<locale>), "voice": {stem: {"race": Path|None, "menu": Path|None}},
    "root": the romfs-holding folder actually used}. Neither list is filtered by DRIVER_SLOTS completeness - callers
    decide what counts as "enough"."""
    ui_setup = _ui()
    icons = ui_setup.find_game_files(source_folder)
    mm = _mm()
    folder = Path(source_folder) if source_folder else None
    voice = {}
    if folder is not None:
        for root in (folder, mm._ci_child(folder, "romfs")):
            if root is None or not root.is_dir():
                continue
            audio = mm._ci_child(root, "Audio")
            if audio is None:
                continue
            driver = mm._ci_child(audio, "Driver")
            driver_menu = mm._ci_child(audio, "DriverMenu")
            for stem in mm.DRIVER_SLOTS:
                race = mm._ci_child(driver, f"Driver_{stem}.bars") if driver else None
                menu = mm._ci_child(driver_menu, f"MenuDriver_{stem}.bars") if driver_menu else None
                if (race is not None and race.is_file()) or (menu is not None and menu.is_file()):
                    entry = voice.setdefault(stem, {"race": None, "menu": None})
                    if race is not None and race.is_file():
                        entry["race"] = race
                    if menu is not None and menu.is_file():
                        entry["menu"] = menu
    return {"icons": icons, "voice": voice, "course_picts": _discover_course_picts(folder),
            "vehicle_picts": _discover_vehicle_picts(folder)}


def _discover_menu_files(source_folder, wanted) -> dict:
    """{file name: Path} of the files under `source_folder` (or its romfs/ folder) in UI/cmn/menu/ for which
    wanted(file name) is true. {} when there are none (some dumps and older extractions leave them out)."""
    if not source_folder:
        return {}
    mm = _mm()
    folder = Path(source_folder)
    for root in (folder, mm._ci_child(folder, "romfs")):
        if root is None or not root.is_dir():
            continue
        menu = root
        for part in COURSE_PICT_DIR.split("/"):
            menu = mm._ci_child(menu, part) if menu is not None else None
        if menu is None or not menu.is_dir():
            continue
        found = {f.name: f for f in menu.iterdir() if f.is_file() and wanted(f.name)}
        if found:
            return found
    return {}


def _discover_course_picts(source_folder) -> dict:
    """The course-select pictures: every UI/cmn/menu/ym_CoursePict_*.bntx."""
    return _discover_menu_files(
        source_folder, lambda n: n.startswith(COURSE_PICT_PREFIX) and n.lower().endswith(".bntx"))


def _discover_vehicle_picts(source_folder) -> dict:
    """Every loose vehicle-part picture (vehicle_icons.loose_family() - all 351: the Vehicles screen shows 16 of them, and
    your own picture for a part has to be written into every variant of it)."""
    return _discover_menu_files(source_folder, lambda n: vehicle_icons.loose_family(n) is not None)


def _copy_one(dest_root: Path, relpath: str, src: Path, magic: bytes, problems: list) -> bool:
    if not _looks_like(src, magic):
        problems.append(f"{relpath}: doesn't look like a valid file ({src}) - skipped")
        return False
    dest = dest_root / relpath
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(src, dest)
    except OSError as e:
        problems.append(f"{relpath}: couldn't copy - {e}")
        return False
    return True


def _copy_into(found: dict, dest_root: Path) -> dict:
    """Copies everything `discover()` found into `dest_root` (mirroring the game's own relative paths), validating each
    file's magic bytes first. Returns {"icons": [ids copied], "voice": [stems copied - race and/or menu], "problems": []}."""
    problems = []
    icons_ok = []
    for aid, src in sorted(found["icons"].items()):
        rel = ICON_RELPATHS.get(aid) or f"UI/{aid.split(':', 1)[1]}/message.sarc"
        if _copy_one(dest_root, rel, src, b"SARC", problems):
            icons_ok.append(aid)
    voice_ok = []
    for stem, kinds in sorted(found["voice"].items()):
        got = {}
        for kind, src in kinds.items():
            if src is None:
                continue
            if _copy_one(dest_root, _voice_relpath(kind, stem), src, b"BARS", problems):
                got[kind] = True
        if got:
            voice_ok.append({"stem": stem, **{k: True for k in got}})
    picts_ok = 0
    for fname, src in sorted(found.get("course_picts", {}).items()):
        if _copy_one(dest_root, f"{COURSE_PICT_DIR}/{fname}", src, b"BNTX", problems):
            picts_ok += 1
    vehicle_ok = 0
    for fname, src in sorted(found.get("vehicle_picts", {}).items()):
        if _copy_one(dest_root, f"{COURSE_PICT_DIR}/{fname}", src, b"BNTX", problems):
            vehicle_ok += 1
    return {"icons": icons_ok, "voice": voice_ok, "course_pictures": picts_ok, "vehicle_pictures": vehicle_ok,
            "problems": problems}


def _fail(message: str, detail: str = "") -> dict:
    diag.log("game-files", f"copy failed: {message}" + (f" ({detail})" if detail else ""))
    return {"success": False, "error": message}


def copy_both(source_folder, master_root: Path) -> dict:
    """Validates a folder the user chose has enough to work with, then copies it into BOTH original/ and current/
    (replacing whichever was there before - see the "update from a new dump" behaviour) and writes the manifest.
    The new copies are made beside the old ones and swapped in only once they are complete, so a copy that fails
    (disk full, a file locked by antivirus, the app closed) leaves what was there before untouched.
    {"success": True, "manifest": {...}} or {"success": False, "error": "plain words"}."""
    found = discover(source_folder)
    missing_required = [a for a in REQUIRED_ICON_IDS if a not in found["icons"]]
    if missing_required or not any(a.startswith("message:") for a in found["icons"]):
        return {"success": False, "error": (
            "That folder doesn't hold the game's files. Choose the 'romfs' folder you extracted from your own copy of "
            "the game (it contains UI/cmn/common.sarc, UI/cmn/menu.sarc, and a UI/<language>/message.sarc).")}
    root = master_root / DIRNAME
    names = ("original", "current")
    diag.log("game-files", f"copy starting from {source_folder}: found {len(found['icons'])} archives, {len(found['voice'])} voices, "
                           f"{len(found.get('course_picts', {}))} course pictures, {len(found.get('vehicle_picts', {}))} vehicle pictures; "
                           f"{diag.free_gb(master_root)}")
    fresh = {name: root / f"{name}.new" for name in names}
    for path in list(fresh.values()) + [root / f"{name}.old" for name in names]:
        shutil.rmtree(path, ignore_errors=True)   # (left over from a copy that was interrupted)
    try:
        result_original = _copy_into(found, fresh["original"])
        result_current = _copy_into(found, fresh["current"])
    except OSError as e:
        for path in fresh.values():
            shutil.rmtree(path, ignore_errors=True)
        return _fail(f"Couldn't copy the game's files ({e}). Check there is enough free space, then try again. Nothing was changed.",
                     f"{type(e).__name__} at {getattr(e, 'filename', None)}")
    copied = set(result_current["icons"])
    if any(a not in copied for a in REQUIRED_ICON_IDS) or not any(a.startswith("message:") for a in copied):
        for path in fresh.values():
            shutil.rmtree(path, ignore_errors=True)
        problems = result_original["problems"] + result_current["problems"]
        return _fail("Some of the game's files couldn't be copied (" + "; ".join(problems[:3]) + "). Nothing was changed.", "; ".join(problems[:10]))
    swapped = []
    try:
        for name in names:
            final, old = root / name, root / f"{name}.old"
            if final.is_dir():
                os.replace(final, old)
            os.replace(fresh[name], final)
            swapped.append(name)
    except OSError as e:   # (put back what was there: a half-swapped pair would be worse than either)
        for name in names:
            final, old = root / name, root / f"{name}.old"
            try:
                if old.is_dir():
                    if final.is_dir():
                        shutil.rmtree(final, ignore_errors=True)
                    os.replace(old, final)
            except OSError:
                pass
            shutil.rmtree(fresh[name], ignore_errors=True)
        return _fail(f"Couldn't put the copied game files in place ({e}). The previous copy was kept.", f"{type(e).__name__} at {getattr(e, 'filename', None)}")
    for name in names:
        shutil.rmtree(root / f"{name}.old", ignore_errors=True)
    mm = _mm()
    manifest = {
        "source": str(source_folder), "copied_at": mm.datetime.now().isoformat(timespec="seconds"),
        "icons": sorted(result_current["icons"]), "voice": result_current["voice"],
        "course_pictures": result_current["course_pictures"], "vehicle_pictures": result_current["vehicle_pictures"],
        "vehicle_pictures_all": True,
        "voice_total": len(mm.DRIVER_SLOTS), "problems": result_original["problems"] + result_current["problems"],
    }
    try:
        safe_io.write_json_atomic((root / MANIFEST_FILENAME), manifest)
    except OSError as e:
        return _fail(f"The game's files were copied but couldn't be recorded ({e}). Try again.", type(e).__name__)
    diag.log("game-files", f"copy finished: {len(manifest['icons'])} archives, {len(manifest['voice'])} voices, "
                           f"{manifest['course_pictures']} course pictures, {manifest['vehicle_pictures']} vehicle pictures"
                           + (f"; problems: {'; '.join(manifest['problems'][:10])}" if manifest["problems"] else ""))
    return {"success": True, "manifest": manifest}


def _load_manifest(master_root: Path):
    try:
        return json.loads((master_root / DIRNAME / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def status(master_root: Path) -> dict:
    """For the Setup step and the flow bar: {"done", "source", "copied_at", "icons": [...], "locales": [...], "voice_found",
    "voice_total", "problems"}. "done" is what gates the required setup step - the same minimum copy_both() requires."""
    manifest = _load_manifest(master_root)
    if not manifest or not (master_root / DIRNAME / "current").is_dir():
        return {"done": False, "source": None, "copied_at": None, "icons": [], "locales": [], "voice_found": 0,
                "voice_total": len(_mm().DRIVER_SLOTS), "problems": []}
    icons = manifest.get("icons") or []
    locales = sorted(a.split(":", 1)[1] for a in icons if a.startswith("message:"))
    # The manifest says what was copied; the files must really be there too (a copy that was cut short, or files deleted since,
    # leave a manifest behind that still says "done").
    on_disk = find_current(master_root)
    missing = [a for a in REQUIRED_ICON_IDS if a not in on_disk] + ([] if any(k.startswith("message:") for k in on_disk) else ["message"])
    done = all(a in icons for a in REQUIRED_ICON_IDS) and bool(locales) and not missing
    return {"done": done, "missing_on_disk": missing, "source": manifest.get("source"), "copied_at": manifest.get("copied_at"),
            "icons": icons, "locales": locales, "voice_found": len(manifest.get("voice") or []),
            "course_pictures": manifest.get("course_pictures") or 0, "vehicle_pictures": manifest.get("vehicle_pictures") or 0,
            "voice_total": manifest.get("voice_total") or len(_mm().DRIVER_SLOTS), "problems": manifest.get("problems") or []}


def original_dir(master_root: Path) -> Path:
    return master_root / DIRNAME / "original"


def find_current(master_root: Path) -> dict:
    """{"common": Path, "menu": Path, "message:<locale>": Path, ...} from the app's own working copy - same shape as
    ui_setup.find_game_files(), but reading a folder the app wrote itself (its structure is exactly known, no need for
    the fuzzy case-insensitive dual-root search a user-chosen folder needs)."""
    root = master_root / DIRNAME / "current"
    found = {}
    for aid, rel in ICON_RELPATHS.items():
        p = root / rel
        if p.is_file():
            found[aid] = p
    ui_dir = root / "UI"
    if ui_dir.is_dir():
        for loc_dir in ui_dir.iterdir():
            if loc_dir.is_dir() and loc_dir.name in _ui().LOCALES:
                p = loc_dir / "message.sarc"
                if p.is_file():
                    found[f"message:{loc_dir.name}"] = p
    return found


def find_current_course_pict(master_root: Path, pict_id: str):
    """The app's own copy of one course's select-screen picture (`pict_id` is the part of the file name after
    "ym_CoursePict_", e.g. "Gu_FirstCircuit" or "DLC07"), or None."""
    p = master_root / DIRNAME / "current" / COURSE_PICT_DIR / f"{COURSE_PICT_PREFIX}{pict_id}_00^u.bntx"
    return p if p.is_file() else None


def find_current_vehicle_pict(master_root: Path, file_name: str):
    """The app's own copy of one loose vehicle-part picture (any of the 351, see vehicle_icons.loose_family()), or None."""
    p = master_root / DIRNAME / "current" / COURSE_PICT_DIR / file_name
    return p if p.is_file() else None


def current_vehicle_picts(master_root: Path) -> dict:
    """{file name: Path} of every loose vehicle-part picture in the app's working copy."""
    folder = master_root / DIRNAME / "current" / COURSE_PICT_DIR
    if not folder.is_dir():
        return {}
    return {f.name: f for f in folder.iterdir() if f.is_file() and vehicle_icons.loose_family(f.name) is not None}


def top_up_pictures(master_root: Path) -> None:
    """For a copy made before the course pictures / the vehicle pictures were part of it: fetches what is missing from the
    folder the copy was made from, if that still exists, into BOTH copies (adding files only - nothing already there is
    touched) and records the count in the manifest so each is tried once. When the source folder is gone (or has none),
    nothing is recorded, so a later try - or the next "Update from a new dump" - can still succeed."""
    manifest = _load_manifest(master_root)
    root = master_root / DIRNAME
    if not manifest or not (root / "current").is_dir():
        return
    changed = False
    # (a copy made when only 16 of the vehicle pictures were kept has "vehicle_pictures" but not "vehicle_pictures_all")
    for key, marker, discover_fn in (("course_pictures", "course_pictures", _discover_course_picts),
                                     ("vehicle_pictures", "vehicle_pictures_all", _discover_vehicle_picts)):
        if marker in manifest:
            continue
        found = discover_fn(manifest.get("source"))
        if not found:
            continue
        count = 0
        for name in ("original", "current"):
            problems = []
            ok = 0
            for fname, src in sorted(found.items()):
                dest = root / name / COURSE_PICT_DIR / fname
                try:
                    if dest.is_file() and dest.stat().st_size == src.stat().st_size:
                        ok += 1
                        continue
                except OSError:
                    pass
                if _copy_one(root / name, f"{COURSE_PICT_DIR}/{fname}", src, b"BNTX", problems):
                    ok += 1
            count = max(count, ok)
            manifest["problems"] = (manifest.get("problems") or []) + problems
        manifest[key] = count
        manifest[marker] = True if marker != key else count
        changed = True
    if changed:
        safe_io.write_json_atomic((root / MANIFEST_FILENAME), manifest)
def find_current_voice(master_root: Path, kind: str, stem: str):
    """The app's own copy of one character's voice archive, or None."""
    p = master_root / DIRNAME / "current" / _voice_relpath(kind, stem)
    return p if p.is_file() else None
