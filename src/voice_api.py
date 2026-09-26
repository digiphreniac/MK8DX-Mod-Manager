"""The app's side of editing a character's voice: mute a line, or use your own audio for it (see voice_edit.py for the
archive work). Mixed into mod_manager.Api, so it uses the Api's own paths, state and left-out-file bookkeeping.

How it fits together
--------------------
* What the user asks for is kept in voice-edits.json: per character, {line key: {"mode": "mute"} | {"mode": "custom", ...}}.
  A custom line's audio is kept as a .wav in voice-custom/<character>/ so it can be encoded again whenever the archive
  it goes into changes.
* The result is an ordinary mod - mods/extracted/characters/<Character>/Custom voice/ - holding the rewritten archive(s)
  under romfs/Audio/. It shows in the character's mod list, can be unticked or removed like any other mod, and is merged
  by Commit like any other mod. It is ticked when it is first made.
* Muting or replacing one line means writing out the WHOLE archive, so the app needs the archive as it would otherwise be
  ("the base"): a ticked voice mod's copy if one is ticked for that slot, else the game's own file from the "Your game's
  files" folder. With neither there is nothing to start from, and the editor says so instead of guessing.
* When the base is a mod, that mod's copy of the file would clash with ours; the app leaves it out of the merge on the
  mod's behalf (a normal left-out file, "kept from Custom voice") and puts it back when the Custom voice mod is unticked
  or removed.
* If the base changes (another voice mod is ticked, the game folder is changed) the archive is written again from the
  new base (sync_voice_edits(), run whenever ticks change and before a commit).
"""
import base64
import functools
import json
import safe_io
import re
import shutil
import threading
import wave
from array import array
from pathlib import Path

import voice_audio as va
from library_cache import mutates_library
import voice_edit as ve

VOICE_EDITS_FILENAME = "voice-edits.json"
VOICE_CUSTOM_DIRNAME = "voice-custom"
UNIT_MOD_NAME = "Custom voice"
MAX_CUSTOM_SECONDS = 8.0
KIND_PREFIX = {"race": ("Audio", "Driver", "Driver_"), "menu": ("Audio", "DriverMenu", "MenuDriver_")}


def _mm():
    import mod_manager            # (imported late: mod_manager imports this module)
    return mod_manager


def _romfs_rel(path: Path) -> str:
    """A file's path relative to the romfs folder it is inside ("Audio/Driver/Driver_BbMario.bars")."""
    parts = list(path.parts)
    low = [p.lower() for p in parts]
    return "/".join(parts[len(low) - low[::-1].index("romfs"):])


def _locked(method):
    """The window can call the Api from several threads at once (two quick clicks on different lines): everything that reads and
    rewrites the voice record and the Custom voice mods takes turns."""
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        lock = self.__dict__.get("_voice_lock_obj") or self.__dict__.setdefault("_voice_lock_obj", threading.RLock())
        with lock:
            return method(self, *args, **kwargs)
    return wrapper


def _signature(path: Path) -> str:
    st = path.stat()
    return f"{path}|{st.st_size}|{st.st_mtime_ns}"


