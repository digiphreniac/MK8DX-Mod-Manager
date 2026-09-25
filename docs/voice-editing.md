# Voice editing

Muting a character's voice line or using your own sound, and what is proven about the game's voice files.

## Voice editing: mute a line, or use your own sound

A character's card has a **Voice** row (**Edit voice lines**). Like **Name** and **Icons**, it is dimmed ("Comes after
you pick a mod", no Edit button) until the character has a ticked mod - `attachVoiceRow()`'s `setEnabled()`, fed by the card's `refresh()`.
The character's own *Custom voice* mod doesn't count toward that, so it can't keep the row open after the real mod is unticked
(existing edits aren't touched - the row just can't be opened until a mod is ticked again). The window lists the character's voice lines - the four
*important moments* first (character select, finish first, finish mid-pack, finish last), then every other line by category -
each with a short description, a play button, and **Mute** / **Use my own...**. A handful of lines say "Unknown" instead of
a description - nobody's traced what triggers them (checked against real Switch hardware, and two modder references - see
`voice_edit.LINES`'s header comment); play one to hear what it is rather than trust a guess dressed up as fact.

### What the game's voice files are (and what is proven)

* Each character has two archives: `romfs/Audio/DriverMenu/MenuDriver_<slot>.bars` (the character-select sound: one, sometimes
  two sounds) and `romfs/Audio/Driver/Driver_<slot>.bars` (73-82 sounds used during a race, horns included). `<slot>` is the
  game's own name for the character (`DRIVER_SLOTS` in `mod_manager.py`). A voice mod replaces a whole archive.
* An archive ("BARS") is a header, a table of name hashes, a table of offsets, one small metadata block (AMTA) per sound, then the
  sounds themselves (FWAV/BFWAV files), each starting on a 0x40 boundary. Names can share one sound's data (`START_GLIDE` and
  `START_GLIDE2`). All 1,959 sounds in the 60 archives of the author's mods are DSP-ADPCM (the format of every voice in the
  game), little-endian (one sound is big-endian), 1958 of them with no loop; 87 % mono; sample rates from 8 to 48 kHz (59 % at
  32 kHz); 0.005 to 6.7 seconds. Mods mix rates and lengths freely, so a new sound does not have to match the one it replaces.
* **Proven on a real Switch** (hand-built test mods, `audio-test-mods/`): swapping chosen sounds of a real archive for a tiny
  silent sound works in both kinds of archive - other sounds are untouched, and the metadata blocks need no change (mods that
  work on the Switch leave them as they were, even when a sound is replaced by 0.005 s of silence). The silent sound used is a
  copy, byte for byte, of the one in a mod known to work.
* **Finish sounds** (heard on the Switch): `GOL_TOP` plays when you finish first, `GOL_GOD` mid-pack (heard at 4th), `GOL_BAD` at
  the end (heard at last). Each is three sounds: the plain one, a `2` variant and an `_END` tail; which of the three plays when
  is not known, so a line is always changed as a whole.
* **Also proven on a real Switch**: a custom sound made by `voice_dsp.py` plays correctly, in both a race line and a menu
  select sound, in full, with the rest of the character's voice and the rest of the game unaffected (tests 3-4 in
  `audio-test-mods/`). **Not proven**: lines longer than 6.7 seconds (the app limits a line to 8; test 5, skipped so far).

### How it works

* A **line** is what a player thinks of as one thing the character says. In the archive it is one or more sounds; the line's
  key is the sound's name without the character's code and without the number / `_END` (`pVO_BMR_GOL_TOP_END` -> `GOL_TOP`;
  menu sounds are `M_SELECT_CHAR`; horns `HORN_ON` / `HORN_OFF` / `HORN_ON_SP`). `voice_edit.LINES` holds each line's label,
  description, and how sure the description is (`sure` - heard on a Switch or plainly said by the name; `likely` - the name
  and the game make it clear, or an outside source backs it up; `unknown` - no source or reading pins it down, so the
  description just says "Unknown" instead of a dressed-up guess). Any sound the list doesn't recognise at all gets the same
  treatment - a plain "not identified yet" description rather than being hidden.
* **Muting** swaps every sound of the line for the silent sound. **Use my own** takes an audio file the user chooses: the *page*
  reads it (`decodeAudioData` - mp3, wav, ogg, m4a, flac..., whatever the browser plays - brought to 32 kHz), shows it as a
  waveform to pick the part (drag, or start/end), can cut the quiet ends, previews it, and sends the 16-bit samples; the app
  keeps them as a `.wav` in `voice-custom/<character>/` and encodes them into the sounds of the line: the same channel count
  as each sound it replaces (mono is doubled, stereo averaged), rate kept as sent. Up to 8 seconds.
