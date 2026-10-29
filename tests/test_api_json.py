"""Every Api method's answer must survive the trip to the page as JSON.

In a pywebview window the bridge is in-process and forgiving. In browser mode (how Linux runs - docs/browser-mode.md)
the same answer is written as JSON, pushed through a socket and parsed by the browser, which is stricter in two ways:

  - a set, a Path or bytes raises TypeError. Loud, and web_server turns it into a failed call the page can report.
  - **NaN and Infinity do not.** `json.dumps(float("nan"))` succeeds and writes `NaN`, which is not JSON at all;
    JSON.parse then rejects the WHOLE answer, so the call fails with a parse error nowhere near the method that
    produced the number. web_server passes allow_nan=False so that one is loud too - and this file keeps it from
    arising in the first place.

What is checked here: every public method that CAN be called with no arguments is either called for real against a
throwaway data folder and its answer round-tripped through strict JSON, or listed in NOT_CALLED with a reason. A new
one belongs to a list, and the test says so if it belongs to neither - otherwise this would quietly cover less and
less of the Api as the app grows.

A method that needs arguments is not called here: making up arguments for it would mean guessing what it does, and
several of them write to the user's files. Those are covered at run time instead, by web_server passing
allow_nan=False - which turns the silent failure into a named one. The gap is counted below, not hidden.
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import mod_manager as mm      # noqa: E402
import web_server             # noqa: E402

# Called for real. All read-only, all local (nothing here goes to GameBanana), all callable with no arguments.
CALLED = [
    "build_mod_list", "can_pick_folders", "get_all_conflicts", "get_app_version", "get_base_files_status",
    "get_character_view", "get_commit_progress", "get_course_view", "get_cup_icons", "get_default_settings",
    "get_diagnostics", "get_excluded_files", "get_flow_status", "get_game_versions", "get_guessed_names",
    "get_item_icons", "get_items_view", "get_known_shared_files", "get_master_dir_status", "get_mods",
    "get_pack_links", "get_settings", "get_simple_categories_view", "get_staging_status", "get_stats",
    "get_ui_locales", "get_ui_setup", "get_vehicle_icons", "get_vehicles_view", "ui_icon_worklist",
]

# Not called, and why. Keep the reasons accurate: they are what a reader checks when deciding whether a method
# could be moved into CALLED.
NOT_CALLED = {
    # Would open a dialog and wait for a person.
    "export_mod_list": "opens a Save dialog", "read_mod_list": "opens an Open dialog",
    "pick_folder": "opens a folder picker", "pick_master_dir": "opens a folder picker",
    "pick_base_files_source": "opens a folder picker",
    # Would start another program.
    "show_log_file": "opens the log in a file manager", "open_staging_folder": "opens a file manager",
    # Would change the user's files, settings or ticks.
    "clear_all_mods": "deletes mods", "complete_setup": "writes settings",
    "use_default_master_dir": "moves the data folder", "use_recommended_staging_dir": "moves the staging folder",
    "mark_switch_done": "writes settings", "sync_auto_names": "writes names",
    "sync_part_pictures": "writes pictures", "sync_voice_edits": "writes voice edits",
    "warm_ui_analysis": "starts the background warm-up",
}


def _needs_arguments(name):
    """True when the method cannot be called with no arguments at all (so it is not a candidate for CALLED)."""
    import inspect
    try:
        parameters = list(inspect.signature(getattr(mm.Api, name)).parameters.values())[1:]
    except (ValueError, TypeError):
        return True
    return any(p.default is inspect.Parameter.empty and p.kind in (p.POSITIONAL_OR_KEYWORD, p.POSITIONAL_ONLY)
               for p in parameters)


def as_the_page_would_see_it(value):
    """The value after the round trip the browser puts it through. Raises if it cannot make the trip."""
    return json.loads(json.dumps(value, allow_nan=False))


def describe(value, path="result"):
    """Where in a nested answer the trouble is - "result['stats']['per_day'][2]" rather than just "a float"."""
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return f"{path} is {value!r}, which is not JSON (NaN and Infinity cannot be sent to the page)"
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, (str, int, float, bool, type(None))):
                return f"{path} has the key {key!r} ({type(key).__name__}), which JSON cannot name"
            found = describe(item, f"{path}[{key!r}]")
            if found:
                return found
        return None
    if isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            found = describe(item, f"{path}[{i}]")
            if found:
                return found
        return None
    if not isinstance(value, (str, int, float, bool, type(None))):
        return f"{path} is a {type(value).__name__}, which cannot be sent to the page"
    return None


class EveryMethodIsAccountedFor(unittest.TestCase):
    """The guard that keeps this file honest as the Api grows."""

    def setUp(self):
        self.methods = set(web_server.api_methods(mm.Api))
        self.callable_now = {n for n in self.methods if not _needs_arguments(n)}

    def test_every_method_that_could_be_called_is_either_called_or_has_a_reason_not_to_be(self):
        unclassified = self.callable_now - set(CALLED) - set(NOT_CALLED)
        self.assertEqual(unclassified, set(),
                         "New Api method(s) that take no arguments and are listed nowhere here. Add each to CALLED "
                         "(read-only, nothing on the network, changes nothing) or to NOT_CALLED with the reason.")

    def test_the_lists_do_not_name_methods_that_are_gone(self):
        stale = (set(CALLED) | set(NOT_CALLED)) - self.methods
        self.assertEqual(stale, set(), "These are listed here but are no longer public methods of Api.")

    def test_nothing_is_in_both_lists(self):
        self.assertEqual(set(CALLED) & set(NOT_CALLED), set())

    def test_the_called_ones_really_do_take_no_arguments(self):
        for name in CALLED:
            self.assertFalse(_needs_arguments(name), f"{name} needs arguments, so it cannot be in CALLED")

    def test_every_reason_for_not_calling_is_written_down(self):
        for name, reason in NOT_CALLED.items():
            self.assertTrue(reason and reason.strip(), f"{name} has no reason")

    def test_the_run_time_backstop_for_everything_else_is_still_there(self):
        # Most of the Api needs arguments and so is never called here. What stops one of those writing NaN into an
        # answer the browser then refuses WHOLE is web_server's allow_nan=False. If that line goes, this gap reopens.
        source = (Path(__file__).resolve().parent.parent / "src" / "web_server.py").read_text(encoding="utf-8")
        self.assertIn("allow_nan=False", source)

    def test_the_size_of_the_gap_is_stated_rather_than_hidden(self):
        # Not a threshold to chase - a number that makes the uncovered part of the Api visible to whoever reads this.
        uncalled = len(self.methods) - len(CALLED)
        self.assertGreater(len(CALLED), 25, "the directly-checked set has shrunk; was something dropped from CALLED?")
        self.assertLess(len(CALLED) / len(self.methods), 1.0)
        print(f"\n  [api-json] {len(CALLED)} of {len(self.methods)} Api methods answered and checked here; "
              f"{uncalled} rely on web_server's allow_nan=False at run time "
              f"({len(self.methods - self.callable_now)} of them because they need arguments).")


class TheAnswersSurviveTheTrip(unittest.TestCase):
    """Calls each read-only method and sends its answer through strict JSON.

    With one mod on disk and ticked, rather than an empty folder: an empty library answers `{}` to half of these,
    and `{}` proves nothing. A ticked mod gives the views, the stats (which carry percentages - the obvious place
    for a division to produce NaN), the flow and the mod list something real to describe. What is still not
    covered is anything that needs the base game's files, which are the user's own and cannot be in a test."""

    @classmethod
    def setUpClass(cls):
        cls.parent = Path(tempfile.mkdtemp(prefix="mk8dx-apijson-"))
        # mods/extracted/<category>/<item>/<mod name>/romfs/... - the layout docs/architecture.md describes.
        romfs = cls.parent / "mods" / "extracted" / "characters" / "Mario" / "Test Mod" / "romfs"
        (romfs / "ui" / "Menu").mkdir(parents=True)
        (romfs / "ui" / "Menu" / "cmn.bntx").write_bytes(b"\0" * 32)
        cls.api = mm.Api(cls.parent)
        loaded = cls.api.get_mods()
        cls.api.save_checked({"characters/Mario/Test Mod": True}, loaded["epoch"])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.parent, ignore_errors=True)

    def test_the_fixture_really_is_there(self):
        # If the mod stopped being found, every test below would pass on empty answers and mean nothing.
        self.assertEqual(self.api.get_mods()["categories"]["characters"], ["Mario/Test Mod"])
        self.assertTrue(self.api.get_mods()["checked"], "the fixture mod is not ticked")
        self.assertGreater(self.api.get_stats()["extracted_bytes"], 0)

    def test_each_read_only_method_answers_with_something_the_page_can_read(self):
        for name in CALLED:
            with self.subTest(method=name):
                answer = getattr(self.api, name)()
                trouble = describe(answer)
                self.assertIsNone(trouble, f"{name}() -> {trouble}")
                as_the_page_would_see_it(answer)        # (and strict json.dumps agrees with describe())

    def test_an_answer_is_unchanged_by_the_round_trip(self):
        # Not just "it can be written": a tuple becomes a list, an int key becomes a string. The page gets what the
        # backend meant only when the value comes back equal to itself.
        for name in CALLED:
            with self.subTest(method=name):
                answer = getattr(self.api, name)()
                self.assertEqual(as_the_page_would_see_it(answer), answer,
                                 f"{name}() does not come back the same through JSON (tuple? a non-string key?)")


class TheCheckItselfWorks(unittest.TestCase):
    """If describe() cannot spot these, the tests above prove nothing."""

    def test_it_catches_nan_and_infinity(self):
        for bad in (float("nan"), float("inf"), float("-inf")):
            self.assertIn("not JSON", describe({"a": [1, {"b": bad}]}) or "")

    def test_it_says_where_the_trouble_is(self):
        self.assertIn("['stats']['per_day'][1]", describe({"stats": {"per_day": [1, float("nan")]}}))

    def test_it_catches_types_json_has_no_word_for(self):
        for bad in ({1, 2}, Path("/x"), b"bytes", object()):
            self.assertIn("cannot be sent to the page", describe({"a": bad}) or "")

    def test_it_catches_a_key_json_cannot_name(self):
        self.assertIn("JSON cannot name", describe({("a", "b"): 1}))

    def test_it_passes_ordinary_answers(self):
        for fine in ({"ok": True, "n": 3, "x": 1.5, "s": "t", "none": None}, [1, 2, 3], "text", None, 0):
            self.assertIsNone(describe(fine))

    def test_a_tuple_is_allowed_through_but_does_not_come_back_the_same(self):
        # describe() lets it pass (JSON can write it), which is why the round-trip test above exists as well.
        self.assertIsNone(describe({"a": (1, 2)}))
        self.assertNotEqual(as_the_page_would_see_it({"a": (1, 2)}), {"a": (1, 2)})


if __name__ == "__main__":
    unittest.main()
