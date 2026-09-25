// One request for the same question asked twice at once.
// A screen draws several things at the same moment, and several of them ask the backend the same read-only question (the flow
// bar, the footer, every tile's conflict check, ...). While a call is still waiting for its answer, an identical call (same
// method, same arguments) gets that same answer instead of starting another - so nothing is ever older than one round trip.
// Only questions whose answer nobody changes afterwards are listed here (a caller that edits what it got, like the views'
// unit lists, must not share it).
(function () {
  const SHARED = ["get_flow_status", "get_master_dir_status", "check_conflicts", "get_all_conflicts", "get_stats",
                  "get_pack_links", "get_course_icon_preview", "get_exefs_unit_info", "get_unit_slots"];
  function install() {
    const api = window.pywebview && window.pywebview.api;
    if (!api || api.__coalesced) return;
    for (const name of SHARED) {
      const original = api[name];
      if (typeof original !== "function") continue;
      const inflight = new Map();
      api[name] = function (...args) {
        let key;
        try { key = JSON.stringify(args); } catch (e) { return original.apply(api, args); }
        if (inflight.has(key)) return inflight.get(key);
        const call = Promise.resolve(original.apply(api, args));
        inflight.set(key, call);
        const done = () => { if (inflight.get(key) === call) inflight.delete(key); };
        call.then(done, done);
        return call;
      };
    }
    try { Object.defineProperty(api, "__coalesced", { value: true }); } catch (e) { api.__coalesced = true; }
  }
  window.addEventListener("pywebviewready", install);
  install();   // (already ready when this loads)
})();
