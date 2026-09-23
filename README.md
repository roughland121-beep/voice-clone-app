# Voice Clone Reader

A free, local desktop app: give it a short sample of your voice, paste in a
script (in *any* language), and it reads the script out loud in your voice
as an MP3 — using the open-source **Coqui XTTS-v2** model. Runs entirely on
your own computer — no API keys, no subscription, no per-use cost.

Only clone your own voice, or a voice you have explicit permission to use.

## What's new in this version

- **Uses your GPU/CPU to the fullest** — tries an NVIDIA GPU first, then an
  AMD/Intel GPU via DirectML, then falls back to *every* CPU core (with the
  extra threading/perf flags turned on either way).
- **No practical script length limit, in any language** — long scripts are
  automatically split into pieces and stitched back into one seamless file.
- **Auto-translate** — type or paste your script in *any* language; if you
  pick a different reading language from the dropdown, it's translated
  automatically before being read aloud. Turn this off with the checkbox
  if you want the script read exactly as typed.
- **MP3 output** — generated audio is exported as an .mp3, no separate
  ffmpeg install needed.
- **Recorded samples are auto-saved** to a folder you choose (shown and
  changeable right in Step 1), with a timestamped filename each time.
- **Nicer UI**, and a real portable-.exe build script (see below).

## 1. Install (one-time, Windows)

1. Make sure you have **Python 3.9, 3.10, or 3.11** installed (get it from
   [python.org](https://www.python.org/downloads/) if not — check "Add
   python.exe to PATH" during setup).
2. Put all the files from this folder together in one place.
3. Double-click **`install.bat`**.

That's it — it finds your Python install, sets up an isolated environment,
installs everything needed (a few GB, so it takes a while), and adds a
**"Voice Clone Reader" shortcut to your Desktop**.

(macOS/Linux users: skip `install.bat` and instead run the manual commands
in the "Manual install" section below.)

## 2. Run it

Double-click the **"Voice Clone Reader"** shortcut on your Desktop.

The very first time you click "Generate speech" inside the app, it will
download the XTTS-v2 voice model (~2 GB) — that needs internet and happens
once. After that, generation works completely offline (auto-translate is
the one feature that always needs internet, since it calls Google
Translate's free web service — untick its checkbox for a fully offline run).

## Manual install (macOS/Linux, or if install.bat doesn't work for you)

```bash
cd voice-clone-app
python -m venv venv

# Activate the virtual environment:
# macOS/Linux:
source venv/bin/activate
# Windows:
venv\Scripts\activate

pip install -r requirements.txt
python main.py
```

## 3. How to use it

1. **Voice sample** — click "Browse file..." to pick an existing recording
   of your voice (wav/mp3/etc, 10–30 seconds of clear, single-speaker
   speech works best), or click "Record from microphone" to record one on
   the spot, then click it again to stop. Mic recordings are automatically
   saved into the folder shown under "Save recorded samples to:" — click
   "Change..." to pick a different folder.
2. **Script** — paste your text into the box (any language), or load it
   from a .txt file. Pick the language you want it *read in* from the
   dropdown. Leave "Auto-translate" checked if your script isn't already
   in that language.
3. Click **"Generate speech (MP3)"**. This can take anywhere from a few
   seconds to a few minutes depending on your computer, script length, and
   whether a GPU is being used.
4. Click **"Play result"** to listen, or **"Save as..."** to export the
   .mp3 (or .wav, if MP3 conversion couldn't run on your system).

## 4. Turn it into a portable .exe

Once you've done step 1 (`install.bat` has been run), double-click:

```
build_portable_exe.bat
```

This runs PyInstaller and produces
`dist\VoiceCloneReader\VoiceCloneReader.exe`. Copy the whole
`dist\VoiceCloneReader` folder wherever you like (a USB drive, another
Windows PC, etc.) — everything it needs is bundled inside it, so anyone
can just double-click the .exe from then on without installing Python.

Notes on the .exe:
- It's **large** (several GB) because PyTorch and the TTS engine are
  bundled in, and the build itself can take **10–20+ minutes** — that's
  normal, don't close the window.
- The first time someone clicks "Generate speech" on a given machine, it
  still needs to download the ~2GB voice model once (needs internet that
  one time).
- If you already have an `urdu_model` folder set up (see below), the
  script copies it into the portable build automatically. If you set up
  Urdu *after* building, just copy the `urdu_model` folder next to
  `VoiceCloneReader.exe` yourself.
- If a build fails, the error will almost always name a missing package —
  add `--collect-all <that package>` to the `pyinstaller` command inside
  `build_portable_exe.bat` and run it again.

## Urdu support (optional)

The base model doesn't include Urdu, but a community fine-tuned version
does. Setting it up takes a few extra steps because it's a separate,
much larger model:

1. Go to https://huggingface.co/suhaibrashid17/XTTS-v2-Urdu-FT/tree/main
2. Download these 4 files into a new folder called `urdu_model` inside
   `voice-clone-app` (so you'll have `voice-clone-app\urdu_model\config.json`,
   etc.):
   - `config.json`
   - `model.pth` (this one is **~5.65 GB** — it's a big download)
   - `vocab.json`
   - `tokenizer.py`
3. Run `setup_urdu.bat` once. This patches your installed TTS library so
   it understands Urdu text (it backs up the original file first, so
   it's reversible).
4. Open the app, pick **"ur - Urdu"** from the Language dropdown, and
   generate as normal. Auto-translate will convert any other-language
   script into Urdu first if the checkbox is on.

## Notes & troubleshooting

- **Quality**: works best with a clean sample — minimal background noise,
  one speaker, natural pace.
- **Speed**: first load of the model each session is slow (loading into
  memory); generation after that is faster. An NVIDIA GPU is fastest, an
  AMD/Intel GPU via DirectML is next, all-CPU-cores is the fallback.
- **Long scripts**: no practical limit — long scripts are automatically
  split into pieces and stitched back into one file, in every language.
- **Auto-translate**: uses Google Translate's free web endpoint via the
  `deep-translator` package, so it needs internet and isn't 100%
  guaranteed for every language pair. If it fails for any reason, the app
  quietly falls back to reading your script exactly as typed rather than
  stopping with an error.
- **MP3 conversion**: if it ever fails on your system for some reason, the
  app automatically hands you the .wav instead rather than losing the
  generated audio.
