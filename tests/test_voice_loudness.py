"""The voice editor's loudness matching: measuring a line's loudness, re-gaining it to the game's own level, and warning when a rebuilt
voice file is getting too big.

Run from the repo root:  python -m unittest discover -s tests

Everything here is built in memory or in a temporary folder - no game files and no network. The voice archives themselves (.bars)
aren't needed: the maths works on plain audio, and the Api helpers are given the pieces they would otherwise read from disk.
"""
import math
import shutil
import sys
import tempfile
import unittest
from array import array
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import mod_manager as mm  # noqa: E402
import voice_api          # noqa: E402,F401  (the mixin the Api's voice methods come from)
import voice_dsp as dsp   # noqa: E402
import voice_edit as ve   # noqa: E402

RATE = 22050


def tone(amplitude, seconds=1.0, channels=1, freq=440.0):
    """int16 PCM, one array per channel: a sine at `amplitude` (1.0 = full scale)."""
    n = int(RATE * seconds)
    samples = [int(amplitude * 32767 * math.sin(2 * math.pi * freq * i / RATE)) for i in range(n)]
    return [array("h", samples) for _ in range(channels)]


def peak(channels):
    return max(max(abs(v) for v in c) for c in channels)


class MeasuringLoudness(unittest.TestCase):
    def test_a_full_scale_sine_is_about_minus_3_dbfs(self):
        self.assertAlmostEqual(dsp.rms_dbfs(tone(1.0)), -3.01, delta=0.1)

    def test_halving_the_level_takes_6_db_off(self):
        self.assertAlmostEqual(dsp.rms_dbfs(tone(0.5)), dsp.rms_dbfs(tone(1.0)) - 6.02, delta=0.1)

    def test_a_stereo_clip_with_one_silent_side_averages_the_two(self):
        loud = tone(0.5)[0]
        stereo = [loud, array("h", [0] * len(loud))]
        self.assertAlmostEqual(dsp.rms_dbfs(stereo), dsp.rms_dbfs([loud]) - 3.01, delta=0.1)

    def test_silence_and_nothing_cannot_be_measured(self):
        self.assertIsNone(dsp.rms_dbfs([array("h", [0] * 1000)]))
        self.assertIsNone(dsp.rms_dbfs([]))
        self.assertIsNone(dsp.rms_dbfs([array("h")]))

    def test_the_target_matches_the_games_own_median(self):
        self.assertAlmostEqual(dsp.LOUD_TARGET_DBFS, -14.65, delta=0.05)
        self.assertGreater(dsp.QUIET_DBFS_MARGIN, 0)


