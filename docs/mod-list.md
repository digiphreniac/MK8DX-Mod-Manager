# Sharing your mod list (Export and Import)

Settings has a **Share your mod list** card. **Export** saves the mods you have selected, with their GameBanana links, to one JSON file.
**Import** reads such a file, downloads those mods and selects them. It exists so a person can share a whole setup, and so a bug can be
reproduced from someone's exact mods. The code is `src/mod_list.py` (the file format, pure data), the `Api` methods in `mod_manager.py`
(`build_mod_list`, `export_mod_list`, `read_mod_list`, `import_mod_list_item`) and `src/ui/js/mod-list.js` (the card's buttons and the
Import window).

Import is offered in two places: the Settings card, and the closing "You're all set" page of Setup, where it is only a small link at the bottom of
the screen, under the card (`setup-wizard.js`) that opens a short explanation and the button (`btn-setup-import-mod-list`) - most people have no list, so
it takes no room until clicked. It is the same window either way and it stacks above the Setup overlay.

## What the file holds

`{"format": "mk8dx-mod-list", "version": 1, "app_version", "exported_at", "note", "mods": [...], "not_shared": [...]}`. Each mod is:

| Field | Meaning |
| --- | --- |
| `item`, `category` | what it is filed under (`Birdo`, `characters`) - the same names the download uses |
| `mod_id`, `record_type` | the GameBanana id, and `Mod` or `Sound` (the two have separate counters) |
| `name`, `author`, `url` | to show a person; the link is `profile_url` |
| `files` | the file ids that were downloaded and are selected |
| `units` | each selected folder: its `file_id`, `sub` (the folder inside the mod's own folder, `""` for the mod itself) and the `left_out` files with their reason |

`"looks"` (optional, so a list from before it still reads) holds, for each character, course and vehicle part whose ticked mods are
**all** in the list, `{"kind", "item", "name", "icons_confirmed"}` (`Api._mod_list_looks()`): the name its menus get (the one typed or
guessed - `null` for none of its own) and whether its icons were approved **as the mods ship them**. Icons the sharer changed - a picture
of their own, one taken from a mod's loose files or the Select screen picture, a made course picture, or pictures turned down
(`_own_icons()`) - make that `false`: those are not in the file, so the importer will see something else. The one exception is a
version of a mod's **own** loose icon pictures chosen from several (`use_loose_icon_set()`, e.g. a Mario mod that ships two sets): the
importer has the same files, so the entry gets `"icon_set": {"mod_id", "record_type", "set"}` and stays approved. Which version was
chosen is stored with the pictures (`"set"`); for one chosen before that was kept, `_chosen_icon_set()` recognises it by its pictures
(each is stored under its hash - `ui_setup.icon_picture()`). An item with a ticked mod
that isn't shared (added by hand) has no entry: what was approved for it is a set of mods the importer won't have.

The file never holds a path on the exporter's computer. A selected folder is matched to its GameBanana download through where that file
was downloaded (`downloaded_to`), and `sub` is what comes after the mod's own folder - so a mod the author has renamed since still lands on
the right folders when imported (its folder is looked up again after downloading, not rebuilt from the old name).

**Not included**: custom icons (only whether icons were approved - see `looks` above), voice edits, notes, the clash priorities, and every mod that was **added by hand** (no GameBanana
record, so no link). Those mods are listed in `not_shared` with the reason, and Export names them in the message it shows. The window
says that custom icons, voices and notes are not included, in the Settings card, the Import window and the Export message.

## Import

The page reads the file (`read_mod_list`), shows how many mods there are and how many are here already, and on **Import**
asks the backend for one mod at a time (`import_mod_list_item`), so it can show progress, stop between mods, and end with a report of
what could not be installed. For each mod:

1. a mod whose files are all downloaded here already is not downloaded again; otherwise its GameBanana page is fetched and the listed files
   are downloaded with the normal download (so a pack is filed under the thing it replaces, like any download);
2. the listed folders are selected through `save_checked` (adds ticks only - **import never unticks anything**), and the listed files are
   left out through `exclude_files`.

Once every mod is in, the page calls `import_mod_list_looks(mods, looks)`: for each item whose ticked mods all came from this list
(one that also has mods of the importer's own is a set nobody has looked at, so it is left alone) it gives the item the list's name
(or turns down a guess the sharer turned down), **marks the Name approved** whatever it is, and marks the Icons approved when the sharer
approved them as the mods ship them and the importer hasn't changed them either. With an `icon_set` it first chooses that version
of the mod's pictures here (`_apply_list_icons()`) - never over pictures of the importer's own, which then stay unapproved. Closing the Import window after an import goes to
**Choose mods** to look over what came in (`showImportedMods()` in `mod-list.js`); from Setup's closing page this also finishes Setup,
as its "Start choosing mods" button does, and from Settings it closes Settings.

What is reported, instead of hidden: a GameBanana page that couldn't be reached; a file that is no longer on the page (the author updated
the mod - the file id changes, so the person has to find the new version in Browse GameBanana); a download that failed; a selected folder
that wasn't there after downloading; and entries in the file the app can't use.

## The file is untrusted

A list comes from another person, so `mod_list.parse_mod_list()` / `clean_entry()` rebuild every entry from only the fields the app uses
and refuse anything that could reach outside the data folder: the category must be one of the app's own (`characters`, `courses`, `items`,
`vehicles`, `wheels`, `gliders`), the item name has no slash, ids are positive integers, and `sub` and left-out paths are relative with no
`..` or drive. An unusable entry is skipped and listed; it does not fail the rest. `import_mod_list_item` checks its entry again, because
the page is what passes it in. Import never runs anything from the file; it only downloads from GameBanana by id.
