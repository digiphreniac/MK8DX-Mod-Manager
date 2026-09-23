"""A local, required copy of the base game's own files - the "source of truth" for menu icons/text (ui_setup.py) and
default character voices (voice_api.py), so both features work without the user's extracted game folder staying plugged in,
and without a character needing its own voice mod ticked first.

Only a known, bounded set of files is copied - not the whole RomFS:
  UI/cmn/common.sarc, UI/cmn/menu.sarc                          - menu icons (every character)
  UI/<locale>/message.sarc                                      - menu text, one per language found
  Audio/Driver/Driver_<slot>.bars, Audio/DriverMenu/MenuDriver_<slot>.bars   - each character's own voice

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
import shutil
from pathlib import Path

DIRNAME = "game-files"
MANIFEST_FILENAME = "manifest.json"
ICON_RELPATHS = {"common": "UI/cmn/common.sarc", "menu": "UI/cmn/menu.sarc"}
REQUIRED_ICON_IDS = ("common", "menu")


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
    return {"icons": icons, "voice": voice}


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
    return {"icons": icons_ok, "voice": voice_ok, "problems": problems}


def copy_both(source_folder, master_root: Path) -> dict:
    """Validates a folder the user chose has enough to work with, then copies it into BOTH original/ and current/
    (replacing whichever was there before - see the "update from a new dump" behaviour) and writes the manifest.
    {"success": True, "manifest": {...}} or {"success": False, "error": "plain words"}."""
    found = discover(source_folder)
    missing_required = [a for a in REQUIRED_ICON_IDS if a not in found["icons"]]
    if missing_required or not any(a.startswith("message:") for a in found["icons"]):
        return {"success": False, "error": (
            "That folder doesn't hold the game's files. Choose the 'romfs' folder you extracted from your own copy of "
            "the game (it contains UI/cmn/common.sarc, UI/cmn/menu.sarc, and a UI/<language>/message.sarc).")}
    root = master_root / DIRNAME
    for name in ("original", "current"):
        old = root / name
        if old.is_dir():
            shutil.rmtree(old)
    result_original = _copy_into(found, root / "original")
    result_current = _copy_into(found, root / "current")
    mm = _mm()
    manifest = {
        "source": str(source_folder), "copied_at": mm.datetime.now().isoformat(timespec="seconds"),
        "icons": sorted(result_current["icons"]), "voice": result_current["voice"],
        "voice_total": len(mm.DRIVER_SLOTS), "problems": result_original["problems"] + result_current["problems"],
    }
    (root / MANIFEST_FILENAME).write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return {"success": True, "manifest": manifest}


def _load_manifest(master_root: Path):
    try:
        return json.loads((master_root / DIRNAME / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def status(master_root: Path) -> dict:
    """For Setup and Settings: {"done", "source", "copied_at", "icons": [...], "locales": [...], "voice_found",
    "voice_total", "problems"}. "done" is what gates the required setup step - the same minimum copy_both() requires."""
    manifest = _load_manifest(master_root)
    if not manifest or not (master_root / DIRNAME / "current").is_dir():
        return {"done": False, "source": None, "copied_at": None, "icons": [], "locales": [], "voice_found": 0,
                "voice_total": len(_mm().DRIVER_SLOTS), "problems": []}
    icons = manifest.get("icons") or []
    locales = sorted(a.split(":", 1)[1] for a in icons if a.startswith("message:"))
    done = all(a in icons for a in REQUIRED_ICON_IDS) and bool(locales)
    return {"done": done, "source": manifest.get("source"), "copied_at": manifest.get("copied_at"),
            "icons": icons, "locales": locales, "voice_found": len(manifest.get("voice") or []),
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


def find_current_voice(master_root: Path, kind: str, stem: str):
    """The app's own copy of one character's voice archive, or None."""
    p = master_root / DIRNAME / "current" / _voice_relpath(kind, stem)
    return p if p.is_file() else None
