"""
Voice Clone Reader
-------------------
A free, local desktop app that clones your voice from a short audio sample
and reads any script you give it out loud, using Coqui TTS's open-source
XTTS-v2 voice-cloning model. Everything runs on your own computer -
no API keys, no subscriptions, no cloud calls after the model is downloaded
(script auto-translation is the one feature that uses the internet, since
it calls Google Translate's free web endpoint - turn it off if you want a
fully offline run).

IMPORTANT / ETHICS:
Only use this to clone your own voice, or a voice you have explicit
permission to clone. Do not use it to impersonate other people without
their consent.

Setup:
    pip install -r requirements.txt
    python main.py

First run will download the XTTS-v2 model (~2GB) - needs internet once.
After that, everything works offline (except auto-translate, see above).
"""

import os
import sys

# Windows' default console encoding can't display some characters that
# libraries print at startup (like emoji in coqui-tts's banner). Force
# UTF-8 so those prints don't crash the app.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import json
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import wave
import tempfile
import time
import datetime

APP_TITLE = "Voice Clone Reader"
SUPPORTED_SAMPLE_EXTS = [("Audio files", "*.wav *.mp3 *.flac *.m4a"), ("All files", "*.*")]
SUPPORTED_TEXT_EXTS = [("Text files", "*.txt"), ("All files", "*.*")]

# Base folder = wherever main.py (or the frozen .exe) lives, so this works
# both when run from source and when packaged with PyInstaller.
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Folder holding the downloaded Urdu fine-tune (config.json, model.pth, vocab.json)
URDU_MODEL_DIR = os.path.join(BASE_DIR, "urdu_model")
SETTINGS_PATH = os.path.join(BASE_DIR, "app_settings.json")
DEFAULT_SAMPLES_DIR = os.path.join(BASE_DIR, "saved_voice_samples")

LANGUAGES = ["en", "es", "fr", "de", "it", "pt", "pl", "tr", "ru", "nl", "cs", "ar", "zh-cn", "ja", "hu", "ko", "ur"]
LANGUAGE_NAMES = {
    "en": "English", "es": "Spanish", "fr": "French", "de": "German", "it": "Italian",
    "pt": "Portuguese", "pl": "Polish", "tr": "Turkish", "ru": "Russian", "nl": "Dutch",
    "cs": "Czech", "ar": "Arabic", "zh-cn": "Chinese", "ja": "Japanese", "hu": "Hungarian",
    "ko": "Korean", "ur": "Urdu",
}
# deep-translator wants slightly different codes for a couple of these
TRANSLATOR_CODE = {"zh-cn": "zh-CN"}

# ---------------------------------------------------------------- settings

def load_settings():
    defaults = {"samples_folder": DEFAULT_SAMPLES_DIR}
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        defaults.update(data)
    except Exception:
        pass
    return defaults


def save_settings(settings):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except Exception:
        pass  # never let a settings-save failure crash the app


# Lazy imports for heavy libs so the GUI opens instantly even before
# dependencies finish installing / model loads.
_tts_model = None
_tts_lock = threading.Lock()
_fast_tts_model = None
_urdu_model = None
_urdu_lock = threading.Lock()
_ffmpeg_ready = False


def get_tts_model(status_callback=None, fast_mode=False):
    """Load (and cache) the voice-cloning model. Downloads it on first use.

    fast_mode=True loads YourTTS instead of XTTS-v2: noticeably faster on
    CPU, at the cost of a less accurate voice match and no Urdu support.
    """
    global _tts_model, _fast_tts_model
    with _tts_lock:
        cached = _fast_tts_model if fast_mode else _tts_model
        if cached is None:
            # XTTS normally asks you to type "y" in the terminal to accept its
            # license the first time it downloads. The app has no console
            # attached to answer that prompt, so we auto-accept it here.
            os.environ["COQUI_TOS_AGREED"] = "1"
            model_name = (
                "tts_models/multilingual/multi-dataset/your_tts"
                if fast_mode
                else "tts_models/multilingual/multi-dataset/xtts_v2"
            )
            if status_callback:
                label = "fast" if fast_mode else "standard"
                status_callback(f"Loading {label} voice model (first run downloads it, please wait)...")
            from TTS.api import TTS  # imported here so app starts fast

            device = _pick_best_device(status_callback)
            model = TTS(model_name=model_name, progress_bar=False)
            device = _move_model_to_device(model, device, status_callback)
            if fast_mode:
                _fast_tts_model = model
            else:
                _tts_model = model
            if status_callback:
                status_callback(f"Model loaded on {device}.")
            return model
        return cached


