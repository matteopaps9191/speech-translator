# Downloads the Piper voice models listed in voice_list.py into voices/ (~820 MB total).
# Already-downloaded voices are skipped.
#   python download_voices.py

from pathlib import Path

import requests

from voice_list import VOICES

BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
VOICE_DIR = Path(__file__).resolve().parent / "voices"

# Local file names that differ from the official name (kept ASCII-only locally)
REMOTE_NAMES = {"pt_PT-tugao-medium": "pt_PT-tugão-medium"}


def voice_url(name, ext):
    # e.g. en_US-joe-medium -> en/en_US/joe/medium/en_US-joe-medium.onnx
    name = REMOTE_NAMES.get(name, name)
    locale, speaker, quality = name.split("-")
    family = locale.split("_")[0]
    return f"{BASE_URL}/{family}/{locale}/{speaker}/{quality}/{name}{ext}"


def download(url, dest):
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    tmp.replace(dest)


def main():
    VOICE_DIR.mkdir(exist_ok=True)
    for lang, name in VOICES.items():
        for ext in (".onnx", ".onnx.json"):
            dest = VOICE_DIR / f"{name}{ext}"
            if dest.exists():
                continue
            print(f"[{lang}] downloading {dest.name} ...")
            download(voice_url(name, ext), dest)
    print(f"All {len(VOICES)} voices are in {VOICE_DIR}")


if __name__ == "__main__":
    main()
