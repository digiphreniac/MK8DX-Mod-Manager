# Sharing your mod list (Export and Import)

Settings has a **Share your mod list** card. **Export** saves the mods you have selected, with their GameBanana links, to one JSON file.
**Import** reads such a file, downloads those mods and selects them. It exists so a person can share a whole setup, and so a bug can be
reproduced from someone's exact mods. The code is `src/mod_list.py` (the file format, pure data), the `Api` methods in `mod_manager.py`
(`build_mod_list`, `export_mod_list`, `read_mod_list`, `import_mod_list_item`) and `src/ui/js/mod-list.js` (the card's buttons and the
Import window).

## What the file holds

`{"format": "mk8dx-mod-list", "version": 1, "app_version", "exported_at", "note", "mods": [...], "not_shared": [...]}`. Each mod is:

| Field | Meaning |
| --- | --- |
| `item`, `category` | what it is filed under (`Birdo`, `characters`) - the same names the download uses |
| `mod_id`, `record_type` | the GameBanana id, and `Mod` or `Sound` (the two have separate counters) |
| `name`, `author`, `url` | to show a person; the link is `profile_url` |
| `files` | the file ids that were downloaded and are selected |
| `units` | each selected folder: its `file_id`, `sub` (the folder inside the mod's own folder, `""` for the mod itself) and the `left_out` files with their reason |

The file never holds a path on the exporter's computer. A selected folder is matched to its GameBanana download through where that file
was downloaded (`downloaded_to`), and `sub` is what comes after the mod's own folder - so a mod the author has renamed since still lands on
the right folders when imported (its folder is looked up again after downloading, not rebuilt from the old name).

**Not included**: custom icons and names, voice edits, notes, the clash priorities, and every mod that was **added by hand** (no GameBanana
record, so no link). Those mods are listed in `not_shared` with the reason, and Export names them in the message it shows. The window
says that custom icons, voices and notes are not included, in the Settings card, the Import window and the Export message.

## Import

The page reads the file (`read_mod_list`), shows how many mods there are and how many are here already, and on **Download and select**
asks the backend for one mod at a time (`import_mod_list_item`), so it can show progress, stop between mods, and end with a report of
what could not be installed. For each mod:

1. a mod whose files are all downloaded here already is not downloaded again; otherwise its GameBanana page is fetched and the listed files
   are downloaded with the normal download (so a pack is filed under the thing it replaces, like any download);
2. the listed folders are selected through `save_checked` (adds ticks only - **import never unticks anything**), and the listed files are
   left out through `exclude_files`.

What is reported, instead of hidden: a GameBanana page that couldn't be reached; a file that is no longer on the page (the author updated
the mod - the file id changes, so the person has to find the new version in Browse GameBanana); a download that failed; a selected folder
that wasn't there after downloading; and entries in the file the app can't use.

## The file is untrusted

A list comes from another person, so `mod_list.parse_mod_list()` / `clean_entry()` rebuild every entry from only the fields the app uses
and refuse anything that could reach outside the data folder: the category must be one of the app's own (`characters`, `courses`, `items`,
`vehicles`, `wheels`, `gliders`), the item name has no slash, ids are positive integers, and `sub` and left-out paths are relative with no
`..` or drive. An unusable entry is skipped and listed; it does not fail the rest. `import_mod_list_item` checks its entry again, because
the page is what passes it in. Import never runs anything from the file; it only downloads from GameBanana by id.
