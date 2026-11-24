# Speak into the computer mic -> transcribe -> translate -> speak the translation -> save as WAV.
#
# Usage (from the project folder):
#   python speak.py --src en --tgt es
# Press Enter to start talking, Enter again to stop.
# Target languages with a voice: es, fr, pt, en, de, it, zh, ja, ko, ru, ar, hi, nl (see voice_list.py).

import argparse
import os
import queue
import sys
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

HERE = Path(__file__).resolve().parent
os.chdir(HERE)  # run from the project folder no matter where it was started

from stt import transcribe          # noqa: E402
from translate import DailyLimitReached, translate  # noqa: E402
from tts import TTS, Voices, output_rate  # noqa: E402

MIC_RATE = 16000  # Whisper works at 16 kHz
OUTPUT_DIR = HERE / "output"


def save_wav(path, pcm_bytes, rate):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm_bytes)


def record():
    """Record from the default mic between two Enter presses. Returns (int16 bytes, rate)."""
    try:
        rate = MIC_RATE
        sd.check_input_settings(samplerate=rate, channels=1, dtype="int16")
    except Exception:
        rate = int(sd.query_devices(kind="input")["default_samplerate"])

    chunks = queue.Queue()

    def callback(indata, frames, time, status):
        if status:
            print(status, file=sys.stderr)
        chunks.put(indata.copy())

    input("Press Enter to start recording...")
    with sd.InputStream(samplerate=rate, channels=1, dtype="int16", callback=callback):
        input("Recording... press Enter to stop.")

    blocks = []
    while not chunks.empty():
        blocks.append(chunks.get())
    if not blocks:
        return b"", rate
    return np.concatenate(blocks).tobytes(), rate


def main():
    parser = argparse.ArgumentParser(description="Speak, translate, and save the translated speech.")
    parser.add_argument("--src", default="en", help="language you speak (e.g. en, es, fr, pt)")
    parser.add_argument("--tgt", default="es", help="language to translate into (es, fr, pt, en, de, it, zh, ja, ko, ru, ar, hi, nl)")
    args = parser.parse_args()

    if args.tgt not in Voices:
        sys.exit(f"No voice for '{args.tgt}'. Choose one of: {', '.join(Voices)}")

    OUTPUT_DIR.mkdir(exist_ok=True)

    audio, rate = record()
    if len(audio) < rate * 2 * 0.3:  # under ~0.3 s
        sys.exit("Recording too short, nothing to do.")

    # only the latest recording/translation are kept; each run overwrites them
    for old in OUTPUT_DIR.glob("latest_input.*"):
        old.unlink(missing_ok=True)
    input_path = OUTPUT_DIR / "latest_input.wav"
    save_wav(input_path, audio, rate)
    print(f"Saved your recording: {input_path}")

    text = transcribe(str(input_path), args.src)
    print(f"\nYou said ({args.src}): {text}")
    if not text:
        sys.exit("No speech detected.")

    # Google rejects same-language requests, so just repeat the text
    try:
        translated = text if args.src == args.tgt else translate(text, args.tgt, args.src)
    except DailyLimitReached as error:
        sys.exit(str(error))
    if translated is None:
        sys.exit("Translation failed (check key.env and your internet connection).")
    print(f"Translation ({args.tgt}): {translated}")

    speech = TTS(translated, args.tgt)
    if not speech:
        sys.exit("Text-to-speech failed.")

    output_path = OUTPUT_DIR / "latest_translation.wav"
    save_wav(output_path, speech, output_rate)
    print(f"\nSaved translated audio: {output_path}")


if __name__ == "__main__":
    main()