class VoiceEditMixin:
    # ---------------------------------------------------------------- the record
    def _voice_path(self):
        return self.mod_root / VOICE_EDITS_FILENAME

    def _voice_load(self):
        data = self._load_json(self._voice_path(), {})
        if not isinstance(data, dict) or not isinstance(data.get("characters"), dict):
            data = {"characters": {}}
        return data

    def _voice_save(self, data):
        chars = {c: r for c, r in data["characters"].items() if r}
        if chars:
            safe_io.write_json_atomic(self._voice_path(), {"characters": chars})
        else:
            try:
                self._voice_path().unlink()
            except OSError:
                pass

    def _voice_unit_key(self, character):
        return f"characters/{_mm().sanitize_filename(character)}/{UNIT_MOD_NAME}"

    def _voice_stems(self, character):
        return [s for s, c in _mm().DRIVER_SLOTS.items() if c == character]

    def _voice_signature(self):
        """A short text that changes whenever a Custom voice mod's contents change ('' when there are none) - part of what
        a commit is made from, so editing a line makes the last commit stale."""
        rec = self._voice_load()["characters"]
        if not rec:
            return ""
        parts = []
        for character, r in sorted(rec.items()):
            romfs = self._unit_dir(r.get("unit") or self._voice_unit_key(character)) / "romfs"
            if romfs.is_dir():
                parts.append(character + ":" + ",".join(f"{p.relative_to(romfs).as_posix()}={p.stat().st_size}:{p.stat().st_mtime_ns}"
                                                        for p in sorted(romfs.rglob("*")) if p.is_file()))
        return "|".join(parts)

    # ---------------------------------------------------------------- where the starting archive comes from
    def _voice_game_file(self, kind, stem):
        """The app's own local copy of the game's own archive for a slot (see game_files.py), or None."""
        import game_files
        return game_files.find_current_voice(self.mod_root, kind, stem)

    def _voice_ticked_files(self, skip_key):
        mm = _mm()
        out = []
        for key, on in sorted(self._load_state().items()):
            if not on or not key.startswith("characters/") or key.count("/") < 2 or key == skip_key:
                continue
            unit = self._unit_dir(key)
            if unit.is_dir():
                for kind, path in mm.unit_voice_files(unit):
                    out.append((key, kind, path))
        return out

    def _voice_find_base(self, kind, stem, own_key, ticked_files, excluded):
        """The archive a slot's edits are made on: {"path", "source" ("mod" | "game"), "key", "label", "rel", "sig"} or None.
        A ticked mod's copy wins (that is what the game would play); one left out of the merge is skipped - except when it
        was left out on behalf of the Custom voice mod itself."""
        mm = _mm()
        fname = f"{KIND_PREFIX[kind][2]}{stem}.bars".lower()
        for key, k2, path in ticked_files:
            if k2 != kind or path.name.lower() != fname:
                continue
            rel = _romfs_rel(path)
            ex = (excluded.get(key) or {}).get(self._norm_rel(rel))
            if ex and ex.get("kept_from") != own_key:
                continue
            return {"path": path, "source": "mod", "key": key, "label": mm.mod_label(key), "rel": rel, "sig": _signature(path)}
        game = self._voice_game_file(kind, stem)
        if game is not None:
            return {"path": game, "source": "game", "key": None, "label": "the game's own files",
                    "rel": f"{KIND_PREFIX[kind][0]}/{KIND_PREFIX[kind][1]}/{game.name}", "sig": _signature(game)}
        return None

    def _voice_bases(self, character):
        """{"race:<stem>" | "menu:<stem>": base or None} for a character's slots."""
        own = self._voice_unit_key(character)
        ticked, excluded = self._voice_ticked_files(own), self._load_excluded_files()
        return {f"{kind}:{stem}": self._voice_find_base(kind, stem, own, ticked, excluded)
                for stem in self._voice_stems(character) for kind in ("race", "menu")}

    # ---------------------------------------------------------------- custom audio on disk
    def _voice_custom_dir(self, character):
        return self.mod_root / VOICE_CUSTOM_DIRNAME / _mm().sanitize_filename(character)

    def _voice_store_custom(self, character, key, audio):
        """Validates the audio the page sent ({"rate", "channels", "pcm": base64 16-bit little-endian interleaved, "name"}) and
        keeps it as a .wav; returns what to remember about it."""
        try:
            rate, nch = int(audio["rate"]), int(audio["channels"])
            pcm = base64.b64decode(audio["pcm"])
        except (KeyError, TypeError, ValueError):
            raise ve.VoiceEditError("The audio didn't arrive in a form the app understands.")
        if nch not in (1, 2) or not 8000 <= rate <= 48000:
            raise ve.VoiceEditError("The audio must be mono or stereo, between 8 and 48 kHz.")
        n = len(pcm) // (2 * nch)
        seconds = n / rate
        if seconds < ve.SILENT_SECONDS:
            raise ve.VoiceEditError("That audio is too short to be a voice line.")
        if seconds > MAX_CUSTOM_SECONDS:
            raise ve.VoiceEditError(f"That audio is {seconds:.1f} seconds long; voice lines here can be at most {MAX_CUSTOM_SECONDS:.0f} seconds. Trim it first.")
        folder = self._voice_custom_dir(character)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{re.sub(r'[^A-Za-z0-9_]', '_', key)}.wav"
        with wave.open(str(path), "wb") as w:
            w.setnchannels(nch)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(pcm[:n * 2 * nch])
        return {"file": path.relative_to(self.mod_root).as_posix(), "name": str(audio.get("name") or "")[:120],
                "seconds": round(seconds, 2), "rate": rate, "channels": nch}

    def _voice_read_custom(self, ed):
        """(rate, [array('h') per channel]) of a custom line's saved audio."""
        path = self.mod_root / Path(*ed["file"].split("/"))
        with wave.open(str(path), "rb") as w:
            nch, rate, frames = w.getnchannels(), w.getframerate(), w.readframes(w.getnframes())
        samples = array("h")
        samples.frombytes(frames)
        if array("h", [1]).tobytes() != b"\x01\x00":
            samples.byteswap()
        return rate, [samples[c::nch] for c in range(nch)]

    # ---------------------------------------------------------------- building the Custom voice mod
    @mutates_library
    def _voice_build(self, character):
        """Writes (or removes) the Custom voice mod for a character from its saved edits, and brings the left-out-file
        bookkeeping and the ticked state in line. Returns {"problems": [plain sentences]}."""
        data = self._voice_load()
        rec = data["characters"].get(character)
        unit_key = self._voice_unit_key(character)
        unit_dir = self._unit_dir(unit_key)
        edits = (rec or {}).get("edits") or {}
        if not edits:
            self._voice_drop(character)
            return {"problems": []}
        bases = self._voice_bases(character)
        files, problems, used = {}, [], {}
        cache = {}
        for slot, base in sorted(bases.items()):
            kind, stem = slot.split(":")
            if base is None:
                continue
            try:
                blob = base["path"].read_bytes()
                ents = ve.parse(blob)
            except (OSError, ve.VoiceEditError) as e:
                problems.append(f"{base['label']}: {e}")
                continue
            groups = ve.group_lines(ents)
            repl = {}
            for key, ed in edits.items():
                for i in groups.get(key, []):
                    if ed["mode"] == "mute":
                        repl[i] = ve.SILENT_FWAV
                    elif ed["mode"] == "custom":
                        _rate, _n, _sec = ve.sound_format(ve.sound_bytes(blob, ents[i]))
                        want = _n
                        ck = (key, want)
                        if ck not in cache:
                            rate, chans = self._voice_read_custom(ed)
                            cache[ck] = ve.encode_sound(rate, chans, want)
                        repl[i] = cache[ck]
            used[slot] = dict(base, written=bool(repl))
            if repl:
                sub1, sub2, prefix = KIND_PREFIX[kind]
                files[f"{sub1}/{sub2}/{prefix}{stem}.bars"] = ve.rebuild(blob, repl)
        if not files:
            self._voice_suspend(character)
            return {"problems": problems or ["There is no voice file to start from."]}
        romfs = unit_dir / "romfs"
        if romfs.is_dir():
            shutil.rmtree(romfs)
        for rel, out in files.items():
            dest = romfs / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(out)
        (unit_dir / "About this mod.txt").write_text(
            "Made by the mod manager from the voice lines you muted or replaced (Voice section of the character's card).\n"
            "Do not edit this folder by hand: change the lines in the app and it is written again.\n", encoding="utf-8")
        rec["unit"] = unit_key
        if rec.get("suspended"):                   # a base is back: the mod is ticked again if it was before
            rec["suspended"] = False
            if rec.pop("was_ticked", True):
                self._update_state(lambda state: state.__setitem__(unit_key, True))
        rec["bases"] = {slot: {"source": b["source"], "key": b["key"], "rel": b["rel"], "label": b["label"], "sig": b["sig"],
                               "written": b["written"]} for slot, b in used.items()}
        rec.setdefault("excluded", [])
        if not rec.get("created"):
            rec["created"] = True
            self._update_state(lambda state: state.__setitem__(unit_key, True))
        self._voice_save(data)
        self._voice_apply_exclusions(character)
        return {"problems": problems}

    @mutates_library
    def _voice_suspend(self, character):
        """There is nothing to start from (the voice mod it was made from is unticked and the game's files aren't set): the edits
        are kept, but the Custom voice mod is put away - it would otherwise still play the old mod's voice."""
        data = self._voice_load()
        rec = data["characters"].get(character)
        if rec is None:
            return
        unit_key = rec.get("unit") or self._voice_unit_key(character)
        unit_dir = self._unit_dir(unit_key)
        if not rec.get("suspended"):
            rec["was_ticked"] = bool(self._load_state().get(unit_key))
        self._voice_release_exclusions(character, rec, unit_key)
        shutil.rmtree(unit_dir / "romfs", ignore_errors=True)
        unit_dir.mkdir(parents=True, exist_ok=True)
        self._clear_state_prefix(unit_key)
        rec["suspended"] = True
        rec["bases"] = {}
        rec["unit"] = unit_key
        self._voice_save(data)

    @mutates_library
    def _voice_drop(self, character):
        """Removes a character's Custom voice mod, its record and its saved audio, and gives back any file left out for it."""
        data = self._voice_load()
        rec = data["characters"].get(character) or {}
        unit_key = rec.get("unit") or self._voice_unit_key(character)
        self._voice_release_exclusions(character, rec, unit_key)
        unit_dir = self._unit_dir(unit_key)
        if unit_dir.is_dir():
            shutil.rmtree(unit_dir, ignore_errors=True)
        self._clear_state_prefix(unit_key)
        shutil.rmtree(self._voice_custom_dir(character), ignore_errors=True)
        data["characters"].pop(character, None)
        self._voice_save(data)

    def _voice_release_exclusions(self, character, rec, unit_key):
        """Puts back the files of other mods that were left out on behalf of the Custom voice mod."""
        excluded = self._load_excluded_files()
        for item in rec.get("excluded") or []:
            entry = (excluded.get(item["mod"]) or {}).get(self._norm_rel(item["path"]))
            if entry and entry.get("kept_from") == unit_key and self._unit_exists(item["mod"]):
                self.include_files(item["mod"], [item["path"]])
        rec["excluded"] = []

    def _voice_apply_exclusions(self, character):
        """While the Custom voice mod is ticked, the mod its archive was made from leaves its own copy of the file out (so the
        two don't clash); when it is not ticked, everything is given back."""
        data = self._voice_load()
        rec = data["characters"].get(character)
        if not rec:
            return
        unit_key = rec.get("unit") or self._voice_unit_key(character)
        ticked = bool(self._load_state().get(unit_key)) and (self._unit_dir(unit_key) / "romfs").is_dir()
        want = []
        if ticked:
            for b in (rec.get("bases") or {}).values():
                if b["source"] == "mod" and b["key"] and b.get("written") and self._unit_exists(b["key"]):
                    item = {"mod": b["key"], "path": b["rel"]}
                    if item not in want:
                        want.append(item)
        have = rec.get("excluded") or []
        keep = []
        for item in have:
            if item in want:
                keep.append(item)
            else:
                self._voice_release_exclusions(character, {"excluded": [item]}, unit_key)
        excluded = self._load_excluded_files()
        for item in want:
            entry = (excluded.get(item["mod"]) or {}).get(self._norm_rel(item["path"]))
            if not entry or entry.get("kept_from") != unit_key:
                self.exclude_files(item["mod"], [item["path"]], reason="conflict", kept_from=unit_key)
            if item not in keep:
                keep.append(item)
        rec["excluded"] = keep
        self._voice_save(data)

    @_locked
    def sync_voice_edits(self):
        """Keeps every Custom voice mod true to its base: writes it again if the archive it was made from has changed, gives back
        left-out files when it is unticked, and forgets edits whose mod was deleted. Cheap when there are no edits."""
        try:
            data = self._voice_load()
            if not data["characters"]:
                return {"changed": 0}
            changed = 0
            for character in list(data["characters"]):
                rec = self._voice_load()["characters"].get(character) or {}
                unit_key = rec.get("unit") or self._voice_unit_key(character)
                unit_dir = self._unit_dir(unit_key)
                if rec.get("suspended"):
                    if not unit_dir.is_dir():
                        self._voice_drop(character)
                        changed += 1
                    elif any(self._voice_bases(character).values()):
                        self._voice_build(character)
                        changed += 1
                    continue
                if not (unit_dir / "romfs").is_dir():
                    self._voice_drop(character)
                    changed += 1
                    continue
                if self._load_state().get(unit_key):
                    now = {slot: (b["sig"] if b else None) for slot, b in self._voice_bases(character).items()}
                    was = {slot: b["sig"] for slot, b in (rec.get("bases") or {}).items()}
                    if {s: v for s, v in now.items() if v} != was:
                        self._voice_build(character)
                        changed += 1
                        continue
                self._voice_apply_exclusions(character)
            return {"changed": changed}
        except Exception:
            return {"changed": 0}      # (never let this get in the way of ticking a mod)

    # ---------------------------------------------------------------- what the editor shows
    def _voice_read_base(self, base):
        blob = base["path"].read_bytes()
        return blob, ve.parse(blob)

    def get_voice_summary(self, characters):
        """{character: {"known", "muted", "custom"}} - what the card's Voice row says."""
        rec = self._voice_load()["characters"]
        out = {}
        for c in characters:
            edits = (rec.get(c) or {}).get("edits") or {}
            out[c] = {"known": bool(self._voice_stems(c)),
                      "muted": sum(1 for e in edits.values() if e["mode"] == "mute"),
                      "custom": sum(1 for e in edits.values() if e["mode"] == "custom")}
        return out

    @_locked
    def _voice_base_files_status(self):
        import game_files
        return game_files.status(self.mod_root)

    def get_voice_editor(self, character):
        """Everything the voice editor window shows for a character (see ui/js/voice.js, openVoiceEditor)."""
        stems = self._voice_stems(character)
        if not stems:
            return {"success": True, "character": character, "known": False, "lines": [], "bases": [], "problems": [],
                    "game": self._voice_base_files_status(), "unit": None}
        self.sync_voice_edits()
        rec = self._voice_load()["characters"].get(character) or {}
        edits = rec.get("edits") or {}
        bases = self._voice_bases(character)
        infos, lines, problems = [], {}, []
        for slot, base in sorted(bases.items()):
            kind, stem = slot.split(":")
            if base is None:
                continue
            try:
                blob, ents = self._voice_read_base(base)
            except (OSError, ve.VoiceEditError) as e:
                problems.append(f"{base['label']}: {e}")
                continue
            infos.append({"kind": kind, "stem": stem, "source": base["source"], "label": base["label"], "key": base["key"]})
            for key, idx in ve.group_lines(ents).items():
                secs, silent = [], True
                for i in idx:
                    fw = ve.sound_bytes(blob, ents[i])
                    try:
                        secs.append(ve.sound_format(fw)[2])
                    except va.VoiceError:
                        secs.append(0.0)
                    silent = silent and ve.is_silent(fw)
                line = lines.setdefault(key, {"kind": kind, "count": 0, "seconds": 0.0, "silent": True})
                line["count"] += len(idx)
                line["seconds"] = max(line["seconds"], max(secs))
                line["silent"] = line["silent"] and silent
        out = []
        for key, info in lines.items():
            d = ve.describe(key)
            ed = edits.get(key)
            state = ed["mode"] if ed else ("silent" if info["silent"] else "normal")
            d.update(kind=info["kind"], count=info["count"], seconds=round(info["seconds"], 2), state=state, available=True,
                     custom=({"name": ed.get("name", ""), "seconds": ed.get("seconds"), "rate": ed.get("rate"), "channels": ed.get("channels")}
                             if ed and ed["mode"] == "custom" else None))
            out.append(d)
        for key in ve.MOMENTS:                     # the important moments are listed even when there is nothing to start from
            if key not in lines:
                d = ve.describe(key)
                ed = edits.get(key)
                d.update(kind=ve.line_kind(key), count=0, seconds=0, state=ed["mode"] if ed else "normal", available=False,
                         reason="file" if infos else "base",
                         custom=({"name": ed.get("name", ""), "seconds": ed.get("seconds")} if ed and ed["mode"] == "custom" else None))
                out.append(d)
        cat_rank = {c: i for i, c in enumerate(ve.CATEGORIES)}
        moment_rank = {k: i for i, k in enumerate(ve.MOMENTS)}
        out.sort(key=lambda d: (0 if d["moment"] else 1, moment_rank.get(d["key"], 0), cat_rank.get(d["category"], 99), d["label"], d["key"]))
        unit_key = rec.get("unit") or self._voice_unit_key(character)
        return {"success": True, "character": character, "known": True, "stems": stems, "lines": out, "bases": infos,
                "problems": problems, "game": self._voice_base_files_status(),
                "unit": unit_key if (self._unit_dir(unit_key) / "romfs").is_dir() else None,
                "unit_ticked": bool(self._load_state().get(unit_key)), "suspended": bool(rec.get("suspended"))}

    # ---------------------------------------------------------------- the changes the user makes
    @_locked
    def voice_set_line(self, character, key, mode, audio=None):
        """Sets one line to "normal" (undo), "mute", or "custom" (with `audio` from the page). Writes the Custom voice mod
        again and returns the editor's new state - or {"success": False, "error": plain words}."""
        if not self._voice_stems(character):
            return {"success": False, "error": "This character's voice files aren't known to the app yet."}
        if mode not in ("normal", "mute", "custom") or not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,40}", key):
            return {"success": False, "error": "That isn't a voice line."}
        data = self._voice_load()
        rec = data["characters"].setdefault(character, {"edits": {}})
        edits = rec.setdefault("edits", {})
        before = json.loads(json.dumps(edits))
        if mode == "normal":
            if edits.pop(key, None) is not None:
                try:
                    (self._voice_custom_dir(character) / f"{re.sub(r'[^A-Za-z0-9_]', '_', key)}.wav").unlink()
                except OSError:
                    pass          # (a muted line has no saved audio)
        else:
            bases = self._voice_bases(character)
            kind = ve.line_kind(key)
            can = any(b for slot, b in bases.items() if slot.startswith(kind + ":") and b)
            if not can:
                if not rec.get("edits"):
                    data["characters"].pop(character, None)
                return {"success": False, "needs_base": True, "error": (
                    "The app has no copy of this character's voice to start from. That shouldn't normally happen - the app's own "
                    "base-game-files copy (Settings > Your game's files) is supposed to always have one. Tick a voice mod for this "
                    "character, or check Settings > Your game's files is still set up correctly.")}
            present = False
            for b in bases.values():
                if b is None:
                    continue
                try:
                    present = present or key in ve.group_lines(ve.parse(b["path"].read_bytes()))
                except (OSError, ve.VoiceEditError):
                    pass
            if not present:
                if not rec.get("edits"):
                    data["characters"].pop(character, None)
                return {"success": False, "error": "This character's voice file doesn't have that line."}
            try:
                if mode == "custom":
                    edits[key] = dict(self._voice_store_custom(character, key, audio or {}), mode="custom")
                else:
                    edits[key] = {"mode": "mute"}
            except ve.VoiceEditError as e:
                return {"success": False, "error": str(e)}
        self._voice_save(data)
        try:
            res = self._voice_build(character)
        except (ve.VoiceEditError, OSError, va.VoiceError) as e:
            data = self._voice_load()
            if before:
                data["characters"].setdefault(character, {})["edits"] = before
            else:
                data["characters"].pop(character, None)
            self._voice_save(data)
            return {"success": False, "error": f"Couldn't write the voice file: {e}"}
        state = self.get_voice_editor(character)
        state["build_problems"] = res["problems"]
        return state

    @_locked
    def voice_mute_all(self, character):
        """Mutes every line the character's voice files have (menu select sound, race lines, horns), in one rewrite of the
        Custom voice mod. Lines that already have the user's own sound are left as they are, and so are lines that are silent
        in the starting archive. Returns the editor's new state, like `voice_set_line`."""
        if not self._voice_stems(character):
            return {"success": False, "error": "This character's voice files aren't known to the app yet."}
        bases = {slot: b for slot, b in self._voice_bases(character).items() if b}
        if not bases:
            return {"success": False, "needs_base": True, "error": (
                "The app has no copy of this character's voice to start from. Tick a voice mod for this character, or check "
                "Settings > Your game's files is still set up correctly.")}
        audible = set()
        for b in bases.values():
            try:
                blob, ents = self._voice_read_base(b)
            except (OSError, ve.VoiceEditError):
                continue
            for key, idx in ve.group_lines(ents).items():
                if not all(ve.is_silent(ve.sound_bytes(blob, ents[i])) for i in idx):
                    audible.add(key)
        data = self._voice_load()
        rec = data["characters"].setdefault(character, {"edits": {}})
        edits = rec.setdefault("edits", {})
        before = json.loads(json.dumps(edits))
        todo = [k for k in sorted(audible) if (edits.get(k) or {}).get("mode") != "custom"]
        if not todo:
            if not edits:
                data["characters"].pop(character, None)
            return self.get_voice_editor(character)
        for key in todo:
            edits[key] = {"mode": "mute"}
        self._voice_save(data)
        try:
            res = self._voice_build(character)
        except (ve.VoiceEditError, OSError, va.VoiceError) as e:
            data = self._voice_load()
            if before:
                data["characters"].setdefault(character, {})["edits"] = before
            else:
                data["characters"].pop(character, None)
            self._voice_save(data)
            return {"success": False, "error": f"Couldn't write the voice file: {e}"}
        state = self.get_voice_editor(character)
        state["build_problems"] = res["problems"]
        return state

    @_locked
    def voice_reset_all(self, character):
        """Undoes every edit for a character (removes its Custom voice mod)."""
        self._voice_drop(character)
        return self.get_voice_editor(character)

    def get_voice_line_clip(self, character, key, which="current"):
        """One sound of a line as a playable .wav: {"success", "wav", "seconds", "name", "silent"}. `which` "original" is the
        base archive's sound; "current" is what is in the Custom voice mod (the original where the line is unchanged)."""
        if not isinstance(key, str):
            return {"success": False, "error": "That isn't a voice line."}
        bases = self._voice_bases(character)
        rec = self._voice_load()["characters"].get(character) or {}
        unit_key = rec.get("unit") or self._voice_unit_key(character)
        for slot, base in sorted(bases.items()):
            if base is None:
                continue
            kind, stem = slot.split(":")
            path = base["path"]
            if which == "current":
                sub1, sub2, prefix = KIND_PREFIX[kind]
                mine = self._unit_dir(unit_key) / "romfs" / sub1 / sub2 / f"{prefix}{stem}.bars"
                if mine.is_file():
                    path = mine
            try:
                blob = path.read_bytes()
                ents = ve.parse(blob)
            except (OSError, ve.VoiceEditError) as e:
                return {"success": False, "error": str(e)}
            idx = ve.group_lines(ents).get(key)
            if not idx:
                continue
            # the plain sound of the line (no number, no _END) if there is one
            pick = sorted(idx, key=lambda i: (bool(re.search(r"(_END|\d)$", ents[i]["name"])), ents[i]["name"]))[0]
            try:
                rate, _n, chans = va.decode_bfwav(ve.sound_bytes(blob, ents[pick]))
            except va.VoiceError as e:
                return {"success": False, "error": f"Couldn't play this sound: {e}."}
            secs = len(chans[0]) / rate
            return {"success": True, "wav": base64.b64encode(va.to_wav(rate, chans)).decode("ascii"), "seconds": round(secs, 2),
                    "name": ents[pick]["name"], "silent": secs < ve.SILENT_SECONDS}
        return {"success": False, "error": "This line isn't in the character's voice file."}