def _pick_best_device(status_callback=None):
    """Try an NVIDIA GPU, then an AMD/Intel GPU via DirectML, then fall
    back to using every CPU core - and squeeze the most out of whichever
    one we land on."""
    import torch

    if torch.cuda.is_available():
        name = torch.cuda.get_device_name(0)
        torch.backends.cudnn.benchmark = True  # let cuDNN pick the fastest algorithms
        torch.backends.cuda.matmul.allow_tf32 = True
        if status_callback:
            status_callback(f"NVIDIA GPU detected ({name}) - using it for generation.")
        return "cuda"

    # Try DirectML (works with AMD/Intel GPUs on Windows). This backend is
    # experimental and doesn't support every operation, so we sanity-check
    # it with a tiny test op before trusting it.
    try:
        import torch_directml
        if torch_directml.is_available():
            dml_device = torch_directml.device()
            test = torch.tensor([1.0], device=dml_device) + torch.tensor([1.0], device=dml_device)
            _ = test.cpu()
            gpu_name = None
            try:
                gpu_name = torch_directml.device_name(torch_directml.default_device())
            except Exception:
                pass
            if status_callback:
                extra = f" ({gpu_name})" if gpu_name else ""
                status_callback(f"AMD/DirectML GPU detected{extra} - using it for generation.")
            return dml_device
    except Exception:
        pass

    # No usable GPU: let PyTorch use every physical CPU core instead of
    # just one, and turn off Python's GIL-bound thread hand-holding for
    # the math libraries underneath so they can actually run in parallel.
    cpu_count = os.cpu_count() or 4
    torch.set_num_threads(cpu_count)
    torch.set_num_interop_threads(max(1, cpu_count // 2))
    try:
        torch.set_flush_denormal(True)  # small free speed-up on CPU math
    except Exception:
        pass
    os.environ.setdefault("OMP_NUM_THREADS", str(cpu_count))
    os.environ.setdefault("MKL_NUM_THREADS", str(cpu_count))
    os.environ.setdefault("OPENBLAS_NUM_THREADS", str(cpu_count))
    if status_callback:
        status_callback(f"No GPU found - using all {cpu_count} CPU cores instead (still slower than a GPU).")
    return "cpu"


def _move_model_to_device(model, device, status_callback=None):
    """Move a model to device, falling back to CPU if that device errors out."""
    import torch

    try:
        model.to(device)
        return device
    except Exception as e:
        if status_callback:
            status_callback(f"That GPU path failed ({e}) - falling back to CPU.")
        cpu_count = os.cpu_count() or 4
        torch.set_num_threads(cpu_count)
        model.to("cpu")
        return "cpu"


def get_urdu_model(status_callback=None):
    """Load (and cache) the community Urdu fine-tune of XTTS from local files."""
    global _urdu_model
    with _urdu_lock:
        if _urdu_model is None:
            config_path = os.path.join(URDU_MODEL_DIR, "config.json")
            checkpoint_path = os.path.join(URDU_MODEL_DIR, "model.pth")
            vocab_path = os.path.join(URDU_MODEL_DIR, "vocab.json")

            missing = [p for p in (config_path, checkpoint_path, vocab_path) if not os.path.exists(p)]
            if missing:
                raise RuntimeError(
                    "Urdu model files not found in the 'urdu_model' folder next to main.py.\n"
                    "Please download config.json, model.pth, and vocab.json from:\n"
                    "https://huggingface.co/suhaibrashid17/XTTS-v2-Urdu-FT\n"
                    "and place them in that folder. Also run setup_urdu.bat once, if you haven't."
                )

            if status_callback:
                status_callback("Loading Urdu voice model (this is a large model, please wait)...")
            from TTS.tts.configs.xtts_config import XttsConfig
            from TTS.tts.models.xtts import Xtts

            device = _pick_best_device(status_callback)
            config = XttsConfig()
            config.load_json(config_path)
            model = Xtts.init_from_config(config)
            model.load_checkpoint(config, checkpoint_path=checkpoint_path, vocab_path=vocab_path, use_deepspeed=False)
            device = _move_model_to_device(model, device, status_callback)
            _urdu_model = model
            if status_callback:
                status_callback("Urdu model loaded.")
        return _urdu_model


def _chunk_text(text, max_chars=200):
    """Split arbitrarily long text into sentence-ish chunks so a single
    generation call is never handed more than the model likes. This is
    what removes any practical length limit on the script, in any language."""
    import re
    raw = re.split(r"(?<=[\u06d4\u061f!\?\.\u3002\uff01\uff1f\n])\s*", text.strip())
    raw = [s.strip() for s in raw if s.strip()]
    if not raw:
        raw = [text.strip()]

    chunks = []
    current = ""
    for sentence in raw:
        # A single sentence longer than max_chars on its own still needs
        # a hard split so it doesn't get dropped or choke the model.
        while len(sentence) > max_chars:
            chunks.append(sentence[:max_chars])
            sentence = sentence[max_chars:]
        candidate = (current + " " + sentence).strip() if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks


def generate_urdu_speech(sample_path, text, out_path, status_callback=None):
    """Generate speech using the Urdu fine-tune's own recommended settings.

    Long scripts are split into sentence-sized pieces, generated one at a
    time, and stitched back together into a single audio file - so there
    is no practical limit on how long the script can be.
    """
    import numpy as np
    import soundfile as sf
    import torch

    model = get_urdu_model(status_callback=status_callback)
    chunks = _chunk_text(text, max_chars=200)

    gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(
        audio_path=[sample_path],
        gpt_cond_len=model.config.gpt_cond_len,
        max_ref_length=model.config.max_ref_len,
        sound_norm_refs=model.config.sound_norm_refs,
    )

    sample_rate = 24000
    silence_gap = np.zeros(int(sample_rate * 0.3), dtype=np.float32)
    wav_pieces = []

    for i, chunk in enumerate(chunks):
        if status_callback:
            status_callback(f"Generating Urdu audio... part {i + 1} of {len(chunks)}")
        with torch.inference_mode():
            result = model.inference(
                text=chunk,
                language="ur",
                gpt_cond_latent=gpt_cond_latent,
                speaker_embedding=speaker_embedding,
                temperature=0.1,
                length_penalty=0.1,
                repetition_penalty=10.0,
                top_k=10,
                top_p=0.3,
            )
        wav_pieces.append(np.asarray(result["wav"], dtype=np.float32))
        if i < len(chunks) - 1:
            wav_pieces.append(silence_gap)

    full_wav = np.concatenate(wav_pieces) if wav_pieces else np.zeros(1, dtype=np.float32)
    sf.write(out_path, full_wav, sample_rate)
    return out_path


def generate_standard_speech(model, sample_path, text, language, out_path, status_callback=None):
    """Generate speech for any non-Urdu language. Chunks long scripts
    ourselves (on top of the library's own sentence splitting) so there is
    effectively no length limit, then stitches the pieces together."""
    import numpy as np
    import soundfile as sf
    import torch

    chunks = _chunk_text(text, max_chars=400)
    if len(chunks) == 1:
        with torch.inference_mode():
            model.tts_to_file(
                text=chunks[0],
                speaker_wav=sample_path,
                language=language,
                file_path=out_path,
                split_sentences=True,
            )
        return out_path

    sample_rate = 24000
    silence_gap = np.zeros(int(sample_rate * 0.3), dtype=np.float32)
    pieces = []
    tmp_dir = tempfile.mkdtemp(prefix="vcr_chunks_")
    try:
        for i, chunk in enumerate(chunks):
            if status_callback:
                status_callback(f"Generating audio... part {i + 1} of {len(chunks)}")
            part_path = os.path.join(tmp_dir, f"part_{i}.wav")
            with torch.inference_mode():
                model.tts_to_file(
                    text=chunk,
                    speaker_wav=sample_path,
                    language=language,
                    file_path=part_path,
                    split_sentences=True,
                )
            data, sr = sf.read(part_path, dtype="float32")
            pieces.append(data)
            if i < len(chunks) - 1:
                pieces.append(silence_gap)
        full = np.concatenate(pieces) if pieces else np.zeros(1, dtype=np.float32)
        sf.write(out_path, full, sample_rate)
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return out_path


def ensure_ffmpeg_ready():
    """Point pydub at the bundled ffmpeg binary from imageio-ffmpeg, so the
    user never has to separately install ffmpeg to get MP3 output."""
    global _ffmpeg_ready
    if _ffmpeg_ready:
        return
    import imageio_ffmpeg
    from pydub import AudioSegment
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    AudioSegment.converter = ffmpeg_path
    AudioSegment.ffmpeg = ffmpeg_path
    _ffmpeg_ready = True


def convert_wav_to_mp3(wav_path, mp3_path, status_callback=None):
    try:
        ensure_ffmpeg_ready()
        from pydub import AudioSegment
        if status_callback:
            status_callback("Converting to MP3...")
        audio = AudioSegment.from_wav(wav_path)
        audio.export(mp3_path, format="mp3", bitrate="192k")
        return mp3_path
    except Exception as e:
        # If MP3 conversion fails for any reason, don't lose the generated
        # audio - just hand back the WAV instead.
        if status_callback:
            status_callback(f"Could not make an MP3 ({e}) - kept the WAV instead.")
        return wav_path


def translate_script(text, target_lang, status_callback=None):
    """Translate arbitrary-language input text into target_lang using
    Google Translate's free web endpoint (via deep-translator). Long text
    is chunked to stay under the endpoint's per-request limit. If anything
    goes wrong (no internet, etc.) the original text is returned unchanged
    rather than failing the whole generation."""
    try:
        from deep_translator import GoogleTranslator
        code = TRANSLATOR_CODE.get(target_lang, target_lang)

        # Split on paragraph breaks first, then hard-wrap anything still
        # too long, to stay under Google Translate's ~5000 char limit.
        paragraphs = text.split("\n")
        chunks = []
        current = ""
        for para in paragraphs:
            candidate = (current + "\n" + para) if current else para
            if len(candidate) <= 4000:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = para
                while len(current) > 4000:
                    chunks.append(current[:4000])
                    current = current[4000:]
        if current:
            chunks.append(current)
        if not chunks:
            return text

        translator = GoogleTranslator(source="auto", target=code)
        translated_parts = []
        for i, chunk in enumerate(chunks):
            if status_callback:
                status_callback(f"Translating script to {LANGUAGE_NAMES.get(target_lang, target_lang)}... ({i + 1}/{len(chunks)})")
            translated_parts.append(translator.translate(chunk))
        return "\n".join(translated_parts)
    except Exception as e:
        if status_callback:
            status_callback(f"Translation skipped ({e}) - using the script as typed.")
        return text


class Recorder:
    """Simple microphone recorder using sounddevice, saved as WAV."""

    def __init__(self):
        self.is_recording = False
        self.frames = []
        self.samplerate = 44100
        self.channels = 1
        self.stream = None

    def start(self):
        import sounddevice as sd
        self.frames = []
        self.is_recording = True

        def callback(indata, frame_count, time_info, status):
            if self.is_recording:
                self.frames.append(indata.copy())

        self.stream = sd.InputStream(
            samplerate=self.samplerate, channels=self.channels, callback=callback
        )
        self.stream.start()

    def stop_and_save(self, path):
        import numpy as np
        self.is_recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        if not self.frames:
            return None
        audio = np.concatenate(self.frames, axis=0)
        audio_int16 = (audio * 32767).astype(np.int16)
        with wave.open(path, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)
            wf.setframerate(self.samplerate)
            wf.writeframes(audio_int16.tobytes())
        return path


# ------------------------------------------------------------------ colors
COL_BG = "#f4f6fb"
COL_CARD = "#ffffff"
COL_ACCENT = "#4f6df5"
COL_ACCENT_DARK = "#3a54d1"
COL_TEXT = "#1f2433"
COL_SUBTEXT = "#6b7280"
COL_BORDER = "#e2e5ec"


class VoiceCloneApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("820x780")
        self.root.minsize(700, 640)
        self.root.configure(bg=COL_BG)

        self.settings = load_settings()
        os.makedirs(self.settings.get("samples_folder", DEFAULT_SAMPLES_DIR), exist_ok=True)

        self.sample_path = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Ready.")
        self.language_var = tk.StringVar(value="en")
        self.fast_mode_var = tk.BooleanVar(value=False)
        self.auto_translate_var = tk.BooleanVar(value=True)
        self.samples_folder_var = tk.StringVar(value=self.settings.get("samples_folder", DEFAULT_SAMPLES_DIR))
        self.output_path = None
        self.recorder = Recorder()
        self.recording_thread = None
        self._rec_start_time = None
        self._last_was_mic_recording = False

        self._setup_style()
        self._build_ui()

    # ---------------------------------------------------------------- UI
    def _setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background=COL_BG)
        style.configure("Card.TFrame", background=COL_CARD)
        style.configure("TLabel", background=COL_BG, foreground=COL_TEXT, font=("Segoe UI", 10))
        style.configure("Card.TLabel", background=COL_CARD, foreground=COL_TEXT, font=("Segoe UI", 10))
        style.configure("Sub.TLabel", background=COL_BG, foreground=COL_SUBTEXT, font=("Segoe UI", 10))
        style.configure("CardSub.TLabel", background=COL_CARD, foreground=COL_SUBTEXT, font=("Segoe UI", 9))
        style.configure("Title.TLabel", background=COL_BG, foreground=COL_TEXT, font=("Segoe UI", 20, "bold"))
        style.configure("Heading.TLabel", background=COL_CARD, foreground=COL_TEXT, font=("Segoe UI", 11, "bold"))
        style.configure("TCheckbutton", background=COL_CARD, foreground=COL_TEXT, font=("Segoe UI", 9))
        style.configure(
            "Accent.TButton", background=COL_ACCENT, foreground="white",
            font=("Segoe UI", 10, "bold"), padding=(14, 8), borderwidth=0,
        )
        style.map("Accent.TButton", background=[("active", COL_ACCENT_DARK), ("disabled", "#a9b3d6")])
        style.configure("TButton", font=("Segoe UI", 9), padding=(10, 6))
        style.configure("TProgressbar", background=COL_ACCENT, troughcolor=COL_BORDER)

    def _card(self, parent, title=None):
        outer = ttk.Frame(parent, style="TFrame")
        card = tk.Frame(outer, bg=COL_CARD, highlightbackground=COL_BORDER, highlightthickness=1)
        card.pack(fill="both", expand=True)
        if title:
            ttk.Label(card, text=title, style="Heading.TLabel").pack(anchor="w", padx=14, pady=(12, 6))
        return outer, card

    def _build_ui(self):
        pad = {"padx": 16, "pady": 8}

        header = ttk.Frame(self.root)
        header.pack(fill="x", padx=16, pady=(16, 4))
        ttk.Label(header, text=APP_TITLE, style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="1) Add a voice sample  →  2) Paste your script  →  3) Generate an MP3 in your voice",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        # --- Step 1: voice sample ---
        step1_outer, step1 = self._card(self.root, "Step 1 · Your voice sample (10-30 sec of clear speech)")
        step1_outer.pack(fill="x", **pad)

        row1 = tk.Frame(step1, bg=COL_CARD)
        row1.pack(fill="x", padx=14, pady=4)
        self.sample_label = ttk.Label(row1, text="No sample selected", style="CardSub.TLabel")
        self.sample_label.pack(side="left", fill="x", expand=True)
        ttk.Button(row1, text="Browse file...", command=self.browse_sample).pack(side="right", padx=4)

        row2 = tk.Frame(step1, bg=COL_CARD)
        row2.pack(fill="x", padx=14, pady=(0, 6))
        self.record_btn = ttk.Button(row2, text="🎙 Record from microphone", command=self.toggle_record)
        self.record_btn.pack(side="left")
        self.record_status = ttk.Label(row2, text="", background=COL_CARD, foreground="#c0392b")
        self.record_status.pack(side="left", padx=10)

        row3 = tk.Frame(step1, bg=COL_CARD)
        row3.pack(fill="x", padx=14, pady=(0, 12))
        ttk.Label(row3, text="Save recorded samples to:", style="CardSub.TLabel").pack(side="left")
        folder_entry = ttk.Entry(row3, textvariable=self.samples_folder_var, state="readonly")
        folder_entry.pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(row3, text="Change...", command=self.choose_samples_folder).pack(side="left")

        # --- Step 2: script ---
        step2_outer, step2 = self._card(self.root, "Step 2 · Your script")
        step2_outer.pack(fill="both", expand=True, **pad)

        row4 = tk.Frame(step2, bg=COL_CARD)
        row4.pack(fill="x", padx=14, pady=(0, 6))
        ttk.Button(row4, text="Load .txt file...", command=self.load_script_file).pack(side="left")
        ttk.Label(row4, text="   Read it as:", style="CardSub.TLabel").pack(side="left", padx=(16, 4))
        lang_values = [f"{code} - {LANGUAGE_NAMES[code]}" for code in LANGUAGES]
        self.lang_display_var = tk.StringVar(value=f"en - {LANGUAGE_NAMES['en']}")
        lang_combo = ttk.Combobox(
            row4, textvariable=self.lang_display_var, width=16, state="readonly", values=lang_values
        )
        lang_combo.pack(side="left")
        lang_combo.bind("<<ComboboxSelected>>", self._on_language_selected)

        translate_row = tk.Frame(step2, bg=COL_CARD)
        translate_row.pack(fill="x", padx=14, pady=(0, 4))
        ttk.Checkbutton(
            translate_row,
            text="Auto-translate script into the selected language (script can be typed in ANY language)",
            variable=self.auto_translate_var,
        ).pack(side="left")

        self.script_box = scrolledtext.ScrolledText(
            step2, wrap="word", height=12, font=("Segoe UI", 11),
            bg="#fbfbfd", relief="flat", highlightbackground=COL_BORDER, highlightthickness=1,
        )
        self.script_box.pack(fill="both", expand=True, padx=14, pady=(4, 14))

        # --- Step 3: generate ---
        step3_outer, step3 = self._card(self.root, "Step 3 · Generate")
        step3_outer.pack(fill="x", **pad)

        row5 = tk.Frame(step3, bg=COL_CARD)
        row5.pack(fill="x", padx=14, pady=(0, 6))
        self.generate_btn = ttk.Button(row5, text="▶  Generate speech (MP3)", style="Accent.TButton", command=self.generate)
        self.generate_btn.pack(side="left")
        self.play_btn = ttk.Button(row5, text="🔊 Play result", command=self.play_result, state="disabled")
        self.play_btn.pack(side="left", padx=8)
        self.save_btn = ttk.Button(row5, text="💾 Save as...", command=self.save_result, state="disabled")
        self.save_btn.pack(side="left")

        row6 = tk.Frame(step3, bg=COL_CARD)
        row6.pack(fill="x", padx=14, pady=(0, 12))
        ttk.Checkbutton(
            row6, text="Fast mode (quicker, less accurate voice match, no Urdu)",
            variable=self.fast_mode_var,
        ).pack(side="left")

        self.progress = ttk.Progressbar(self.root, mode="indeterminate")
        self.progress.pack(fill="x", padx=16, pady=(4, 4))

        status_bar = ttk.Label(self.root, textvariable=self.status_var, style="Sub.TLabel", anchor="w")
        status_bar.pack(fill="x", padx=16, pady=(0, 14))

    def _on_language_selected(self, event=None):
        code = self.lang_display_var.get().split(" - ")[0]
        self.language_var.set(code)

    # ---------------------------------------------------------- Step 1
    def browse_sample(self):
        path = filedialog.askopenfilename(title="Choose a voice sample", filetypes=SUPPORTED_SAMPLE_EXTS)
        if path:
            self.sample_path.set(path)
            self.sample_label.config(text=os.path.basename(path), foreground=COL_TEXT)
            self._last_was_mic_recording = False

    def choose_samples_folder(self):
        folder = filedialog.askdirectory(title="Choose where recorded voice samples are saved")
        if folder:
            self.samples_folder_var.set(folder)
            self.settings["samples_folder"] = folder
            save_settings(self.settings)
            os.makedirs(folder, exist_ok=True)

    def toggle_record(self):
        if not self.recorder.is_recording:
            try:
                self.recorder.start()
            except Exception as e:
                messagebox.showerror("Microphone error", f"Couldn't access microphone:\n{e}")
                return
            self._rec_start_time = time.time()
            self.record_btn.config(text="⏹ Stop recording")
            self._tick_record_timer()
        else:
            folder = self.samples_folder_var.get() or DEFAULT_SAMPLES_DIR
            os.makedirs(folder, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            saved_path = os.path.join(folder, f"voice_sample_{timestamp}.wav")
            saved = self.recorder.stop_and_save(saved_path)
            self.record_btn.config(text="🎙 Record from microphone")
            self.record_status.config(text="")
            if saved:
                self.sample_path.set(saved)
                self.sample_label.config(text=f"Recorded sample - saved to {os.path.basename(folder)}/", foreground=COL_TEXT)
                self._last_was_mic_recording = True
            else:
                messagebox.showwarning("No audio", "No audio was captured.")

    def _tick_record_timer(self):
        if self.recorder.is_recording:
            elapsed = time.time() - self._rec_start_time
            self.record_status.config(text=f"Recording... {elapsed:0.1f}s")
            self.root.after(100, self._tick_record_timer)

    # ---------------------------------------------------------- Step 2
    def load_script_file(self):
        path = filedialog.askopenfilename(title="Choose a script file", filetypes=SUPPORTED_TEXT_EXTS)
        if path:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.script_box.delete("1.0", "end")
            self.script_box.insert("1.0", content)

    # ---------------------------------------------------------- Step 3
    def generate(self):
        sample = self.sample_path.get()
        script = self.script_box.get("1.0", "end").strip()

        if not sample:
            messagebox.showwarning("Missing voice sample", "Please add a voice sample first.")
            return
        if not script:
            messagebox.showwarning("Missing script", "Please paste or load a script first.")
            return
        if not os.path.exists(sample):
            messagebox.showerror("Sample not found", f"The voice sample file no longer exists:\n{sample}")
            return

        self.generate_btn.config(state="disabled")
        self.play_btn.config(state="disabled")
        self.save_btn.config(state="disabled")
        self.progress.start(12)
        self.status_var.set("Starting...")

        thread = threading.Thread(target=self._generate_worker, args=(sample, script), daemon=True)
        thread.start()

    def _generate_worker(self, sample, script):
        try:
            lang = self.language_var.get()

            if self.auto_translate_var.get():
                script = translate_script(script, lang, status_callback=self._set_status_threadsafe)

            wav_path = os.path.join(tempfile.gettempdir(), "voice_clone_output.wav")
            if lang == "ur":
                generate_urdu_speech(sample, script, wav_path, status_callback=self._set_status_threadsafe)
            else:
                fast_mode = self.fast_mode_var.get()
                model = get_tts_model(status_callback=self._set_status_threadsafe, fast_mode=fast_mode)
                self._set_status_threadsafe("Generating audio...")
                generate_standard_speech(model, sample, script, lang, wav_path, status_callback=self._set_status_threadsafe)

            mp3_path = os.path.join(tempfile.gettempdir(), "voice_clone_output.mp3")
            final_path = convert_wav_to_mp3(wav_path, mp3_path, status_callback=self._set_status_threadsafe)

            self.output_path = final_path
            ext = os.path.splitext(final_path)[1].upper().lstrip(".")
            self._set_status_threadsafe(f"Done! ({ext}) Click Play or Save.")
            self.root.after(0, self._on_generate_done, True)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._set_status_threadsafe(f"Error: {e}")
            self.root.after(0, self._on_generate_done, False)

    def _set_status_threadsafe(self, text):
        self.root.after(0, lambda: self.status_var.set(text))

    def _on_generate_done(self, success):
        self.progress.stop()
        self.generate_btn.config(state="normal")
        if success:
            self.play_btn.config(state="normal")
            self.save_btn.config(state="normal")

    def play_result(self):
        if not self.output_path or not os.path.exists(self.output_path):
            return
        try:
            if sys.platform == "darwin":
                os.system(f"afplay '{self.output_path}'")
            elif sys.platform.startswith("linux"):
                os.system(f"xdg-open '{self.output_path}' >/dev/null 2>&1 &")
            else:
                os.startfile(self.output_path)  # Windows - opens with the default MP3 player
        except Exception as e:
            messagebox.showerror("Playback error", f"Couldn't play the file:\n{e}")

    def save_result(self):
        if not self.output_path or not os.path.exists(self.output_path):
            return
        ext = os.path.splitext(self.output_path)[1] or ".mp3"
        dest = filedialog.asksaveasfilename(
            defaultextension=ext,
            filetypes=[("MP3 audio", "*.mp3"), ("WAV audio", "*.wav"), ("All files", "*.*")],
            initialfile=f"my_voice_reading{ext}",
        )
        if dest:
            import shutil
            shutil.copyfile(self.output_path, dest)
            messagebox.showinfo("Saved", f"Saved to:\n{dest}")


def main():
    root = tk.Tk()
    app = VoiceCloneApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
