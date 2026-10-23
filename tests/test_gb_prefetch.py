"""Fetching a card's first Browse GameBanana page ahead of time (Api.gb_prefetch), and the short-lived page cache that makes it count.

Run from the repo root:  python -m unittest discover -s tests

Nothing here touches the network: the page fetch and the Browse calls are replaced by recorders.
"""
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import gamebanana_api as gb  # noqa: E402
import mod_manager as mm     # noqa: E402


class PageCache(unittest.TestCase):
    def setUp(self):
        gb._page_cache.clear()
        self.calls = []
        self._real = gb._get_json
        gb._get_json = lambda url: (self.calls.append(url), {"_aRecords": [{"n": 1}]})[1]
        self.addCleanup(setattr, gb, "_get_json", self._real)
        self.addCleanup(gb._page_cache.clear)

    def test_a_page_asked_twice_is_fetched_once(self):
        a = gb._get_json_cached("https://example.test/page1")
        b = gb._get_json_cached("https://example.test/page1")
        self.assertEqual(a, b)
        self.assertEqual(len(self.calls), 1)

    def test_different_pages_are_fetched_separately(self):
        gb._get_json_cached("https://example.test/page1")
        gb._get_json_cached("https://example.test/page2")
        self.assertEqual(len(self.calls), 2)

    def test_the_caller_can_change_what_it_got_without_changing_the_cache(self):
        first = gb._get_json_cached("https://example.test/page1")
        first["_aRecords"].append("junk")
        self.assertEqual(gb._get_json_cached("https://example.test/page1"), {"_aRecords": [{"n": 1}]})

    def test_an_old_page_is_fetched_again(self):
        gb._get_json_cached("https://example.test/page1")
        gb._page_cache["https://example.test/page1"] = (time.monotonic() - gb.PAGE_CACHE_TTL - 1, {"old": True})
        self.assertEqual(gb._get_json_cached("https://example.test/page1"), {"_aRecords": [{"n": 1}]})
        self.assertEqual(len(self.calls), 2)

    def test_the_cache_stays_small(self):
        for i in range(gb._PAGE_CACHE_MAX + 20):
            gb._get_json_cached(f"https://example.test/page{i}")
        self.assertLessEqual(len(gb._page_cache), gb._PAGE_CACHE_MAX)

    def test_a_failed_fetch_is_not_remembered(self):
        def boom(url):
            raise gb.GameBananaError("offline")
        gb._get_json = boom
        with self.assertRaises(gb.GameBananaError):
            gb._get_json_cached("https://example.test/page1")
        gb._get_json = lambda url: {"ok": True}
        self.assertEqual(gb._get_json_cached("https://example.test/page1"), {"ok": True})


class Prefetch(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="mk8dx-pf-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        (self.root / "data").mkdir()
        self.api = mm.Api(self.root / "data")
        self.api._GB_PREFETCH_DELAY = 0.05
        self.calls = []
        for name in ("gb_browse", "gb_browse_course", "gb_browse_vehicle", "gb_browse_item"):
            setattr(self.api, name, lambda *a, _n=name, **k: self.calls.append((_n,) + a))

    def settle(self):
        """Waits for the background worker to finish what it was given."""
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with self.api._prefetch_lock:
                if not self.api._prefetch_busy:
                    return
            time.sleep(0.02)
        self.fail("the prefetch worker never finished")

    def test_it_returns_at_once_and_fetches_the_first_page_with_the_default_sort(self):
        t0 = time.monotonic()
        self.assertEqual(self.api.gb_prefetch("characters", "Mario"), {"started": True})
        self.assertLess(time.monotonic() - t0, 0.04)
        self.settle()
        self.assertEqual(self.calls, [("gb_browse", "Mario", 1, "most_liked")])

    def test_each_kind_uses_its_own_browse(self):
        self.api.gb_prefetch("courses", "Wii Moo Moo Meadows")
        self.settle()
        self.api.gb_prefetch("items", "Banana")
        self.settle()
        wheel = "Standard"
        self.api.gb_prefetch("wheels", wheel)
        self.settle()
        self.assertEqual(self.calls, [("gb_browse_course", "Wii Moo Moo Meadows", 1), ("gb_browse_item", "Banana", 1, "most_viewed"),
                                      ("gb_browse_vehicle", wheel, 1, "most_viewed")])

    def test_the_users_saved_sort_is_used(self):
        self.api.save_settings({"gb_browse_sort": "newest"})
        self.api.gb_prefetch("characters", "Luigi")
        self.settle()
        self.assertEqual(self.calls, [("gb_browse", "Luigi", 1, "newest")])

    def test_only_the_newest_card_is_fetched_when_cards_are_flicked_through(self):
        for name in ("Mario", "Luigi", "Peach", "Daisy"):
            self.api.gb_prefetch("characters", name)
        self.settle()
        self.assertEqual(self.calls, [("gb_browse", "Daisy", 1, "most_liked")])

    def test_a_list_fetched_a_moment_ago_is_not_fetched_again(self):
        self.api.gb_prefetch("characters", "Mario")
        self.settle()
        self.api.gb_prefetch("characters", "Mario")
        self.settle()
        self.assertEqual(len(self.calls), 1)

    def test_every_item_shares_one_list_and_so_does_each_kind_of_part(self):
        self.api.gb_prefetch("items", "Banana")
        self.settle()
        self.api.gb_prefetch("items", "Red Shell")
        self.settle()
        self.assertEqual(len(self.calls), 1)
        self.api.gb_prefetch("wheels", "Standard")
        self.settle()
        self.api.gb_prefetch("wheels", "Monster")
        self.settle()
        self.assertEqual([c[0] for c in self.calls], ["gb_browse_item", "gb_browse_vehicle"])

    def test_something_it_cannot_fetch_for_is_ignored(self):
        self.api.gb_prefetch("ui", "anything")
        self.api.gb_prefetch("wheels", "No Such Part")
        self.settle()
        self.assertEqual(self.calls, [])

    def test_an_error_while_fetching_never_gets_out(self):
        def boom(*a):
            raise RuntimeError("GameBanana is down")
        self.api.gb_browse = boom
        self.api.gb_prefetch("characters", "Mario")
        self.settle()   # (the worker ends normally)
        self.api.gb_prefetch("characters", "Luigi")   # (and can be used again)
        self.settle()


if __name__ == "__main__":
    unittest.main()