* **Loudness.** The author's real race lines measure a median -14.7 dBFS (RMS) with a crest factor (peak / average) around 4.7 -
  compressed, "mastered" audio. Plain speech has a crest factor of 10-17 (quiet most of the time, brief loud syllables), so simply
  raising a recording's *peak* to just under full scale (the first version of this) left it 9-11 dB quieter on average than the
  game's own voice - confirmed on a Switch ("a bit too quiet" / "almost too quiet to hear over the music"). "Match the game's own
  voice volume" (on by default) instead: a soft compressor brings the crest factor down near the game's, then a gain is searched
  for (the limiter that follows would eat into a single-shot guess) to bring the *result* to that -14.7 dBFS target, then a smooth
  (tanh) limiter catches any remaining peaks by bending them toward the ceiling rather than flattening them (`matchGameLoudness()`
  in `src/ui/js/voice.js`; checked afterward: well under 1% of samples in the processed test audio come near the ceiling, and the
  encoder's accuracy is unaffected). Unticked, the audio is used as decoded, unprocessed.
* **The starting archive.** Changing one line means writing the whole archive again, so the app needs the archive as the game
  would otherwise use it: the copy in a *ticked* voice mod for that slot (that is what the game would play; one left out of the
  merge is skipped), else the app's own base-game-files copy (`game_files.find_current_voice()` - see [Base game files](base-game-files.md#base-game-files-a-required-local-copy);
  required since Setup, so this is now the normal case for a character with no voice mod ticked). With neither - a character
  whose `DRIVER_SLOTS` code isn't known, or a base-files copy that's somehow missing - the editor says so plainly rather than
  guessing.
* **The Custom voice mod.** The result is an ordinary mod, `mods/extracted/characters/<Character>/Custom voice/romfs/Audio/...`
  (only the archives that have an edit), ticked when it is first made and merged by Commit like any mod. Its tick is the
  user's: unticking it turns the edits off without losing them.
* **The mod it was made from** would clash with the Custom voice mod on the same file, so while the Custom voice mod is ticked the
  app leaves that mod's copy of the file out of the merge (an ordinary left-out file, `kept_from` = the Custom voice mod, visible
  in its Files list) and puts it back when the Custom voice mod is unticked, removed, or has no edits left. Only the archives the
  Custom voice mod actually writes are left out.
* **When the starting archive changes** - another voice mod is ticked or this one unticked, the game folder is set or cleared -
  `sync_voice_edits()` writes the archive again from the new base (custom lines are encoded again from the saved audio). It runs
  when ticks are saved, the mod list is loaded, a mod is removed, before a commit, and when the editor opens; it does nothing (and
  costs nothing) when there are no edits. If there is no starting archive any more the edits are **kept but paused** - the Custom
  voice mod is put away (it would otherwise keep playing the old mod's voice) and comes back by itself when a base is back.
* **Commit** picks the Custom voice mod's archives up like any other file; the commit signature includes the voice edits (only
  when there are some, so an earlier commit is not called stale), so changing a line makes the last commit stale.
* A muted **select sound** is not a sound to play: the tile's click plays nothing and its tooltip says nothing about it
  (`get_select_voice` / `_select_voice_source` treat a sound shorter than 0.05 s as silent).
* The Api calls take turns (a lock), because the window can call from several threads at once.

### Encoding (`voice_dsp.py`)

DSP-ADPCM is 4 bits a sample in 8-byte frames of 14 samples: a header byte (predictor number, scale) and 7 bytes of nibbles.
The encoder works out a good predictor pair for every frame, groups the frames into the eight predictors a sound may carry,
then for each frame tries the two best predictors at the finest scale at which every value still fits, following the decoder's
own integer arithmetic sample by sample. Silence stays silence. A few seconds encode in well under a second (pure Python).
The `.bfwav` written is laid out exactly like the game's own: `make_fwav()` of a silent stereo 48 kHz sound is byte for byte the
silent sound of a working mod, and for real mono and stereo sounds of several sizes every header, INFO and padding byte comes out
identical to the real file (only the coefficients and the audio differ). Real speech comes back at 38-43 dB signal-to-noise,
a game voice line decoded and encoded again at 41 dB.

### Tests

`p28` (archive rewriting on all 60 real archives, line grouping), `p29` (muting through the Api), `p30` (the encoder and
layout), `p31` (custom audio through the Api), `p32` (everything on a read-only copy of the author's real data: no new clashes,
a tick with edits present takes 0.2 s, the real folder byte-for-byte untouched), `p33` (commit staleness, concurrent clicks).