class BoostingToTheGamesLevel(unittest.TestCase):
    def assertAtTarget(self, channels, delta=0.5):
        self.assertAlmostEqual(dsp.rms_dbfs(channels), dsp.LOUD_TARGET_DBFS, delta=delta)

    def test_quiet_clips_are_brought_up_to_the_target(self):
        for amp in (0.02, 0.08):
            with self.subTest(amplitude=amp):
                self.assertAtTarget(dsp.boost_to_game_loudness(tone(amp), RATE))

    def test_loud_clips_are_brought_down_to_the_target(self):
        for amp in (0.3, 0.95):
            with self.subTest(amplitude=amp):
                self.assertAtTarget(dsp.boost_to_game_loudness(tone(amp), RATE))

    def test_nothing_ever_goes_past_the_limiter_ceiling(self):
        for amp in (0.05, 0.95, 1.0):
            with self.subTest(amplitude=amp):
                out = dsp.boost_to_game_loudness(tone(amp), RATE)
                self.assertLessEqual(peak(out), round(dsp.LOUD_CEILING * 32767) + 1)

    def test_the_length_and_the_channel_count_are_kept(self):
        for channels in (1, 2):
            src = tone(0.1, seconds=0.5, channels=channels)
            out = dsp.boost_to_game_loudness(src, RATE)
            self.assertEqual((len(out), len(out[0])), (channels, len(src[0])))

    def test_the_result_is_int16_and_the_input_is_left_alone(self):
        src = tone(0.1)
        before = list(src[0])
        out = dsp.boost_to_game_loudness(src, RATE)
        self.assertEqual(out[0].typecode, "h")
        self.assertEqual(list(src[0]), before)

    def test_both_sides_of_a_stereo_clip_get_the_same_treatment(self):
        out = dsp.boost_to_game_loudness(tone(0.1, channels=2), RATE)
        self.assertEqual(list(out[0]), list(out[1]))

    def test_stereo_balance_is_kept(self):
        left, right = tone(0.4)[0], tone(0.1)[0]
        out = dsp.boost_to_game_loudness([left, right], RATE)
        self.assertGreater(dsp.rms_dbfs([out[0]]) - dsp.rms_dbfs([out[1]]), 3.0)   # (the left side started 12 dB louder)

    def test_a_nearly_silent_clip_is_lifted_only_as_far_as_the_gain_cap_allows(self):
        src = tone(0.002)
        out = dsp.boost_to_game_loudness(src, RATE)
        self.assertGreater(dsp.rms_dbfs(out), dsp.rms_dbfs(src) + 10)                # (it is brought up...)
        self.assertLess(dsp.rms_dbfs(out), dsp.LOUD_TARGET_DBFS - 6)                 # (...but not all the way: the gain is capped)

    def test_silence_stays_silence_and_nothing_stays_nothing(self):
        out = dsp.boost_to_game_loudness([array("h", [0] * 500)], RATE)
        self.assertEqual(set(out[0]), {0})
        self.assertEqual(dsp.boost_to_game_loudness([], RATE), [])
        empty = dsp.boost_to_game_loudness([array("h")], RATE)
        self.assertEqual((len(empty), len(empty[0])), (1, 0))

    def test_boosting_twice_changes_almost_nothing(self):
        once = dsp.boost_to_game_loudness(tone(0.05), RATE)
        twice = dsp.boost_to_game_loudness(once, RATE)
        self.assertAlmostEqual(dsp.rms_dbfs(once), dsp.rms_dbfs(twice), delta=0.5)


class LoudnessOfASound(unittest.TestCase):
    """ve.loudness_dbfs reads the game's own sound format, which is what the editor measures a saved line in."""

    def test_it_agrees_with_the_audio_it_was_made_from(self):
        for amp in (0.05, 0.3):
            with self.subTest(amplitude=amp):
                src = tone(amp)
                fwav = dsp.make_fwav(RATE, src)
                self.assertAlmostEqual(ve.loudness_dbfs(fwav), dsp.rms_dbfs(src), delta=1.5)   # (the encoding is lossy)

    def test_a_boosted_line_measures_louder_than_the_original(self):
        quiet = tone(0.03)
        before = ve.loudness_dbfs(dsp.make_fwav(RATE, quiet))
        after = ve.loudness_dbfs(dsp.make_fwav(RATE, dsp.boost_to_game_loudness(quiet, RATE)))
        self.assertGreater(after - before, 10)

    def test_silence_and_junk_have_no_loudness(self):
        self.assertIsNone(ve.loudness_dbfs(ve.SILENT_FWAV))
        self.assertIsNone(ve.loudness_dbfs(b"this is not a sound"))


