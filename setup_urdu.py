"""
One-time setup for Urdu support in Voice Clone Reader.

Run this AFTER downloading config.json, model.pth, vocab.json, and
tokenizer.py from https://huggingface.co/suhaibrashid17/XTTS-v2-Urdu-FT
into the 'urdu_model' folder next to this script.

It patches your installed TTS package so it can understand Urdu text,
by swapping in the tokenizer file that ships with that fine-tuned model.
A backup of the original file is kept, so this can be undone.
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE_TOKENIZER = os.path.join(HERE, "urdu_model", "tokenizer.py")


def main():
    if not os.path.exists(SOURCE_TOKENIZER):
        print("ERROR: Could not find urdu_model/tokenizer.py")
        print("Download it first from:")
        print("  https://huggingface.co/suhaibrashid17/XTTS-v2-Urdu-FT")
        print("(along with config.json, model.pth, and vocab.json)")
        sys.exit(1)

    try:
        import TTS
    except ImportError:
        print("ERROR: TTS package not installed.")
        print("Run install.bat (or pip install -r requirements.txt) first.")
        sys.exit(1)

    tts_dir = os.path.dirname(os.path.abspath(TTS.__file__))
    candidates = [
        os.path.join(tts_dir, "tts", "layers", "xtts", "tokenizer.py"),
        os.path.join(tts_dir, "tts", "layers", "xtts", "tokenizers.py"),
    ]
    real_target = next((p for p in candidates if os.path.exists(p)), None)

    if real_target is None:
        print("ERROR: Could not find the tokenizer file to replace. Looked at:")
        for c in candidates:
            print(f"  {c}")
        sys.exit(1)

    backup = real_target + ".backup"
    if not os.path.exists(backup):
        shutil.copyfile(real_target, backup)
        print(f"Backed up original to: {backup}")
    else:
        print("Backup already exists, skipping backup step.")

    shutil.copyfile(SOURCE_TOKENIZER, real_target)
    print(f"Patched: {real_target}")
    print()
    print("Urdu support installed! Select 'ur' as the language in the app.")


if __name__ == "__main__":
    main()
