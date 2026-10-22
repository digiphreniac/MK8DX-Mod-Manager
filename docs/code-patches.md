# Code patches (exefs .ips)

Code patches that ship as `.ips` files rather than romfs files.

## Code patches (exefs `.ips`), not just romfs

Some mods - most of the **Mechanics** category (a coin cap, a version
backport, ...) - change no romfs data at all; they ship IPS patches for the
game's executable, one file per game build, named after its build id
(`<32 hex chars>.ips`). These are first-class mergeable units:

- **Discovery** (`find_exefs_units()`): any folder outside a `romfs/` that
  directly holds a `<hex>.ips` file - the mod's own `exefs/` (Ryujinx-style
  layout, which is what most mods ship), `exefs/<name>/`, or an author-shipped
  `atmosphere/exefs_patches/<name>/`. The unit key is that folder's path. A
  mod with both a romfs and a patch gets two separate units, so the patch is
  always its own deliberate tick ("Select All" skips patches).
- **Staging** (`Api.merge()`): each checked patch unit is copied to
  `sd-card-staging/atmosphere/exefs_patches/mk8dxmm_<mod name>_<hash>/<BUILD ID>.ips`
  (upper-case build id, lower-case `.ips`). This is Atmosphere's own layout -
  the loader scans every set under `atmosphere/exefs_patches/`, applies only
  files whose name matches the running game's build id, and stacks patches from
  several sets. It ignores `.ips32`, `.pchtxt`, `.IPS` and non-hex names, so
  those are never staged (the log says when one was ignored). The
  `mk8dxmm_` prefix is what lets a re-merge delete exactly its own previous
  patch sets without touching sigpatches or anything else already on the SD.
- **Conflicts** (`_compute_exefs()`): both patch formats (`PATCH`/`EOF` and
  `IPS32`/`EEOF`, RLE records included) are parsed, and two checked patches
  for the same build id that write *different* bytes to an overlapping range
  conflict, reported with the pseudo-path `exefs/<build id>@0x<offset>`.
  Identical bytes are fine. There's no saved-preference resolution for these
  (half a patch can't be dropped) - one has to be unchecked. What this can't
  see is *logical* incompatibility between patches that touch different bytes.
- **Game version**: a patch built for a different build does nothing, with no
  error. `KNOWN_BUILD_IDS` maps the ids whose version is confirmed (deliberately
  short - unknown ids just show their raw id), and the optional "Game build ID"
  in Settings flags patches that don't target the user's own build ("wrong game
  version" badge + a merge-log warning).

Course mods that ship their own exefs patch (e.g. a music-related one) used
to have it silently dropped by the merge; it now shows up as its own unchecked
"code patch" unit next to the course's romfs unit.