class ApiHelpers(unittest.TestCase):
    CHARACTER = "Mario"

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="mk8dx-loud-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.master = self.root / "data"
        self.master.mkdir()
        self.api = mm.Api(self.master)

    # -- a custom line's saved audio --------------------------------------------------------------------------------------
    def test_a_regained_line_is_written_back_where_it_is_read_from(self):
        ed = {"file": "voice-custom/Mario/line.wav"}
        (self.master / "voice-custom" / "Mario").mkdir(parents=True)
        for channels in (1, 2):
            with self.subTest(channels=channels):
                src = tone(0.2, seconds=0.2, channels=channels)
                self.api._voice_write_custom(ed, RATE, src)
                rate, back = self.api._voice_read_custom(ed)
                self.assertEqual(rate, RATE)
                self.assertEqual([list(c) for c in back], [list(c) for c in src])

    # -- how big a rebuilt voice file may get -----------------------------------------------------------------------------
    def _vanilla(self, kind_folder, **sizes):
        folder = self.master / "game-files" / "current" / "Audio" / kind_folder
        folder.mkdir(parents=True, exist_ok=True)
        for name, size in sizes.items():
            (folder / name).write_bytes(b"\0" * size)

    def test_the_ceiling_is_the_biggest_vanilla_file_of_that_kind(self):
        self._vanilla("Driver", **{"Driver_A.bars": 100, "Driver_B.bars": 300, "Driver_C.bars": 200})
        (self.master / "game-files" / "current" / "Audio" / "Driver" / "notes.txt").write_bytes(b"\0" * 999)
        self._vanilla("DriverMenu", **{"MenuDriver_A.bars": 50})
        self.assertEqual(self.api._voice_size_ceiling("race"), 300)
        self.assertEqual(self.api._voice_size_ceiling("menu"), 50)

    def test_there_is_no_ceiling_without_the_games_files(self):
        self.assertIsNone(self.api._voice_size_ceiling("race"))

    def _custom_voice(self, race_bytes=None, menu_bytes=None):
        """A Custom voice mod for the character with its voice files at the given sizes."""
        stem = self.api._voice_stems(self.CHARACTER)[0]
        unit = f"characters/{self.CHARACTER}/Custom voice"
        romfs = self.master / "mods" / "extracted" / Path(*unit.split("/")) / "romfs" / "Audio"
        for kind_folder, prefix, size in (("Driver", "Driver_", race_bytes), ("DriverMenu", "MenuDriver_", menu_bytes)):
            if size is not None:
                (romfs / kind_folder).mkdir(parents=True, exist_ok=True)
                (romfs / kind_folder / f"{prefix}{stem}.bars").write_bytes(b"\0" * size)
        self.api._voice_load = lambda: {"characters": {self.CHARACTER: {"unit": unit, "edits": {}}}}
        return stem

    def test_the_size_levels(self):
        self._vanilla("Driver", **{"Driver_Big.bars": 1000})
        for size, level in ((500, "ok"), (849, "ok"), (850, "warn"), (999, "warn"), (1000, "over"), (1500, "over")):
            with self.subTest(size=size):
                stem = self._custom_voice(race_bytes=size)
                [entry] = self.api._voice_sizes(self.CHARACTER)
                self.assertEqual((entry["level"], entry["stem"], entry["bytes"], entry["ceiling"]), (level, stem, size, 1000))
                self.assertAlmostEqual(entry["fraction"], size / 1000)

    def test_without_the_games_files_nothing_is_flagged(self):
        self._custom_voice(race_bytes=5000)
        [entry] = self.api._voice_sizes(self.CHARACTER)
        self.assertEqual((entry["level"], entry["fraction"], entry["ceiling"]), ("ok", None, None))

    def test_only_race_voice_files_are_checked(self):
        self._vanilla("Driver", **{"Driver_Big.bars": 1000})
        self._vanilla("DriverMenu", **{"MenuDriver_Big.bars": 100})
        self._custom_voice(race_bytes=100, menu_bytes=5000)   # (a menu file far over its own vanilla size - not a known problem)
        self.assertEqual([e["kind"] for e in self.api._voice_sizes(self.CHARACTER)], ["race"])

    def test_a_character_with_no_custom_voice_has_no_sizes(self):
        self.api._voice_load = lambda: {"characters": {}}
        self.assertEqual(self.api._voice_sizes(self.CHARACTER), [])
        self._custom_voice()   # (a record, but no voice files written yet)
        self.assertEqual(self.api._voice_sizes(self.CHARACTER), [])

    # -- boosting a line --------------------------------------------------------------------------------------------------
    def _boost_setup(self, edits, quiet_lines=()):
        """Wires an Api so voice_boost_line/voice_boost_all run on in-memory audio; returns what they did."""
        log = {"written": {}, "built": 0}
        self.api._voice_load = lambda: {"characters": {self.CHARACTER: {"unit": "x", "edits": edits}}}
        self.api._voice_read_custom = lambda ed: (RATE, tone(0.02, seconds=0.3))

        def write(ed, rate, chans):
            log["written"][ed["file"]] = chans
        self.api._voice_write_custom = write

        def build(character):
            log["built"] += 1
            return {"problems": ["a build note"]}
        self.api._voice_build = build
        self.api.get_voice_editor = lambda character: {"success": True, "lines": [{"key": k, "loud_level": "quiet"} for k in quiet_lines]
                                                       + [{"key": "FINE", "loud_level": "ok"}]}
        return log

    def test_boosting_one_line_regains_it_and_rebuilds_the_voice_once(self):
        log = self._boost_setup({"GOL_TOP": {"mode": "custom", "file": "a.wav"}})
        state = self.api.voice_boost_line(self.CHARACTER, "GOL_TOP")
        self.assertTrue(state["success"])
        self.assertEqual(state["build_problems"], ["a build note"])
        self.assertEqual(log["built"], 1)
        self.assertAlmostEqual(dsp.rms_dbfs(log["written"]["a.wav"]), dsp.LOUD_TARGET_DBFS, delta=0.5)

    def test_only_a_line_with_the_users_own_sound_can_be_boosted(self):
        log = self._boost_setup({"MUTED": {"mode": "mute"}})
        for key in ("MUTED", "NOT_EDITED"):
            with self.subTest(key=key):
                self.assertFalse(self.api.voice_boost_line(self.CHARACTER, key)["success"])
        self.assertEqual((log["written"], log["built"]), ({}, 0))

    def test_boost_all_regains_only_the_quiet_lines_in_one_rebuild(self):
        edits = {"A": {"mode": "custom", "file": "a.wav"}, "B": {"mode": "custom", "file": "b.wav"},
                 "FINE": {"mode": "custom", "file": "fine.wav"}, "MUTED": {"mode": "mute"}}
        log = self._boost_setup(edits, quiet_lines=("A", "B", "MUTED"))
        state = self.api.voice_boost_all(self.CHARACTER)
        self.assertTrue(state["success"])
        self.assertEqual(sorted(log["written"]), ["a.wav", "b.wav"])   # (not the fine one, and not the muted one)
        self.assertEqual(log["built"], 1)

    def test_boost_all_does_nothing_when_no_line_is_quiet(self):
        log = self._boost_setup({"FINE": {"mode": "custom", "file": "fine.wav"}})
        self.assertTrue(self.api.voice_boost_all(self.CHARACTER)["success"])
        self.assertEqual((log["written"], log["built"]), ({}, 0))

    def test_a_failure_is_reported_in_plain_words_not_raised(self):
        log = self._boost_setup({"A": {"mode": "custom", "file": "a.wav"}}, quiet_lines=("A",))

        def unreadable(ed):
            raise OSError("the saved sound is gone")
        self.api._voice_read_custom = unreadable
        for result in (self.api.voice_boost_line(self.CHARACTER, "A"), self.api.voice_boost_all(self.CHARACTER)):
            self.assertFalse(result["success"])
            self.assertIn("gone", result["error"])
        self.assertEqual(log["built"], 0)

        self.api._voice_read_custom = lambda ed: (RATE, tone(0.02, seconds=0.1))

        def cannot_build(character):
            raise OSError("disk full")
        self.api._voice_build = cannot_build
        for result in (self.api.voice_boost_line(self.CHARACTER, "A"), self.api.voice_boost_all(self.CHARACTER)):
            self.assertFalse(result["success"])
            self.assertIn("disk full", result["error"])


if __name__ == "__main__":
    unittest.main()
